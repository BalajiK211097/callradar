"""
/agents router — performance stats per agent.

Endpoints
---------
GET  /agents                       List all agents seen in processed calls
GET  /agents/{agent_name}/calls    Paginated call list for one agent
GET  /agents/{agent_name}/stats    Aggregate QA and risk stats for one agent
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import CallRecord, get_session
from backend.models.call import CallListResponse, CallSummary
from backend.routers.calls import _record_to_summary

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=list[dict[str, Any]])
async def list_agents(
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Return all distinct agent names seen in completed calls.

    Each entry includes the agent name and their aggregate QA score.

    Args:
        db: Injected async database session.

    Returns:
        List of dicts with agent_name, call_count, avg_qa_score,
        avg_attention_score.
    """
    rows = (
        await db.scalars(
            select(CallRecord)
            .where(CallRecord.agent_name.is_not(None))
            .where(CallRecord.status == "done")
        )
    ).all()

    grouped: dict[str, list[CallRecord]] = {}
    for r in rows:
        grouped.setdefault(r.agent_name, []).append(r)  # type: ignore[index]

    result = []
    for agent_name, calls in sorted(grouped.items()):
        qa_scores = [c.qa_score for c in calls if c.qa_score is not None]
        att_scores = [c.attention_score for c in calls if c.attention_score is not None]
        durations = [c.duration_seconds for c in calls if c.duration_seconds is not None]
        resolved = sum(1 for c in calls if c.outcome == "RESOLVED")
        result.append(
            {
                "agent_name": agent_name,
                "call_count": len(calls),
                "avg_qa_score": round(sum(qa_scores) / len(qa_scores), 1) if qa_scores else None,
                "avg_attention_score": round(sum(att_scores) / len(att_scores), 1) if att_scores else None,
                "resolution_rate": round(resolved / len(calls), 3),
                "avg_handle_time": round(sum(durations) / len(durations), 1) if durations else None,
            }
        )

    return result


@router.get("/{agent_name}/calls", response_model=CallListResponse)
async def get_agent_calls(
    agent_name: str,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_session),
) -> CallListResponse:
    """Return paginated calls handled by a specific agent.

    Args:
        agent_name: The agent's name (exact match).
        page: 1-indexed page number.
        page_size: Rows per page (max 200).
        db: Injected async database session.

    Returns:
        CallListResponse with matching calls.

    Raises:
        HTTPException: 404 if no calls are found for this agent.
    """
    page_size = min(page_size, 200)

    total = (
        await db.scalar(
            select(func.count())
            .select_from(CallRecord)
            .where(CallRecord.agent_name == agent_name)
        )
    ) or 0

    if total == 0:
        raise HTTPException(status_code=404, detail=f"No calls found for agent={agent_name!r}")

    offset = (page - 1) * page_size
    rows = (
        await db.scalars(
            select(CallRecord)
            .where(CallRecord.agent_name == agent_name)
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


@router.get("/{agent_name}/stats", response_model=dict[str, Any])
async def get_agent_stats(
    agent_name: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return aggregate performance statistics for one agent.

    Args:
        agent_name: The agent's name (exact match).
        db: Injected async database session.

    Returns:
        Dict with call_count, resolution_rate, avg_qa_score,
        avg_attention_score, risk_breakdown, outcome_breakdown.

    Raises:
        HTTPException: 404 if no completed calls exist for this agent.
    """
    rows = (
        await db.scalars(
            select(CallRecord)
            .where(CallRecord.agent_name == agent_name)
            .where(CallRecord.status == "done")
        )
    ).all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No completed calls found for agent={agent_name!r}",
        )

    qa_scores = [r.qa_score for r in rows if r.qa_score is not None]
    att_scores = [r.attention_score for r in rows if r.attention_score is not None]
    resolved = sum(1 for r in rows if r.outcome == "RESOLVED")

    risk_breakdown: dict[str, int] = {}
    outcome_breakdown: dict[str, int] = {}
    for r in rows:
        if r.risk_level:
            risk_breakdown[r.risk_level] = risk_breakdown.get(r.risk_level, 0) + 1
        if r.outcome:
            outcome_breakdown[r.outcome] = outcome_breakdown.get(r.outcome, 0) + 1

    return {
        "agent_name": agent_name,
        "call_count": len(rows),
        "resolution_rate": round(resolved / len(rows), 3) if rows else 0.0,
        "avg_qa_score": round(sum(qa_scores) / len(qa_scores), 1) if qa_scores else None,
        "avg_attention_score": round(sum(att_scores) / len(att_scores), 1) if att_scores else None,
        "risk_breakdown": risk_breakdown,
        "outcome_breakdown": outcome_breakdown,
    }
