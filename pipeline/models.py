"""
CallRadar pipeline data models.

All Pydantic models used as data contracts between pipeline engines.
Every engine reads from and writes to these models.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class MomentType(str, Enum):
    COMPLAINT = "COMPLAINT"
    ESCALATION_REQUEST = "ESCALATION_REQUEST"
    MANAGER_REQUEST = "MANAGER_REQUEST"
    REPEAT_CONTACT = "REPEAT_CONTACT"
    MOOD_SHIFT = "MOOD_SHIFT"
    LONG_SILENCE = "LONG_SILENCE"
    OVERTALK = "OVERTALK"
    APOLOGY = "APOLOGY"
    RESOLUTION_ATTEMPT = "RESOLUTION_ATTEMPT"
    UNRESOLVED = "UNRESOLVED"
    FRAUD_SIGNAL = "FRAUD_SIGNAL"
    COMPLIANCE_BREACH = "COMPLIANCE_BREACH"
    POSITIVE_FEEDBACK = "POSITIVE_FEEDBACK"
    HOLD_PLACED = "HOLD_PLACED"


class MomentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceStrength(str, Enum):
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"


# ---------------------------------------------------------------------------
# Audio / Transcription primitives
# ---------------------------------------------------------------------------


class SilenceSegment(BaseModel):
    """A period where neither channel has speech."""

    model_config = ConfigDict(frozen=False)

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


class OvertalkSegment(BaseModel):
    """A period where both channels are simultaneously active."""

    model_config = ConfigDict(frozen=False)

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


# ---------------------------------------------------------------------------
# Conversation primitives
# ---------------------------------------------------------------------------


class Turn(BaseModel):
    """A single speaker turn in the conversation."""

    model_config = ConfigDict(frozen=False)

    id: int
    call_id: str
    speaker: str  # "agent" | "customer"
    start_time: float
    end_time: float
    text: str
    word_count: int
    sentiment_score: float | None = None  # -1 to +1; set by behavioral engine


class Entity(BaseModel):
    """A named entity extracted from a turn."""

    model_config = ConfigDict(frozen=False)

    text: str
    label: str
    start_char: int
    end_char: int
    turn_id: int


class Participant(BaseModel):
    """Aggregate stats for one participant in the call."""

    model_config = ConfigDict(frozen=False)

    name: str
    role: str  # "agent" | "customer"
    talk_time_seconds: float
    turn_count: int


class ConversationModel(BaseModel):
    """Complete structured representation of a call."""

    model_config = ConfigDict(frozen=False)

    call_id: str
    turns: list[Turn] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    participants: list[Participant] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    duration_seconds: float
    silence_segments: list[SilenceSegment] = Field(default_factory=list)
    overtalk_segments: list[OvertalkSegment] = Field(default_factory=list)
    deepgram_summary: str = ""
    deepgram_intent: str = ""
    deepgram_topics: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Moment detection
# ---------------------------------------------------------------------------


class Moment(BaseModel):
    """A detected event or pattern of interest within the call."""

    model_config = ConfigDict(frozen=False)

    id: int
    type: MomentType
    start_time: float
    end_time: float
    speaker: str  # "agent" | "customer" | "both"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_turn_ids: list[int] = Field(default_factory=list)
    trigger_phrase: str = ""
    severity: MomentSeverity
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    """A piece of evidence linking a transcript quote to a claim."""

    model_config = ConfigDict(frozen=False)

    claim: str
    turn_id: int
    timestamp: float
    speaker: str
    quote: str  # always verbatim from transcript; never Claude-generated
    strength: EvidenceStrength
    confidence: float = Field(ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class ScoreComponent(BaseModel):
    """One contributing factor to an attention or QA score."""

    model_config = ConfigDict(frozen=False)

    label: str
    points: int
    moment_id: int


class AttentionScore(BaseModel):
    """Composite attention / priority score for a call (0–100)."""

    model_config = ConfigDict(frozen=False)

    total: int = Field(ge=0, le=100)
    components: list[ScoreComponent] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Intermediate engine output containers
# ---------------------------------------------------------------------------


class BehavioralResult(BaseModel):
    """Output of the behavioral engine."""

    model_config = ConfigDict(frozen=False)

    mood_trajectory: list[dict[str, Any]] = Field(default_factory=list)
    mood_start: float | None = None
    mood_end: float | None = None
    mood_shift_turn_id: int | None = None
    mood_shift_time: float | None = None
    mood_shift_quote: str | None = None
    mood_shift_magnitude: float = 0.0


class DetectedMoment(BaseModel):
    """A moment detected by the Claude semantic engine."""

    model_config = ConfigDict(frozen=False)

    type: str  # MomentType value string
    turn_id: int | None = None
    start_time: float = 0.0
    severity: str = "LOW"
    speaker: str = "both"
    description: str = ""


class SemanticResult(BaseModel):
    """Output of the semantic (Claude) engine.

    Claude reads the full transcript and post-call metadata to detect
    moments contextually and compute attention/QA scores.
    """

    model_config = ConfigDict(frozen=False)

    # Narrative fields
    intent: str = ""
    summary: str = ""
    semantic_topics: list[str] = Field(default_factory=list)

    # Name extraction
    customer_name_mentioned: bool = False
    customer_name: str = ""
    agent_name: str = ""

    # Resolution
    resolved: bool | None = None  # None = not determined (USE_CLAUDE_SEMANTIC=False)

    # Business signals (used for backfill and cross-checks)
    identity_verified: bool = False
    reference_number_given: bool = False
    escalation_detected: bool = False
    repeat_contact: bool = False
    fraud_signals: list[str] = Field(default_factory=list)

    # Claude-detected moments (replaces phrase-list matching)
    detected_moments: list[DetectedMoment] = Field(default_factory=list)

    # Scoring — computed by Claude using transcript + post-call metadata
    attention_score: int = 0
    attention_reasoning: str = ""
    qa_score: int = 100
    qa_reasoning: str = ""
    risk_level: str = "LOW"


class DecisionResult(BaseModel):
    """Output of the deterministic decision / scoring engine."""

    model_config = ConfigDict(frozen=False)

    attention_score: AttentionScore
    qa_score: int = Field(ge=0, le=100)
    risk_level: str
    outcome: str


# ---------------------------------------------------------------------------
# Final output
# ---------------------------------------------------------------------------


class CallAnalysis(BaseModel):
    """Complete analysis output for a single call."""

    model_config = ConfigDict(frozen=False)

    call_id: str
    conversation: ConversationModel
    moments: list[Moment] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    attention_score: AttentionScore
    qa_score: int = Field(ge=0, le=100)
    risk_level: str
    outcome: str
    mood_trajectory: list[dict[str, Any]] = Field(default_factory=list)
    mood_shift_time: float | None = None       # timestamp (seconds) of largest sentiment drop
    mood_shift_magnitude: float = 0.0          # size of the drop on [-1, +1] scale
    mood_shift_quote: str | None = None        # verbatim turn text where the shift occurred
    summary: str = ""
    intent: str = ""
    resolved: bool = False
    processing_time_seconds: float = 0.0
