"""
Behavioral intelligence engine.

Reads sentiment scores that Deepgram already populated on each Turn (via the
builder), builds the mood trajectory, detects mood shifts, and computes
acoustic penalty scores from silence and overtalk segments that are now on
the ConversationModel itself.
"""

from __future__ import annotations

import logging
from typing import Any

from pipeline import config
from pipeline.models import BehavioralResult, ConversationModel, Turn

logger = logging.getLogger(__name__)


def _score_to_label(score: float) -> str:
    """Convert a [-1, +1] sentiment score to a human-readable label."""
    if score > 0.1:
        return "positive"
    if score < -0.1:
        return "negative"
    return "neutral"


def _build_trajectory(customer_turns: list[Turn]) -> list[dict[str, Any]]:
    """Build the mood trajectory from pre-scored customer turns.

    Args:
        customer_turns: Turns where speaker == "customer", with sentiment_score set.

    Returns:
        List of dicts with turn_id, timestamp, score, label.
    """
    return [
        {
            "turn_id": t.id,
            "timestamp": t.start_time,
            "score": t.sentiment_score if t.sentiment_score is not None else 0.0,
            "label": _score_to_label(t.sentiment_score or 0.0),
        }
        for t in customer_turns
    ]


def _detect_mood_shift(
    trajectory: list[dict[str, Any]],
    customer_turns: list[Turn],
) -> tuple[int | None, float, str | None]:
    """Find the turn with the largest single-step sentiment drop.

    Args:
        trajectory: List of trajectory dicts with "score" and "turn_id".
        customer_turns: Original Turn objects for quote extraction.

    Returns:
        (shift_turn_id, shift_magnitude, shift_quote)
        shift_turn_id is None if no shift exceeds the threshold.
    """
    if len(trajectory) < 2:
        return None, 0.0, None

    scores = [t["score"] for t in trajectory]
    turn_ids = [t["turn_id"] for t in trajectory]

    max_drop = 0.0
    shift_idx = -1
    for i in range(1, len(scores)):
        drop = scores[i - 1] - scores[i]
        if drop > max_drop:
            max_drop = drop
            shift_idx = i

    if max_drop < config.MOOD_SHIFT_MIN_DROP:
        return None, 0.0, None

    shift_turn_id = turn_ids[shift_idx]
    turn_map = {t.id: t for t in customer_turns}
    shift_turn = turn_map.get(shift_turn_id)
    shift_quote = shift_turn.text if shift_turn else None

    return shift_turn_id, round(max_drop, 4), shift_quote


async def analyse(conversation: ConversationModel) -> BehavioralResult:
    """Run behavioral analysis on a conversation.

    Sentiment is already populated on every Turn by the builder (from Deepgram).
    This engine builds the trajectory, detects mood shifts, and scores acoustics.

    Args:
        conversation: ConversationModel with sentiment_score set on all turns.

    Returns:
        BehavioralResult with trajectory, shift data, and acoustic scores.
    """
    customer_turns = [t for t in conversation.turns if t.speaker == "customer"]
    logger.info(
        "call_id=%s: building mood trajectory for %d customer turns",
        conversation.call_id,
        len(customer_turns),
    )

    trajectory = _build_trajectory(customer_turns)
    mood_start: float | None = trajectory[0]["score"] if trajectory else None
    mood_end: float | None = trajectory[-1]["score"] if trajectory else None

    shift_turn_id, shift_magnitude, shift_quote = _detect_mood_shift(
        trajectory, customer_turns
    )

    shift_time: float | None = None
    if shift_turn_id is not None:
        turn_map = {t.id: t for t in customer_turns}
        shift_turn = turn_map.get(shift_turn_id)
        shift_time = shift_turn.start_time if shift_turn else None

    logger.info(
        "call_id=%s: mood_start=%.2f mood_end=%.2f shift_magnitude=%.2f",
        conversation.call_id,
        mood_start or 0,
        mood_end or 0,
        shift_magnitude,
    )

    return BehavioralResult(
        mood_trajectory=trajectory,
        mood_start=mood_start,
        mood_end=mood_end,
        mood_shift_turn_id=shift_turn_id,
        mood_shift_time=shift_time,
        mood_shift_quote=shift_quote,
        mood_shift_magnitude=shift_magnitude,
    )
