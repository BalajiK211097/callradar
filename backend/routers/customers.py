"""
/customers router — call history and profiles per customer.

Endpoints
---------
GET  /customers/{customer_name}/calls     Paginated call list for one customer
GET  /customers/{customer_name}/profile   Aggregated customer profile
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import CallRecord, get_session
from backend.models.call import CallListResponse
from backend.routers.calls import _record_to_summary

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[dict[str, Any]])
async def list_customers(
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return all distinct customers seen in completed calls with summary stats.

    Args:
        db: Injected async database session.

    Returns:
        List of dicts with customer_name, total_calls, resolved_count,
        last_call_at, risk_level (most recent), avg_score.
    """
    rows = (
        await db.scalars(
            select(CallRecord)
            .where(CallRecord.customer_name.is_not(None))
            .where(CallRecord.status == "done")
            .order_by(CallRecord.created_at.desc())
        )
    ).all()

    grouped: dict[str, list[CallRecord]] = {}
    for r in rows:
        grouped.setdefault(r.customer_name, []).append(r)  # type: ignore[index]

    result = []
    for customer_name, calls in sorted(grouped.items()):
        resolved = sum(1 for c in calls if c.outcome == "RESOLVED")
        scores = [c.attention_score for c in calls if c.attention_score is not None]
        most_recent = calls[0]  # already ordered by created_at desc
        result.append(
            {
                "customer_name": customer_name,
                "total_calls": len(calls),
                "resolved_count": resolved,
                "resolution_rate": round(resolved / len(calls), 3),
                "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
                "risk_level": most_recent.risk_level,
                "last_call_at": most_recent.call_start_utc.isoformat() if most_recent.call_start_utc else (most_recent.created_at.isoformat() if most_recent.created_at else None),
            }
        )

    return result


@router.get("/{customer_name}/calls", response_model=CallListResponse)
async def get_customer_calls(
    customer_name: str,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_session),
) -> CallListResponse:
    """Return all calls associated with a specific customer.

    Args:
        customer_name: The customer's name (exact match).
        page: 1-indexed page number.
        page_size: Rows per page (max 200).
        db: Injected async database session.

    Returns:
        CallListResponse with matching calls ordered by date.

    Raises:
        HTTPException: 404 if no calls are found for this customer.
    """
    page_size = min(page_size, 200)

    total = (
        await db.scalar(
            select(func.count())
            .select_from(CallRecord)
            .where(CallRecord.customer_name == customer_name)
        )
    ) or 0

    if total == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No calls found for customer={customer_name!r}",
        )

    offset = (page - 1) * page_size
    rows = (
        await db.scalars(
            select(CallRecord)
            .where(CallRecord.customer_name == customer_name)
            .order_by(CallRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).all()

    return CallListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_record_to_summary(r) for r in rows],
    )


@router.get("/{customer_name}/profile", response_model=dict[str, Any])
async def get_customer_profile(
    customer_name: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return an aggregated profile for a customer across all their calls.

    Includes call history summary, most frequent intents, detected
    entities (e.g. account numbers, complaint references), mood trend,
    and risk history.

    Args:
        customer_name: The customer's name (exact match).
        db: Injected async database session.

    Returns:
        Dict with profile data and call history summary.

    Raises:
        HTTPException: 404 if no completed calls exist for this customer.
    """
    rows = (
        await db.scalars(
            select(CallRecord)
            .where(CallRecord.customer_name == customer_name)
            .where(CallRecord.status == "done")
            .order_by(CallRecord.created_at.desc())
        )
    ).all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No completed calls found for customer={customer_name!r}",
        )

    # Aggregate intents
    intent_counts: dict[str, int] = {}
    all_topics: list[str] = []
    entities_seen: dict[str, list[str]] = {}
    risk_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {}
    mood_scores: list[float] = []

    for r in rows:
        if r.intent:
            intent_counts[r.intent] = intent_counts.get(r.intent, 0) + 1
        if r.topics_json:
            try:
                all_topics.extend(json.loads(r.topics_json))
            except json.JSONDecodeError:
                pass
        if r.risk_level:
            risk_counts[r.risk_level] = risk_counts.get(r.risk_level, 0) + 1
        if r.outcome:
            outcome_counts[r.outcome] = outcome_counts.get(r.outcome, 0) + 1

        # Extract entities and mood from analysis JSON
        if r.analysis_json:
            try:
                data = json.loads(r.analysis_json)
                # Entities from conversation model
                for entity in data.get("conversation", {}).get("entities", []):
                    label = entity.get("label", "")
                    text = entity.get("text", "")
                    if label and text:
                        entities_seen.setdefault(label, [])
                        if text not in entities_seen[label]:
                            entities_seen[label].append(text)
                # Final mood score from trajectory
                traj = data.get("mood_trajectory", [])
                if traj:
                    last = traj[-1]
                    score = last.get("score", last) if isinstance(last, dict) else last
                    mood_scores.append(float(score))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    # Deduplicate topics
    topic_counts: dict[str, int] = {}
    for t in all_topics:
        topic_counts[t] = topic_counts.get(t, 0) + 1
    top_topics = sorted(topic_counts, key=lambda k: -topic_counts[k])[:5]

    # Most frequent intent
    top_intent = max(intent_counts, key=lambda k: intent_counts[k]) if intent_counts else None

    avg_mood = round(sum(mood_scores) / len(mood_scores), 3) if mood_scores else None

    return {
        "customer_name": customer_name,
        "total_calls": len(rows),
        "top_intent": top_intent,
        "intent_breakdown": intent_counts,
        "top_topics": top_topics,
        "risk_breakdown": risk_counts,
        "outcome_breakdown": outcome_counts,
        "avg_final_mood_score": avg_mood,
        "entities_seen": entities_seen,
        "recent_calls": [
            {
                "call_id": r.call_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "risk_level": r.risk_level,
                "outcome": r.outcome,
                "qa_score": r.qa_score,
            }
            for r in rows[:10]
        ],
    }
