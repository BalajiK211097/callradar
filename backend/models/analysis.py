"""
Pydantic response models for analysis and statistics endpoints.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class AnalysisResponse(BaseModel):
    """Full analysis for a single call, including scalar columns for fast access.

    The `analysis` field is the deserialised pipeline CallAnalysis dict.
    It is None while the call is still pending or processing.
    """

    model_config = ConfigDict(frozen=False)

    call_id: str
    status: str
    session: str | None = None
    agent_name: str | None = None
    customer_name: str | None = None
    duration_seconds: float | None = None
    risk_level: str | None = None
    outcome: str | None = None
    attention_score: float | None = None
    qa_score: float | None = None
    resolved: bool | None = None
    intent: str | None = None
    topics: list[str] = []
    moment_types: list[str] = []
    mood_start: float | None = None
    mood_end: float | None = None
    top_moment_type: str | None = None
    call_start_utc: str | None = None
    label_caller_mos: float | None = None
    label_agent_mos: float | None = None
    created_at: str | None = None
    processed_at: str | None = None
    analysis: dict[str, Any] | None = None


class StatsResponse(BaseModel):
    """Aggregate statistics across all calls in the database."""

    model_config = ConfigDict(frozen=False)

    total_calls: int
    done_calls: int
    failed_calls: int
    pending_calls: int
    processing_calls: int
    avg_qa_score: float | None = None
    avg_attention_score: float | None = None
    resolved_count: int = 0
    unresolved_count: int = 0
    escalated_count: int = 0
    risk_breakdown: dict[str, int] = {}
    outcome_breakdown: dict[str, int] = {}
