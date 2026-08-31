"""
Decision engine.

Converts Claude's semantic scores into a DecisionResult and computes the
call outcome (ESCALATED / RESOLVED / UNRESOLVED) deterministically from
the detected moments.

Claude computes attention_score, qa_score, and risk_level — this engine
acts as a thin formatter and outcome resolver.
"""

from __future__ import annotations

import logging

from pipeline.models import (
    AttentionScore,
    DecisionResult,
    Moment,
    MomentType,
    ScoreComponent,
    SemanticResult,
)

logger = logging.getLogger(__name__)


def _compute_outcome(
    moments: list[Moment],
    resolved: bool = False,
) -> str:
    """Determine the call outcome label.

    Precedence: ESCALATED > RESOLVED > UNRESOLVED.

    Args:
        moments: All detected Moments.
        resolved: Effective resolved flag from the semantic engine.

    Returns:
        Outcome string: "ESCALATED" | "RESOLVED" | "UNRESOLVED".
    """
    moment_types = {m.type for m in moments}

    if MomentType.ESCALATION_REQUEST in moment_types:
        return "ESCALATED"
    if resolved:
        return "RESOLVED"
    return "UNRESOLVED"


def score(
    moments: list[Moment],
    semantic: SemanticResult,
    resolved: bool | None = None,
) -> DecisionResult:
    """Build a DecisionResult from Claude's semantic scores.

    Claude computed attention_score, qa_score, and risk_level from the
    transcript and post-call metadata. This function formats them into the
    DecisionResult structure and adds the deterministic outcome label.

    Args:
        moments: All Moments detected by the moment engine.
        semantic: Semantic engine output (carries Claude's scores).
        resolved: Effective resolved flag from the semantic engine.

    Returns:
        DecisionResult with attention_score, qa_score, risk_level, outcome.
    """
    effective_resolved = resolved if resolved is not None else bool(semantic.resolved)

    # Use Claude's scores directly — clamp to valid range as a safety net
    attention_total = max(0, min(semantic.attention_score, 100))
    qa = max(0, min(semantic.qa_score, 100))

    risk = (
        semantic.risk_level
        if semantic.risk_level in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        else "LOW"
    )
    outcome = _compute_outcome(moments, resolved=effective_resolved)

    # Wrap the score with Claude's reasoning for the frontend breakdown panel
    attention = AttentionScore(
        total=attention_total,
        components=[
            ScoreComponent(
                label=semantic.attention_reasoning or "llm assessment",
                points=attention_total,
                moment_id=0,
            )
        ],
    )

    logger.info(
        "Decision: attention=%d qa=%d risk=%s outcome=%s",
        attention_total,
        qa,
        risk,
        outcome,
    )

    return DecisionResult(
        attention_score=attention,
        qa_score=qa,
        risk_level=risk,
        outcome=outcome,
    )
