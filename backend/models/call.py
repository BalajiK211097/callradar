"""
Pydantic request/response models for the /calls routes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SubmitCallRequest(BaseModel):
    """Body for POST /calls/submit."""

    model_config = ConfigDict(frozen=False)

    call_id: str | None = None  # derived from mp3 filename if omitted
    mp3_path: str
    agent_name: str | None = None
    customer_name: str | None = None
    metadata: dict[str, Any] | None = None


class BatchSubmitRequest(BaseModel):
    """Body for POST /calls/batch — submit many calls in one request."""

    model_config = ConfigDict(frozen=False)

    calls: list[SubmitCallRequest]


class CallStatusResponse(BaseModel):
    """Minimal response returned immediately after call submission."""

    model_config = ConfigDict(frozen=False)

    call_id: str
    status: str
    error_message: str | None = None
    created_at: datetime | None = None
    processed_at: datetime | None = None


class CallSummary(BaseModel):
    """Row-level summary for list endpoints."""

    model_config = ConfigDict(frozen=False)

    call_id: str
    status: str
    session: str | None = None
    agent_name: str | None = None
    customer_name: str | None = None
    duration_seconds: float | None = None
    risk_level: str | None = None
    outcome: str | None = None
    attention_score: int | None = None
    qa_score: int | None = None
    resolved: bool | None = None
    intent: str | None = None
    topics: list[str] = []
    moment_types: list[str] = []
    mood_start: float | None = None
    mood_end: float | None = None
    top_moment_type: str | None = None
    call_start_utc: datetime | None = None
    label_caller_mos: float | None = None
    label_agent_mos: float | None = None
    created_at: datetime | None = None
    processed_at: datetime | None = None


class CallListResponse(BaseModel):
    """Paginated list of call summaries."""

    model_config = ConfigDict(frozen=False)

    total: int
    page: int
    page_size: int
    items: list[CallSummary]
