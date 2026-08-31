# CallRadar

AI-powered call centre analysis platform. Ingests stereo MP3 recordings, transcribes both channels, and runs six AI engines to surface risk levels, key moments, behavioural patterns, and evidence-backed findings.

**The 1,441 calls in this repo are already processed** — the database seeds automatically on first `docker-compose up`.

---

## Quick Start

### Prerequisites
- Docker + Docker Compose
- AWS credentials (access to `callradar-prod` S3 bucket & Parameters store)

### 1. Clone and configure

```bash
git clone https://github.com/BalajiK211097/callradar.git
cd callradar
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Notes |
|---|---|
| `AWS_ACCESS_KEY_ID` | **Required** — for S3 presigned URLs (audio playback) |
| `AWS_SECRET_ACCESS_KEY` | **Required** |
| `AWS_REGION` | Default: `ap-south-1` |

### 2. Build and start the stack

```bash
# First time — builds the backend and frontend images (takes ~3–5 min)
docker-compose up --build

# Subsequent runs — images are cached, starts in seconds
docker-compose up
```

The database auto-seeds with all 1,441 processed calls on first startup. Wait for `backend_1 | Application startup complete`, then open:

- **Dashboard** → http://localhost:5173
- **API docs** → http://localhost:8000/docs

Login: any username / password (demo auth gate).

> **Fresh start** — if you've run it before: `docker-compose down -v && docker-compose up`

---

## What to Explore

| Page | URL | What you'll see |
|---|---|---|
| Overview | `/` | KPI tiles, manager attention queue, unresolved calls, trending intents, agent snapshot |
| All Calls | `/calls` | 1,441 calls — filter by risk, outcome, agent, session |
| Call Detail | `/calls/:id` | Full transcript, mood trajectory, detected moments with evidence quotes, scores |
| Agents | `/agents` | Per-agent resolution rates, average scores, call history |
| Customers | `/customers` | Repeat-caller detection, risk history |
| Trends | `/trends` | Call volume, resolution rate, attention score over time |

---

## Pipeline (6 stages)

```
S3 audio (presigned URL)
    │
    ▼  Stage 1 — deepgram_ingest.py
Deepgram Nova-3: multichannel transcription + sentiment + entities + topics + summary + intent
    │
    ▼  Stage 2 — builder.py
ConversationModel: turns, sentiment, silence/overtalk from timestamp gaps
    │
    ├──────────────────────┐  Stage 3 (parallel)
    ▼                      ▼
semantic.py           behavioral.py
DeepSeek reasoning    Mood shifts, acoustic signals
    │                      │
    └──────────────────────┘
    │
    ▼  Stage 4 — moment.py
Typed Moments: COMPLAINT, FRAUD_SIGNAL, MOOD_SHIFT, LONG_SILENCE, OVERTALK, …
    │
    ▼  Stage 5 — evidence.py
Two-stage verification: select candidate turns → verify quotes support the claim
    │
    ▼  Stage 6 — decision.py
DecisionResult: attention score, QA score, outcome, risk level
    │
    ▼
PostgreSQL (CallRecord + MomentRecord)
    │
    ▼
FastAPI → React dashboard
```

---

## Project Layout

```
pipeline/           # AI processing
  orchestrator.py   # Single entry point: process_call()
  config.py         # All model names, thresholds, weights
  models.py         # Shared Pydantic contracts between engines
  engines/          # semantic, behavioral, moment, evidence, decision

backend/            # FastAPI — 17 endpoints across 4 routers
  main.py           # App entry, lifespan, secrets bootstrap
  routers/          # calls, agents, customers, flagged
  db.py             # ORM models, save_analysis(), mark_failed()

frontend/src/       # React 19 + Vite + Tailwind CSS v4
  pages/            # Overview, AllCalls, CallDetail, Agents, Trends…
  lib/api.ts        # Typed fetch client

db/seed.sql.gz      # Pre-processed 1,441 calls — auto-loads on first up
scripts/            # batch_submit.py — submit/reprocess calls in bulk
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Transcription | Deepgram Nova-3 (multichannel, one API call) |
| AI reasoning | DeepSeek v4-flash via OpenAI-compatible API |
| Audio storage | AWS S3 — presigned URLs, no local files needed |
| Backend | FastAPI + SQLAlchemy 2.0 async + asyncpg |
| Database | PostgreSQL 16 |
| Frontend | React 19 + Vite 8 + TypeScript + Tailwind CSS v4 |
| Infra | Docker Compose (postgres, backend, frontend) |

---

## Processing New Calls

To submit additional calls (requires Deepgram + DeepSeek API keys in `.env`):

```bash
# Test with 10 calls first
python scripts/batch_submit.py --limit 10

# Submit all unprocessed
python scripts/batch_submit.py

# Resubmit failed calls
python scripts/batch_submit.py
```

The script reads SIDs from `data/metadata/`, skips already-done calls, and submits at concurrency 2 by default.
