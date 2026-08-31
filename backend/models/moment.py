"""
Pydantic response models for moment endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class MomentResponse(BaseModel):
    """A single detected moment within a call."""

    model_config = ConfigDict(frozen=False)

    moment_id: int
    call_id: str
    moment_type: str
    severity: str
    start_time: float
    trigger_phrase: str
    description: str | None = None
    confidence: float | None = None


class MomentListResponse(BaseModel):
    """All moments for a single call."""

    model_config = ConfigDict(frozen=False)

    call_id: str
    total: int
    moments: list[MomentResponse]


class MomentTypeStats(BaseModel):
    """Count of moments grouped by type across all calls."""

    model_config = ConfigDict(frozen=False)

    moment_type: str
    count: int
