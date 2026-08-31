"""
Database layer — async SQLite via SQLAlchemy 2.0.

Provides the ORM models (CallRecord, MomentRecord), the async engine,
session factory, and the init_db() coroutine that creates tables on
first run.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    delete,
    func,
    select,
    update,
)

load_dotenv()
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=40,
)
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine, expire_on_commit=False
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


class CallRecord(Base):
    """Persisted record for every call submitted to the pipeline.

    Scalar columns mirror the top-level CallAnalysis fields so the
    calls list and flagged endpoints can filter without deserialising
    the full JSON blob.  The full analysis is kept in analysis_json.
    """

    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String, unique=True, nullable=False, index=True)
    mp3_path = Column(String, nullable=False)
    # pending → processing → done | failed
    status = Column(String, nullable=False, default="pending", index=True)
    error_message = Column(Text, nullable=True)

    # Extracted from analysis on completion
    agent_name = Column(String, nullable=True, index=True)
    customer_name = Column(String, nullable=True, index=True)
    duration_seconds = Column(Float, nullable=True)
    risk_level = Column(String, nullable=True, index=True)
    outcome = Column(String, nullable=True, index=True)
    attention_score = Column(Integer, nullable=True)
    qa_score = Column(Integer, nullable=True)
    resolved = Column(Boolean, nullable=True)
    intent = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    topics_json = Column(Text, nullable=True)  # JSON-encoded list[str]
    moment_types_json = Column(Text, nullable=True)  # JSON-encoded list[str] of all moment types
    mood_start = Column(Float, nullable=True)  # first score in mood_trajectory
    mood_end = Column(Float, nullable=True)    # last score in mood_trajectory
    top_moment_type = Column(String, nullable=True)  # highest-severity moment type

    # Full pipeline output
    analysis_json = Column(Text, nullable=True)

    # From companion metadata JSON
    session = Column(String, nullable=True, index=True)
    call_start_utc = Column(DateTime(timezone=True), nullable=True)
    agent_survey_ease = Column(String, nullable=True)
    agent_survey_rating = Column(String, nullable=True)
    caller_survey_ease = Column(String, nullable=True)
    caller_survey_rating = Column(String, nullable=True)
    label_caller_mos = Column(Float, nullable=True)
    label_agent_mos = Column(Float, nullable=True)
    label_lhvb_script = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)


class MomentRecord(Base):
    """Denormalised moment rows for fast per-type and per-severity queries."""

    __tablename__ = "moments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    call_id = Column(String, nullable=False, index=True)
    moment_id = Column(Integer, nullable=False)
    moment_type = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False, index=True)
    start_time = Column(Float, nullable=False)
    trigger_phrase = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)  # 0.0–1.0 confidence score


# ---------------------------------------------------------------------------
# Session dependency
# ---------------------------------------------------------------------------


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables if they do not already exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ---------------------------------------------------------------------------
# Write helpers (used by the background pipeline task)
# ---------------------------------------------------------------------------


async def save_analysis(
    db: AsyncSession,
    call_id: str,
    analysis_obj: object,
    raw_metadata: dict[str, Any] | None = None,
) -> None:
    """Persist a completed CallAnalysis to the database.

    Extracts scalar fields for fast filtering and stores the full
    analysis as JSON.  Also inserts one MomentRecord row per moment,
    and persists companion metadata fields (session, MOS scores, surveys)
    when raw_metadata is provided.

    Args:
        db: Active async database session.
        call_id: The call identifier.
        analysis_obj: A pipeline CallAnalysis Pydantic model instance.
        raw_metadata: Normalised metadata dict from pipeline.metadata.load().

    Raises:
        Exception: Re-raises any DB error after logging.
    """
    analysis_json: str = analysis_obj.model_dump_json()  # type: ignore[attr-defined]
    data: dict = json.loads(analysis_json)  # use JSON-serialised form so enums are plain strings

    conv = data.get("conversation", {})
    participants = conv.get("participants", {})

    def _name(role: str) -> str | None:
        if isinstance(participants, list):
            for p in participants:
                if isinstance(p, dict) and p.get("role") == role:
                    return p.get("name")
        elif isinstance(participants, dict):
            p = participants.get(role, {})
            return p.get("name") if isinstance(p, dict) else None
        return None

    topics = conv.get("topics", [])
    attention = data.get("attention_score", {})
    attention_total = attention.get("total") if isinstance(attention, dict) else None

    # Mood start/end from trajectory (list of {time, score, label} dicts)
    mood_traj = data.get("mood_trajectory") or []
    mood_start_val: float | None = None
    mood_end_val: float | None = None
    if mood_traj:
        try:
            mood_start_val = float(mood_traj[0].get("score", mood_traj[0]) if isinstance(mood_traj[0], dict) else mood_traj[0])
            mood_end_val = float(mood_traj[-1].get("score", mood_traj[-1]) if isinstance(mood_traj[-1], dict) else mood_traj[-1])
        except (TypeError, ValueError, KeyError):
            pass

    # Top moment type by severity rank
    _sev_rank = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    moments_data = data.get("moments") or []
    top_moment_type_val: str | None = None
    if moments_data:
        top_m = max(moments_data, key=lambda m: _sev_rank.get(str(m.get("severity", "")), 0))
        top_moment_type_val = str(top_m.get("type", "")) or None
    moment_types_list = list({str(m.get("type", "")) for m in moments_data if m.get("type")})

    # Extract metadata-derived fields
    meta = raw_metadata or {}
    labels = meta.get("labels", {}) or {}
    agent_survey = meta.get("agent_survey", {}) or {}
    caller_survey = meta.get("caller_survey", {}) or {}

    call_start_utc: datetime | None = None
    start_ms = meta.get("call_start_ms")
    if start_ms:
        try:
            call_start_utc = datetime.fromtimestamp(int(start_ms) / 1000, tz=timezone.utc)
        except (ValueError, OSError):
            pass

    await db.execute(
        update(CallRecord)
        .where(CallRecord.call_id == call_id)
        .values(
            status="done",
            agent_name=_name("agent"),
            customer_name=_name("customer"),
            duration_seconds=conv.get("duration_seconds"),
            risk_level=data.get("risk_level"),
            outcome=data.get("outcome"),
            attention_score=attention_total,
            qa_score=data.get("qa_score"),
            resolved=bool(data.get("resolved")),
            intent=data.get("intent"),
            summary=data.get("summary"),
            topics_json=json.dumps(topics),
            moment_types_json=json.dumps(moment_types_list),
            mood_start=mood_start_val,
            mood_end=mood_end_val,
            top_moment_type=top_moment_type_val,
            analysis_json=analysis_json,
            processed_at=func.now(),
            # Metadata fields
            session=meta.get("session"),
            call_start_utc=call_start_utc,
            agent_survey_ease=agent_survey.get("ease_of_connection"),
            agent_survey_rating=agent_survey.get("partner_rating"),
            caller_survey_ease=caller_survey.get("ease_of_connection"),
            caller_survey_rating=caller_survey.get("partner_rating"),
            label_caller_mos=labels.get("caller_mos"),
            label_agent_mos=labels.get("agent_mos"),
            label_lhvb_script=labels.get("lhvb_script"),
        )
    )

    # Remove any existing moment rows for this call before inserting fresh ones
    await db.execute(delete(MomentRecord).where(MomentRecord.call_id == call_id))

    # Denormalise moments
    for m in data.get("moments", []):
        raw_conf = m.get("confidence")
        db.add(
            MomentRecord(
                call_id=call_id,
                moment_id=m.get("id", 0),
                moment_type=str(m.get("type", "")),
                severity=str(m.get("severity", "")),
                start_time=float(m.get("start_time", 0.0)),
                trigger_phrase=m.get("trigger_phrase", ""),
                description=m.get("description"),
                confidence=float(raw_conf) if raw_conf is not None else None,
            )
        )

    await db.commit()


async def mark_failed(db: AsyncSession, call_id: str, error: str) -> None:
    """Set a call record to failed status with an error message.

    Args:
        db: Active async database session.
        call_id: The call identifier.
        error: Human-readable error description (truncated to 2000 chars).
    """
    await db.execute(
        update(CallRecord)
        .where(CallRecord.call_id == call_id)
        .values(status="failed", error_message=error[:2000])
    )
    await db.commit()
