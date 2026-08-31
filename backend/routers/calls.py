"""
/calls router — submit, list, inspect, and reprocess calls.

Endpoints
---------
POST   /calls/submit          Register a call and fire the pipeline
POST   /calls/batch           Register many calls at once
GET    /calls                 Paginated list with optional filters
GET    /calls/stats           Aggregate statistics across all calls
GET    /calls/{call_id}       Full analysis for a single call
GET    /calls/{call_id}/transcript   Turn-by-turn transcript
GET    /calls/{call_id}/moments      Detected moments
GET    /calls/{call_id}/evidence     Evidence items
POST   /calls/{call_id}/reprocess   Rerun the pipeline for a call
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import uuid as _uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.cache import analysis_cache
from backend.db import (
    AsyncSessionLocal,
    CallRecord,
    MomentRecord,
    get_session,
    mark_failed,
    save_analysis,
)
from backend.models.analysis import AnalysisResponse, StatsResponse
from backend.models.call import (
    BatchSubmitRequest,
    CallListResponse,
    CallStatusResponse,
    CallSummary,
    SubmitCallRequest,
)
from backend.models.moment import MomentListResponse, MomentResponse
from backend.models.transcript import (
    EvidenceItemResponse,
    EvidenceListResponse,
    TranscriptResponse,
    TurnResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Background pipeline task
# ---------------------------------------------------------------------------


async def _run_pipeline(
    call_id: str,
    mp3_path: str,
    metadata: dict[str, Any] | None,
) -> None:
    """Run the full AI pipeline for a call and persist the result.

    Runs as a FastAPI background task.  Opens its own DB session so it
    is not tied to the HTTP request lifecycle.

    Args:
        call_id: Unique call identifier.
        mp3_path: Absolute or repo-relative path to the MP3 file.
        metadata: Optional metadata dict passed to the pipeline.
    """
    from pipeline import orchestrator  # lazy imports — avoids loading heavy models

    async with AsyncSessionLocal() as db:
        try:
            await db.execute(
                update(CallRecord)
                .where(CallRecord.call_id == call_id)
                .values(status="processing")
            )
            await db.commit()

            # Determine audio source and load metadata.
            # mp3_path is either an S3 key ("audio/<id>.mp3") or a legacy absolute path.
            is_s3_key = not Path(mp3_path).is_absolute()
            if is_s3_key:
                from backend.s3 import presigned_url, get_json, metadata_key
                audio_source: str | Path = presigned_url(mp3_path)
                # Try fetching companion metadata JSON from S3
                s3_meta = get_json(metadata_key(call_id))
                raw_metadata = s3_meta or metadata or {}
            else:
                from pipeline import metadata as meta_loader
                audio_source = Path(mp3_path)
                raw_metadata = meta_loader.load(audio_source) or (metadata or {})

            analysis = await orchestrator.process_call(
                call_id=call_id,
                mp3_path=audio_source,
                metadata=raw_metadata or None,
            )

            await save_analysis(db, call_id, analysis, raw_metadata=raw_metadata)
            analysis_cache.delete(call_id)  # invalidate stale cache entry
            logger.info("Pipeline complete for call_id=%s", call_id)

        except Exception as exc:
            logger.exception("Pipeline failed for call_id=%s", call_id)
            await mark_failed(db, call_id, str(exc))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record_to_summary(record: CallRecord) -> CallSummary:
    """Convert a CallRecord ORM row to a CallSummary response model.

    Args:
        record: SQLAlchemy ORM row.

    Returns:
        Serialisable CallSummary.
    """
    topics: list[str] = []
    if record.topics_json:
        try:
            topics = json.loads(record.topics_json)
        except json.JSONDecodeError:
            pass

    moment_types: list[str] = []
    if record.moment_types_json:
        try:
            moment_types = json.loads(record.moment_types_json)
        except json.JSONDecodeError:
            pass

    return CallSummary(
        call_id=record.call_id,
        status=record.status,
        session=record.session,
        agent_name=record.agent_name,
        customer_name=record.customer_name,
        duration_seconds=record.duration_seconds,
        risk_level=record.risk_level,
        outcome=record.outcome,
        attention_score=record.attention_score,
        qa_score=record.qa_score,
        resolved=bool(record.resolved) if record.resolved is not None else None,
        intent=record.intent,
        topics=topics,
        moment_types=moment_types,
        mood_start=record.mood_start,
        mood_end=record.mood_end,
        top_moment_type=record.top_moment_type,
        call_start_utc=record.call_start_utc,
        label_caller_mos=record.label_caller_mos,
        label_agent_mos=record.label_agent_mos,
        created_at=record.created_at,
        processed_at=record.processed_at,
    )


async def _get_record_or_404(db: AsyncSession, call_id: str) -> CallRecord:
    """Fetch a CallRecord or raise 404.

    Args:
        db: Active async database session.
        call_id: The call identifier to look up.

    Returns:
        CallRecord ORM instance.

    Raises:
        HTTPException: 404 if the call_id is not found.
    """
    record = await db.scalar(select(CallRecord).where(CallRecord.call_id == call_id))
    if record is None:
        raise HTTPException(status_code=404, detail=f"call_id={call_id!r} not found")
    return record


# ---------------------------------------------------------------------------
# Submit endpoints
# ---------------------------------------------------------------------------


@router.post("/upload", response_model=CallStatusResponse, status_code=202)
async def upload_call(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
) -> CallStatusResponse:
    """Accept a multipart MP3/WAV upload, save it to disk, and start the pipeline.

    The file is written to data/audio/<call_id>.mp3 under the repo root.
    A short UUID suffix is appended to the filename stem to avoid collisions
    with the pre-loaded dataset.

    Args:
        background_tasks: FastAPI background task registry.
        file: Uploaded audio file (MP3 or WAV).
        db: Injected async database session.

    Returns:
        CallStatusResponse with status='pending'.

    Raises:
        HTTPException: 415 if the file is not an audio file.
    """
    filename = file.filename or "upload.mp3"
    if not (
        (file.content_type or "").startswith("audio/")
        or filename.lower().endswith(".mp3")
        or filename.lower().endswith(".wav")
    ):
        raise HTTPException(status_code=415, detail="Only MP3 or WAV files are accepted.")

    stem = Path(filename).stem
    call_id = f"{stem}_{_uuid.uuid4().hex[:8]}"

    existing = await db.scalar(select(CallRecord).where(CallRecord.call_id == call_id))
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"call_id={call_id!r} already exists",
        )

    contents = await file.read()

    from backend.s3 import upload_bytes, audio_key
    s3_key = audio_key(call_id)
    upload_bytes(contents, s3_key, content_type="audio/mpeg")

    record = CallRecord(call_id=call_id, mp3_path=s3_key, status="pending")
    db.add(record)
    await db.commit()
    await db.refresh(record)

    background_tasks.add_task(_run_pipeline, call_id, s3_key, None)
    logger.info("Uploaded to S3 and submitted call_id=%s -> s3://%s", call_id, s3_key)

    return CallStatusResponse(call_id=call_id, status="pending", created_at=record.created_at)


@router.post("/submit", response_model=CallStatusResponse, status_code=202)
async def submit_call(
    body: SubmitCallRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
) -> CallStatusResponse:
    """Register a call and start the AI pipeline as a background task.

    The call_id defaults to the MP3 filename stem if not provided.
    Returns 409 if the call_id already exists.

    Args:
        body: SubmitCallRequest with mp3_path and optional metadata.
        background_tasks: FastAPI background task registry.
        db: Injected async database session.

    Returns:
        CallStatusResponse with status='pending'.
    """
    call_id = body.call_id or Path(body.mp3_path).stem

    existing = await db.scalar(
        select(CallRecord).where(CallRecord.call_id == call_id)
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"call_id={call_id!r} already exists (status={existing.status})",
        )

    metadata: dict[str, Any] = body.metadata or {}
    if body.agent_name:
        metadata.setdefault("agent_name", body.agent_name)
    if body.customer_name:
        metadata.setdefault("customer_name", body.customer_name)

    record = CallRecord(
        call_id=call_id,
        mp3_path=body.mp3_path,
        status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    background_tasks.add_task(
        _run_pipeline, call_id, body.mp3_path, metadata or None
    )
    logger.info("Submitted call_id=%s from %s", call_id, body.mp3_path)

    return CallStatusResponse(
        call_id=call_id,
        status="pending",
        created_at=record.created_at,
    )


@router.post("/batch", status_code=202)
async def submit_batch(
    body: BatchSubmitRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Register multiple calls and start a pipeline task for each.

    Skips any call_id that already exists (returns it in the
    'skipped' list rather than raising an error).

    Args:
        body: BatchSubmitRequest containing a list of SubmitCallRequest.
        background_tasks: FastAPI background task registry.
        db: Injected async database session.

    Returns:
        Dict with 'submitted' and 'skipped' lists.
    """
    submitted: list[str] = []
    skipped: list[str] = []

    for item in body.calls:
        call_id = item.call_id or Path(item.mp3_path).stem

        existing = await db.scalar(
            select(CallRecord).where(CallRecord.call_id == call_id)
        )
        if existing is not None:
            skipped.append(call_id)
            continue

        metadata: dict[str, Any] = item.metadata or {}
        if item.agent_name:
            metadata.setdefault("agent_name", item.agent_name)
        if item.customer_name:
            metadata.setdefault("customer_name", item.customer_name)

        record = CallRecord(call_id=call_id, mp3_path=item.mp3_path, status="pending")
        db.add(record)
        background_tasks.add_task(
            _run_pipeline, call_id, item.mp3_path, metadata or None
        )
        submitted.append(call_id)

    await db.commit()
    logger.info("Batch submitted %d calls, skipped %d", len(submitted), len(skipped))
    return {"submitted": submitted, "skipped": skipped}


# ---------------------------------------------------------------------------
# List / stats endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=CallListResponse)
async def list_calls(
    page: int = 1,
    page_size: int = 50,
    status: str | None = None,
    risk_level: str | None = None,
    outcome: str | None = None,
    agent_name: str | None = None,
    session: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> CallListResponse:
    """Return a paginated list of call summaries with optional filters.

    Args:
        page: 1-indexed page number.
        page_size: Rows per page (max 200).
        status: Filter by status (pending/processing/done/failed).
        risk_level: Filter by risk level (LOW/MEDIUM/HIGH/CRITICAL).
        outcome: Filter by outcome (RESOLVED/UNRESOLVED/ESCALATED).
        agent_name: Filter by agent name (exact match).
        db: Injected async database session.

    Returns:
        CallListResponse with pagination metadata and summary items.
    """
    page_size = min(page_size, 200)

    stmt = select(CallRecord).order_by(CallRecord.created_at.desc())
    count_stmt = select(func.count()).select_from(CallRecord)

    if status:
        stmt = stmt.where(CallRecord.status == status)
        count_stmt = count_stmt.where(CallRecord.status == status)
    if risk_level:
        stmt = stmt.where(CallRecord.risk_level == risk_level)
        count_stmt = count_stmt.where(CallRecord.risk_level == risk_level)
    if outcome:
        stmt = stmt.where(CallRecord.outcome == outcome)
        count_stmt = count_stmt.where(CallRecord.outcome == outcome)
    if agent_name:
        stmt = stmt.where(CallRecord.agent_name == agent_name)
        count_stmt = count_stmt.where(CallRecord.agent_name == agent_name)
    if session:
        stmt = stmt.where(CallRecord.session == session)
        count_stmt = count_stmt.where(CallRecord.session == session)

    total = await db.scalar(count_stmt) or 0
    offset = (page - 1) * page_size
    rows = (await db.scalars(stmt.offset(offset).limit(page_size))).all()

    return CallListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_record_to_summary(r) for r in rows],
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_session)) -> StatsResponse:
    """Return aggregate statistics across all calls in the database.

    Args:
        db: Injected async database session.

    Returns:
        StatsResponse with counts, averages, and breakdowns.
    """
    rows = (await db.scalars(select(CallRecord))).all()

    total = len(rows)
    done = [r for r in rows if r.status == "done"]
    failed = sum(1 for r in rows if r.status == "failed")
    pending = sum(1 for r in rows if r.status == "pending")
    processing = sum(1 for r in rows if r.status == "processing")

    qa_scores = [r.qa_score for r in done if r.qa_score is not None]
    att_scores = [r.attention_score for r in done if r.attention_score is not None]
    avg_qa = round(sum(qa_scores) / len(qa_scores), 1) if qa_scores else None
    avg_att = round(sum(att_scores) / len(att_scores), 1) if att_scores else None

    risk_breakdown: dict[str, int] = {}
    outcome_breakdown: dict[str, int] = {}
    resolved_count = escalated_count = unresolved_count = 0

    for r in done:
        if r.risk_level:
            risk_breakdown[r.risk_level] = risk_breakdown.get(r.risk_level, 0) + 1
        if r.outcome:
            outcome_breakdown[r.outcome] = outcome_breakdown.get(r.outcome, 0) + 1
            if r.outcome == "RESOLVED":
                resolved_count += 1
            elif r.outcome == "ESCALATED":
                escalated_count += 1
            else:
                unresolved_count += 1

    return StatsResponse(
        total_calls=total,
        done_calls=len(done),
        failed_calls=failed,
        pending_calls=pending,
        processing_calls=processing,
        avg_qa_score=avg_qa,
        avg_attention_score=avg_att,
        resolved_count=resolved_count,
        unresolved_count=unresolved_count,
        escalated_count=escalated_count,
        risk_breakdown=risk_breakdown,
        outcome_breakdown=outcome_breakdown,
    )


# ---------------------------------------------------------------------------
# Aggregate / trend endpoints (must come before /{call_id} to avoid clash)
# ---------------------------------------------------------------------------

# Stale-while-revalidate cache: serve old data instantly, refresh in background.
_intent_groups_cache: dict[str, Any] = {"data": None, "ts": 0.0, "refreshing": False}
_INTENT_CACHE_TTL = 1800.0  # 30 minutes — intents don't change that fast


async def _compute_intent_groups(db: AsyncSession, limit: int = 10) -> list[dict]:
    """Query the DB and call DeepSeek to group intents. Updates the cache in place.

    Args:
        db: Active async database session.
        limit: Maximum number of groups to return.

    Returns:
        List of dicts with 'intent' and 'count', sorted descending.
    """
    import time as _time

    rows = (
        await db.scalars(
            select(CallRecord)
            .where(CallRecord.status == "done")
            .where(CallRecord.intent.is_not(None))
        )
    ).all()

    raw_counts: dict[str, int] = {}
    for r in rows:
        if r.intent:
            raw_counts[r.intent] = raw_counts.get(r.intent, 0) + 1

    if not raw_counts:
        return []

    if len(raw_counts) == 1:
        intent, cnt = next(iter(raw_counts.items()))
        return [{"intent": intent, "count": cnt}]

    top_intents = sorted(raw_counts.items(), key=lambda x: -x[1])[:100]

    try:
        import openai as _openai
        from pipeline import config as _cfg

        ai_client = _openai.AsyncOpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=_cfg.DEEPSEEK_BASE_URL,
            timeout=_cfg.DEEPSEEK_SEMANTIC_TIMEOUT,
        )
        lines = "\n".join(f"({c}x) {i}" for i, c in top_intents)
        prompt = (
            "You are helping label call-centre data.\n"
            "Group these call intents into short, meaningful category names "
            "(e.g. 'Money Transfer', 'Credit Card Replacement', 'Account Inquiry').\n\n"
            f"Intents (with call counts):\n{lines}\n\n"
            "Return ONLY a JSON array — no explanation, no markdown fences:\n"
            '[{"group":"Category Name","count":N}, ...]\n'
            "where count = sum of the call counts for intents in that group. "
            f"Sorted by count descending. Maximum {limit} groups."
        )

        resp = await ai_client.chat.completions.create(
            model=_cfg.DEEPSEEK_MODEL,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )

        text = (resp.choices[0].message.content or "").strip()
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1].lstrip("json").strip() if len(parts) > 1 else text

        groups = json.loads(text)
        result = [
            {"intent": g["group"], "count": g["count"]}
            for g in groups
            if g.get("group") and isinstance(g.get("count"), int)
        ][:limit]

    except Exception:
        logger.exception("Intent grouping via DeepSeek failed, falling back to raw counts")
        sorted_intents = sorted(raw_counts.items(), key=lambda x: -x[1])
        result = [{"intent": i, "count": c} for i, c in sorted_intents[:limit]]

    _intent_groups_cache["data"] = result
    _intent_groups_cache["ts"] = _time.time()
    _intent_groups_cache["refreshing"] = False
    return result


@router.get("/trending-intents", response_model=list[dict])
async def get_trending_intents(
    limit: int = 10,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return call intents semantically grouped into named categories.

    Stale-while-revalidate: if cached data exists (even expired), return it
    immediately and trigger a background refresh.  Only blocks on the first
    ever call when there is no cached data at all.

    Args:
        limit: Maximum number of groups to return (default 10).
        background_tasks: FastAPI background task registry.
        db: Injected async database session.

    Returns:
        List of dicts with 'intent' (group label) and 'count', descending.
    """
    import time as _time

    cached = _intent_groups_cache
    now = _time.time()
    is_stale = now - cached["ts"] >= _INTENT_CACHE_TTL

    if cached["data"] is not None:
        if is_stale and not cached["refreshing"]:
            # Return stale data instantly; kick off background refresh
            cached["refreshing"] = True
            background_tasks.add_task(_compute_intent_groups, db, limit)
        return cached["data"][:limit]

    # No cache at all (first ever request) — must wait for fresh data
    return await _compute_intent_groups(db, limit)


@router.get("/trends", response_model=list[dict])
async def get_trends(
    days: int = 30,
    db: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Return daily aggregated metrics for the Trends page.

    Buckets by call_start_utc when available, falling back to processed_at.

    Args:
        days: Number of past days to include (default 30).
        db: Injected async database session.

    Returns:
        List of dicts per day: date, call_count, avg_score, resolution_rate.
    """
    rows = (
        await db.scalars(
            select(CallRecord).where(CallRecord.status == "done")
        )
    ).all()

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    buckets: dict[str, list[CallRecord]] = {}

    for r in rows:
        ts = r.call_start_utc or r.processed_at
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < cutoff:
            continue
        day = ts.date().isoformat()
        buckets.setdefault(day, []).append(r)

    result = []
    for day in sorted(buckets):
        day_rows = buckets[day]
        scores = [r.attention_score for r in day_rows if r.attention_score is not None]
        resolved = sum(1 for r in day_rows if r.outcome == "RESOLVED")
        result.append(
            {
                "date": day,
                "call_count": len(day_rows),
                "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
                "resolution_rate": round(resolved / len(day_rows), 3),
            }
        )

    return result


# ---------------------------------------------------------------------------
# Per-call endpoints
# ---------------------------------------------------------------------------


@router.get("/{call_id}", response_model=AnalysisResponse)
async def get_call(
    call_id: str,
    db: AsyncSession = Depends(get_session),
) -> AnalysisResponse:
    """Return the full analysis for a single call.

    Uses an LRU cache to avoid re-deserialising the JSON blob on every
    request for the same call.

    Args:
        call_id: The call identifier.
        db: Injected async database session.

    Returns:
        AnalysisResponse with full analysis dict or None if not yet done.
    """
    record = await _get_record_or_404(db, call_id)

    analysis: dict[str, Any] | None = None
    if record.analysis_json:
        cached = analysis_cache.get(call_id)
        if cached is not None:
            analysis = cached
        else:
            analysis = json.loads(record.analysis_json)
            analysis_cache.set(call_id, analysis)

    import json as _json
    topics_list: list[str] = []
    if record.topics_json:
        try:
            topics_list = _json.loads(record.topics_json)
        except (ValueError, TypeError):
            pass
    moment_types_list: list[str] = []
    if record.moment_types_json:
        try:
            moment_types_list = _json.loads(record.moment_types_json)
        except (ValueError, TypeError):
            pass

    return AnalysisResponse(
        call_id=call_id,
        status=record.status,
        session=record.session,
        agent_name=record.agent_name,
        customer_name=record.customer_name,
        duration_seconds=record.duration_seconds,
        risk_level=record.risk_level,
        outcome=record.outcome,
        attention_score=record.attention_score,
        qa_score=record.qa_score,
        resolved=record.outcome == "RESOLVED" if record.outcome else None,
        intent=record.intent,
        topics=topics_list,
        moment_types=moment_types_list,
        mood_start=record.mood_start,
        mood_end=record.mood_end,
        top_moment_type=record.top_moment_type,
        call_start_utc=record.call_start_utc.isoformat() if record.call_start_utc else None,
        label_caller_mos=record.label_caller_mos,
        label_agent_mos=record.label_agent_mos,
        created_at=record.created_at.isoformat() if record.created_at else None,
        processed_at=record.processed_at.isoformat() if record.processed_at else None,
        analysis=analysis,
    )


@router.get("/{call_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    call_id: str,
    db: AsyncSession = Depends(get_session),
) -> TranscriptResponse:
    """Return the turn-by-turn transcript for a call.

    Args:
        call_id: The call identifier.
        db: Injected async database session.

    Returns:
        TranscriptResponse with all turns.

    Raises:
        HTTPException: 404 if call not found, 422 if not yet processed.
    """
    record = await _get_record_or_404(db, call_id)
    if not record.analysis_json:
        raise HTTPException(
            status_code=422,
            detail=f"call_id={call_id!r} has not been processed yet (status={record.status})",
        )

    data = json.loads(record.analysis_json)
    raw_turns = data.get("conversation", {}).get("turns", [])

    # Build turn_id → [moment_id, ...] from moments' evidence_turn_ids
    turn_to_moments: dict[int, list[int]] = {}
    for m in data.get("moments", []):
        m_id = m.get("id", 0)
        for tid in m.get("evidence_turn_ids", []):
            turn_to_moments.setdefault(int(tid), []).append(m_id)

    turns = [
        TurnResponse(
            id=t.get("id", i),
            speaker=t.get("speaker", ""),
            text=t.get("text", ""),
            start_time=float(t.get("start_time", 0.0)),
            end_time=float(t.get("end_time", 0.0)),
            sentiment_score=t.get("sentiment_score"),
            moment_ids=turn_to_moments.get(t.get("id", i), []),
        )
        for i, t in enumerate(raw_turns)
    ]

    return TranscriptResponse(
        call_id=call_id,
        total_turns=len(turns),
        turns=turns,
    )


@router.get("/{call_id}/moments", response_model=MomentListResponse)
async def get_moments(
    call_id: str,
    severity: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> MomentListResponse:
    """Return all detected moments for a call.

    Args:
        call_id: The call identifier.
        severity: Optional filter (LOW/MEDIUM/HIGH/CRITICAL).
        db: Injected async database session.

    Returns:
        MomentListResponse with filtered or all moments.
    """
    await _get_record_or_404(db, call_id)

    stmt = (
        select(MomentRecord)
        .where(MomentRecord.call_id == call_id)
        .order_by(MomentRecord.start_time)
    )
    if severity:
        stmt = stmt.where(MomentRecord.severity == severity)

    rows = (await db.scalars(stmt)).all()

    moments = [
        MomentResponse(
            moment_id=r.moment_id,
            call_id=r.call_id,
            moment_type=r.moment_type,
            severity=r.severity,
            start_time=r.start_time,
            trigger_phrase=r.trigger_phrase,
            description=r.description,
            confidence=r.confidence,
        )
        for r in rows
    ]

    return MomentListResponse(call_id=call_id, total=len(moments), moments=moments)


@router.get("/{call_id}/evidence", response_model=EvidenceListResponse)
async def get_evidence(
    call_id: str,
    db: AsyncSession = Depends(get_session),
) -> EvidenceListResponse:
    """Return all evidence items for a call.

    Args:
        call_id: The call identifier.
        db: Injected async database session.

    Returns:
        EvidenceListResponse with all evidence items.

    Raises:
        HTTPException: 422 if call not yet processed.
    """
    record = await _get_record_or_404(db, call_id)
    if not record.analysis_json:
        raise HTTPException(
            status_code=422,
            detail=f"call_id={call_id!r} has not been processed yet (status={record.status})",
        )

    data = json.loads(record.analysis_json)
    raw_evidence = data.get("evidence", [])

    items = [
        EvidenceItemResponse(
            turn_id=e.get("turn_id", 0),
            speaker=e.get("speaker", ""),
            quote=e.get("quote", ""),
            strength=str(e.get("strength", "")),
            claim=e.get("claim"),
            timestamp=e.get("timestamp"),
            confidence=e.get("confidence"),
            moment_id=e.get("moment_id"),
            reasoning=e.get("reasoning"),
        )
        for e in raw_evidence
    ]

    return EvidenceListResponse(call_id=call_id, total=len(items), evidence=items)


# ---------------------------------------------------------------------------
# Reprocess
# ---------------------------------------------------------------------------


@router.get("/{call_id}/audio")
async def get_audio(
    call_id: str,
    db: AsyncSession = Depends(get_session),
) -> Any:
    """Return a presigned S3 URL for the call's audio file.

    The client should redirect to this URL to stream the MP3. The presigned URL
    is valid for 1 hour. Falls back to local disk if mp3_path is an absolute path
    (legacy / local dev without S3).

    Args:
        call_id: The call identifier.
        db: Injected async database session.

    Returns:
        JSON with `url` key pointing to the audio stream.

    Raises:
        HTTPException: 404 if call not found or audio unavailable.
    """
    from fastapi.responses import FileResponse, RedirectResponse

    record = await _get_record_or_404(db, call_id)
    stored_path = record.mp3_path or ""

    # S3 key (relative, e.g. "audio/xxxxx.mp3")
    if stored_path and not Path(stored_path).is_absolute():
        try:
            from backend.s3 import presigned_url
            url = presigned_url(stored_path)
            return RedirectResponse(url=url, status_code=302)
        except Exception as exc:
            logger.warning("get_audio: presigned URL failed for %s: %s", call_id, exc)
            raise HTTPException(status_code=404, detail="Audio unavailable")

    # Legacy: absolute local path (local dev without S3)
    mp3_path = Path(stored_path)
    if not mp3_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found on disk")
    return FileResponse(
        str(mp3_path),
        media_type="audio/mpeg",
        headers={"Accept-Ranges": "bytes"},
        filename=f"{call_id}.mp3",
    )


@router.post("/{call_id}/reprocess", response_model=CallStatusResponse, status_code=202)
async def reprocess_call(
    call_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
) -> CallStatusResponse:
    """Wipe the existing analysis and re-run the pipeline for a call.

    Only allowed when the current status is 'done' or 'failed'.

    Args:
        call_id: The call identifier.
        background_tasks: FastAPI background task registry.
        db: Injected async database session.

    Returns:
        CallStatusResponse with status='pending'.
    """
    record = await _get_record_or_404(db, call_id)

    if record.status in ("pending", "processing"):
        raise HTTPException(
            status_code=409,
            detail=f"call_id={call_id!r} is already {record.status}",
        )

    # Clear existing results
    await db.execute(
        update(CallRecord)
        .where(CallRecord.call_id == call_id)
        .values(
            status="pending",
            error_message=None,
            analysis_json=None,
            risk_level=None,
            outcome=None,
            attention_score=None,
            qa_score=None,
            resolved=None,
            intent=None,
            summary=None,
            topics_json=None,
            moment_types_json=None,
            mood_start=None,
            mood_end=None,
            top_moment_type=None,
            processed_at=None,
        )
    )
    from sqlalchemy import delete
    from backend.db import MomentRecord as _MR
    await db.execute(delete(_MR).where(_MR.call_id == call_id))
    await db.commit()
    analysis_cache.delete(call_id)

    background_tasks.add_task(_run_pipeline, call_id, record.mp3_path, None)
    logger.info("Reprocessing call_id=%s", call_id)

    return CallStatusResponse(call_id=call_id, status="pending", created_at=record.created_at)
