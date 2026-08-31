"""
Moment detection engine.

Pure Python. Converts Claude's contextually-detected moments into typed Moment
objects, then appends deterministic physical signals (mood shift, silence,
overtalk) derived from the behavioral engine and conversation model.

No phrase lists. No keyword matching.
"""

from __future__ import annotations

import logging

from pipeline import config
from pipeline.models import (
    BehavioralResult,
    ConversationModel,
    DetectedMoment,
    Moment,
    MomentSeverity,
    MomentType,
    SemanticResult,
)

logger = logging.getLogger(__name__)

# Valid MomentType values that Claude is allowed to emit
_VALID_TYPES: frozenset[str] = frozenset(t.value for t in MomentType)

_SEVERITY_MAP: dict[str, MomentSeverity] = {
    "LOW": MomentSeverity.LOW,
    "MEDIUM": MomentSeverity.MEDIUM,
    "HIGH": MomentSeverity.HIGH,
    "CRITICAL": MomentSeverity.CRITICAL,
}


def _resolve_severity(raw: str) -> MomentSeverity:
    """Safely convert a severity string to MomentSeverity enum."""
    return _SEVERITY_MAP.get(str(raw).upper(), MomentSeverity.LOW)


def _resolve_start_time(
    dm: DetectedMoment,
    turn_map: dict[int, float],
) -> float:
    """Return the best available start time for a detected moment.

    Uses the turn's actual start_time when a valid turn_id is present,
    otherwise falls back to the start_time Claude reported.

    Args:
        dm: The DetectedMoment from the semantic engine.
        turn_map: Mapping from turn_id → start_time.

    Returns:
        Start time in seconds.
    """
    if dm.turn_id is not None and dm.turn_id in turn_map:
        return turn_map[dm.turn_id]
    return dm.start_time


def detect(
    conversation: ConversationModel,
    behavioral: BehavioralResult,
    semantic: SemanticResult,
) -> list[Moment]:
    """Detect all moment types present in a call.

    Claude's detected_moments provide the primary content-based signals.
    Deterministic physical signals (mood shift, silence, overtalk) are
    appended from the behavioral engine and conversation model.

    Args:
        conversation: Fully populated ConversationModel with turns.
        behavioral: Output from the behavioral intelligence engine.
        semantic: Output from the semantic engine (contains detected_moments).

    Returns:
        List of Moment objects sorted by start_time.

    Raises:
        ValueError: If conversation contains no turns.
    """
    if not conversation.turns:
        raise ValueError(
            f"call_id={conversation.call_id}: cannot detect moments without turns"
        )

    # Build a fast lookup: turn_id → start_time
    turn_map: dict[int, float] = {t.id: t.start_time for t in conversation.turns}
    turn_end_map: dict[int, float] = {t.id: t.end_time for t in conversation.turns}

    moments: list[Moment] = []
    moment_id = 0

    def _add(moment: Moment) -> None:
        nonlocal moment_id
        moment.id = moment_id
        moments.append(moment)
        moment_id += 1

    # ------------------------------------------------------------------
    # Claude-detected moments (content-based, no phrase matching)
    # ------------------------------------------------------------------
    for dm in semantic.detected_moments:
        if dm.type not in _VALID_TYPES:
            logger.warning(
                "call_id=%s: semantic engine returned unknown moment type %r — skipping",
                conversation.call_id,
                dm.type,
            )
            continue

        start = _resolve_start_time(dm, turn_map)
        end = turn_end_map.get(dm.turn_id, start) if dm.turn_id is not None else start
        evidence_ids = [dm.turn_id] if dm.turn_id is not None else []

        _add(Moment(
            id=0,
            type=MomentType(dm.type),
            start_time=start,
            end_time=end,
            speaker=dm.speaker,
            confidence=0.9,
            evidence_turn_ids=evidence_ids,
            trigger_phrase=dm.description,
            severity=_resolve_severity(dm.severity),
            metadata={"source": "deepseek"},
        ))

    # ------------------------------------------------------------------
    # MOOD_SHIFT — deterministic from Deepgram sentiment scores
    # (Claude cannot compute exact sentiment drop magnitudes)
    # ------------------------------------------------------------------
    if behavioral.mood_shift_turn_id is not None:
        magnitude = behavioral.mood_shift_magnitude
        if magnitude >= config.MOOD_SHIFT_CRITICAL_DROP:
            severity = MomentSeverity.CRITICAL
        elif magnitude >= config.MOOD_SHIFT_HIGH_DROP:
            severity = MomentSeverity.HIGH
        else:
            severity = MomentSeverity.MEDIUM

        shift_time = behavioral.mood_shift_time or 0.0
        _add(Moment(
            id=0,
            type=MomentType.MOOD_SHIFT,
            start_time=shift_time,
            end_time=shift_time,
            speaker="customer",
            confidence=0.8,
            evidence_turn_ids=[behavioral.mood_shift_turn_id],
            trigger_phrase=behavioral.mood_shift_quote or "",
            severity=severity,
            metadata={"magnitude": magnitude},
        ))

    # ------------------------------------------------------------------
    # LONG_SILENCE — deterministic from timestamp gaps in conversation model
    # ------------------------------------------------------------------
    for silence in conversation.silence_segments:
        if silence.duration >= config.SILENCE_ALERT_DURATION_S:
            _add(Moment(
                id=0,
                type=MomentType.LONG_SILENCE,
                start_time=silence.start,
                end_time=silence.end,
                speaker="both",
                confidence=1.0,
                evidence_turn_ids=[],
                trigger_phrase=f"silence {silence.duration:.1f}s",
                severity=MomentSeverity.MEDIUM,
                metadata={"duration_seconds": silence.duration},
            ))

    # ------------------------------------------------------------------
    # OVERTALK — deterministic from simultaneous speech detection
    # ------------------------------------------------------------------
    for overtalk in conversation.overtalk_segments:
        if overtalk.duration >= config.OVERTALK_ALERT_DURATION_S:
            _add(Moment(
                id=0,
                type=MomentType.OVERTALK,
                start_time=overtalk.start,
                end_time=overtalk.end,
                speaker="both",
                confidence=1.0,
                evidence_turn_ids=[],
                trigger_phrase=f"overtalk {overtalk.duration:.1f}s",
                severity=MomentSeverity.LOW,
                metadata={"duration_seconds": overtalk.duration},
            ))

    # Deduplicate: same type + same start_time bucket (0.5 s) → keep first occurrence
    seen_keys: set[tuple[str, int]] = set()
    deduped: list[Moment] = []
    for m in moments:
        key = (m.type.value, int(m.start_time * 2))  # 0.5-second buckets
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(m)
    moments = deduped

    # Sort by start_time and re-assign sequential IDs
    moments.sort(key=lambda m: m.start_time)
    for i, m in enumerate(moments):
        m.id = i

    logger.info(
        "call_id=%s: detected %d moments: %s",
        conversation.call_id,
        len(moments),
        [m.type.value for m in moments],
    )

    return moments
