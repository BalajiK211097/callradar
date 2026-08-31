"""
Pydantic response models for transcript endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TurnResponse(BaseModel):
    """A single speaker turn in the call transcript."""

    model_config = ConfigDict(frozen=False)

    id: int
    speaker: str
    text: str
    start_time: float
    end_time: float
    sentiment_score: float | None = None
    moment_ids: list[int] = []  # moment IDs whose evidence_turn_ids include this turn


class TranscriptResponse(BaseModel):
    """Full turn-by-turn transcript for a call."""

    model_config = ConfigDict(frozen=False)

    call_id: str
    total_turns: int
    turns: list[TurnResponse]


class EvidenceItemResponse(BaseModel):
    """A single evidence item extracted from the transcript."""

    model_config = ConfigDict(frozen=False)

    turn_id: int
    speaker: str
    quote: str
    strength: str
    claim: str | None = None
    timestamp: float | None = None
    confidence: float | None = None
    moment_id: int | None = None
    reasoning: str | None = None


class EvidenceListResponse(BaseModel):
    """All evidence items for a call."""

    model_config = ConfigDict(frozen=False)

    call_id: str
    total: int
    evidence: list[EvidenceItemResponse]
