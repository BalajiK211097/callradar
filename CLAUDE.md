# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CallRadar is an AI-powered call analysis platform. It ingests stereo MP3 recordings of call-centre calls, transcribes them, runs six parallel analysis engines, and surfaces behavioral patterns, business outcomes, decision points, key moments, and semantic insights.

**All audio and metadata live in S3** (`callradar-prod`, region `ap-south-1`). The `data/` directory is gitignored and local files are never required for production operation.

- S3 audio key: `audio/<sid>.mp3`
- S3 metadata key: `metadata/<sid>.json`

## Architecture

Three distinct layers with separate `requirements.txt` files.

### Pipeline (`pipeline/`)

The AI/ML processing layer. `orchestrator.process_call()` is the single entry point.

Execution order (6 stages):

| Stage | Module | Description |
|---|---|---|
| 1 | `audio_intelligence/deepgram_ingest.py` | **Single Deepgram Nova-3 call** — accepts a local `Path` or an HTTPS presigned URL; multichannel transcription + sentiment per utterance + entities + topics + summary + intent |
| 2 | `conversation_model/builder.py` | Merges Deepgram utterances into Turn list; maps sentiment onto turns; reconstructs silence/overtalk from timestamp gaps; maps entities |
| 3a/3b | `engines/semantic.py`, `engines/behavioral.py` | Two engines in parallel via `asyncio.gather`; semantic runs Claude Sonnet with transcript + post-call metadata (surveys, MOS) to detect moments contextually and compute scores |
| 4 | `engines/moment.py` | Converts semantic detected_moments → Moment list; appends deterministic MOOD_SHIFT, LONG_SILENCE, OVERTALK |
| 5 | `engines/evidence.py` | Two-stage Claude verification: skips Haiku when turn_id already supplied → Sonnet verifies quotes |
| 6 | `engines/decision.py` | Thin formatter: wraps Claude's attention/QA scores into DecisionResult, computes deterministic outcome |

Key files:
- `models.py` — shared Pydantic data contracts between all engines (read this before touching any engine)
- `config.py` — all model names, thresholds, phrase lists, scoring weights; engine files must import from here. `USE_CLAUDE_SEMANTIC = True` toggles Claude Sonnet semantic engine
- `metadata.py` — loads and normalises `data/metadata/<sid>.json`; `load(mp3_path)` auto-resolves the companion JSON
- `secrets.py` — bootstraps AWS Parameter Store secrets into `os.environ`; called once at backend startup before any other import
- `test_single_call.py` — manual end-to-end test harness with per-stage timing banner

ffmpeg and pydub are **not required** — the raw stereo MP3 is sent directly to Deepgram; no local audio processing occurs.

### Backend (`backend/`)

FastAPI + async PostgreSQL (SQLAlchemy 2.0 + asyncpg). Connection string is read from `DATABASE_URL` env var at startup.

- `main.py` — app entry point; calls `pipeline.secrets.load_secrets()` **before all other imports** (including DB), then `init_db()` via lifespan hook
- `s3.py` — S3 helpers: `upload_bytes()`, `presigned_url()`, `get_json()`, `audio_key()`, `metadata_key()`; all use `S3_BUCKET_NAME` env var
- `db.py` — ORM models (`CallRecord`, `MomentRecord`), `save_analysis()`, `mark_failed()`; `mp3_path` column stores either an absolute local path (legacy) or an S3 key like `audio/<sid>.mp3` — detected via `not Path(mp3_path).is_absolute()`
- `cache.py` — LRU in-memory cache (200 entries) for deserialising `analysis_json`
- `models/` — Pydantic request/response schemas (`call`, `analysis`, `moment`, `transcript`)
- `routers/calls.py` — 9 endpoints; `_run_pipeline` detects S3 key vs local path and generates presigned URL + fetches S3 metadata before calling the pipeline; `get_audio` returns HTTP 302 redirect to presigned URL for S3-backed calls
- `routers/agents.py`, `routers/customers.py`, `routers/flagged.py` — cross-call views

Pipeline modules are lazy-imported inside background task functions (inside the function body, not at module level) to avoid loading heavy models at server startup.

### Frontend (`frontend/src/`)

Vite 8 + React 19 + TypeScript + Tailwind CSS v4 SPA. Package manager is **pnpm**.

- `pages/` — Overview, AllCalls, CallDetail, AgentsList, AgentDetail, CustomersList, CustomerDetail, Trends, Login
- `components/` — Badges, Layout
- `lib/api.ts` — typed fetch client wrapping all backend endpoints
- `lib/format.ts` — formatting helpers (fmtTime, fmtDuration, fmtRate, initials)
- `context/AuthContext.tsx` — auth gate (demo login)
- `routes.tsx` — React Router v8 route definitions

`vite.config.ts` uses only `@vitejs/plugin-react` and `@tailwindcss/vite`. Do not re-add `.figma/make/site.json` imports or `figmaSiteConfiguration`/`figmaMakeKitPlugin` — they only work inside Figma's cloud environment.

## Environment Setup

Only three lines are needed in `.env` — everything else is pulled from AWS Parameter Store:

```bash
cp .env.example .env
# Fill in:
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-south-1
```

For local dev without Parameter Store, also set:
```
ANTHROPIC_API_KEY=sk-ant-...
DEEPGRAM_API_KEY=...
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/callradar
S3_BUCKET_NAME=callradar-prod
```

## Development Commands

```bash
# Pipeline
pip install -r pipeline/requirements.txt
python pipeline/test_single_call.py data/audio/<sid>.mp3   # local path
# or pass an S3 presigned URL directly

# Backend
psql -U postgres -c "CREATE DATABASE callradar;"
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload     # http://localhost:8000/docs

# Frontend
cd frontend && pnpm install && pnpm dev   # http://localhost:5173

# Docker (full stack — fresh start)
docker-compose down -v && docker-compose up

# Batch submit all 1441 calls to the running API (run on host, not inside container)
pip install httpx
python scripts/batch_submit.py --limit 10    # test first
python scripts/batch_submit.py               # full run
python scripts/batch_submit.py --force       # resubmit even done calls
```

`scripts/batch_submit.py` reads SIDs from `data/metadata/` locally, checks the API for already-done calls, and POSTs to `POST /calls/submit` with `mp3_path: "audio/<sid>.mp3"` (an S3 key). The backend fetches audio from S3 and runs the pipeline as a background task.

## Key Data Flow

```
S3: audio/<sid>.mp3  +  metadata/<sid>.json
         │
         │  presigned URL generated by backend/s3.py
         ▼
deepgram_ingest.py — ONE Deepgram Nova-3 API call
  Deepgram fetches audio directly from the presigned URL
  multichannel: channel[0]=agent, channel[1]=customer
  + sentiment per utterance + entities + topics + summary + intent
         │
         ▼
builder.py — DeepgramResult → ConversationModel
  (sentiment_score on every Turn; silence/overtalk from timestamp gaps)
         │
    ┌────┼────┐  (parallel)
    ▼    ▼    ▼
semantic  behavioral  business
    └────┼────┘
         ▼
moment.py → evidence.py (Claude Haiku → Sonnet) → decision.py
         │
         ▼
backend/db.save_analysis()
   → CallRecord (scalar columns + analysis_json blob)
   → MomentRecord (one row per moment, for cross-call queries)
         │
         ▼
backend/routers/ → frontend/
```

**`effective_resolved` flow** — Claude's semantic judgment (`SemanticResult.resolved`) takes priority over the business engine phrase-match (`BusinessResult.resolved`). The orchestrator computes `effective_resolved` once and passes it explicitly to `moment.detect()`, `decision.score()`, and the final `CallAnalysis`. Never read `business.resolved` directly downstream of the orchestrator — always use the passed `resolved` parameter or `effective_resolved`.

**Backend API** — 17 endpoints across 4 routers: `/calls` (submit, list, stats, detail, transcript, moments, evidence, reprocess), `/agents` (list, calls, stats), `/customers` (calls, profile), `/flagged` (list, stats). All DB writes go through `db.save_analysis()` which populates both scalar columns on `CallRecord` (for fast filtering) and the full `analysis_json` blob.

## Coding Rules

These rules apply to all pipeline and backend code:

- Every function has a docstring.
- Every engine has `try/except` with specific exception types — never a bare `except:`.
- If a stage fails, log the error and `raise` — never silently swallow exceptions.
- All configs go in `pipeline/config.py` — never hardcode model names, thresholds, or phrase lists in engine files.
- Type hints on every function signature.
- Use `async`/`await` throughout for IO operations.
- All Pydantic models use `model_config = ConfigDict(frozen=False)`.

## Metadata Fields

`pipeline/metadata.py` normalises the raw JSON into these keys used downstream:

| Key | Source | Used by |
|---|---|---|
| `sid` | `raw.sid` | call_id |
| `agent_name` | `raw.agent.name` | `builder.py` participant naming |
| `customer_name` | `raw.caller.metadata["first and last name"]` | `builder.py` participant naming |
| `session` | `raw.session` | DB column, `?session=` filter |
| `agent_speaker_id` / `caller_speaker_id` | `raw.agent.speaker_id` | Deepgram multichannel maps left=agent, right=customer |
| `labels.caller_mos` / `labels.agent_mos` | `raw.labels.caller_mos` | DB quality labels |
| `labels.lhvb_script` | `raw.labels.lhvb_script` | DB quality label |
| `agent_survey` / `caller_survey` | `raw.agent.survey` / `raw.caller.survey` | DB survey columns |
| `call_start_ms` | `raw.start` | `call_start_utc` DB column |
