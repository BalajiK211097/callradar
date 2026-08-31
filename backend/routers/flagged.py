"""
/flagged router — high-priority calls requiring supervisor attention.

A call is considered flagged if its risk_level is CRITICAL or HIGH.
Results are sorted by attention_score descending so the most urgent
calls surface first.

Endpoints
---------
GET  /flagged         Paginated list of CRITICAL + HIGH calls
GET  /flagged/stats   Summary statistics for flagged calls
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import CallRecord, MomentRecord, get_session
from backend.models.call import CallListResponse
from backend.routers.calls import _record_to_summary

logger = logging.getLogger(__name__)

router = APIRouter()

_FLAGGED_LEVELS = ("CRITICAL", "HIGH")


@router.get("", response_model=CallListResponse)
async def list_flagged(
    page: int = 1,
    page_size: int = 50,
    risk_level: str | None = None,
    db: AsyncSession = Depends(get_session),
) -> CallListResponse:
    """Return all flagged calls (CRITICAL and HIGH risk), highest attention first.

    Args:
        page: 1-indexed page number.
        page_size: Rows per page (max 200).
        risk_level: Optional further filter to CRITICAL or HIGH only.
        db: Injected async database session.

    Returns:
        CallListResponse ordered by attention_score descending.
    """
    page_size = min(page_size, 200)

    levels = [risk_level] if risk_level in _FLAGGED_LEVELS else list(_FLAGGED_LEVELS)

    base = (
        select(CallRecord)
        .where(CallRecord.risk_level.in_(levels))
        .where(CallRecord.status == "done")
    )
    count_base = (
        select(func.count())
        .select_from(CallRecord)
        .where(CallRecord.risk_level.in_(levels))
        .where(CallRecord.status == "done")
    )

    total = (await db.scalar(count_base)) or 0
    offset = (page - 1) * page_size
    rows = (
        await db.scalars(
            base.order_by(CallRecord.attention_score.desc()).offset(offset).limit(page_size)
        )
    ).all()

    return CallListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[_record_to_summary(r) for r in rows],
    )


@router.get("/stats", response_model=dict[str, Any])
async def flagged_stats(
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return summary statistics specifically for flagged calls.

    Includes top moment types that triggered the flagging, average
    attention scores, and per-agent breakdown.

    Args:
        db: Injected async database session.

    Returns:
        Dict with counts, averages, top agents, and top moment types.
    """
    rows = (
        await db.scalars(
            select(CallRecord)
            .where(CallRecord.risk_level.in_(_FLAGGED_LEVELS))
            .where(CallRecord.status == "done")
        )
    ).all()

    total = len(rows)
    critical_count = sum(1 for r in rows if r.risk_level == "CRITICAL")
    high_count = sum(1 for r in rows if r.risk_level == "HIGH")

    att_scores = [r.attention_score for r in rows if r.attention_score is not None]
    avg_att = round(sum(att_scores) / len(att_scores), 1) if att_scores else None

    # Per-agent breakdown
    agent_counts: dict[str, int] = {}
    for r in rows:
        if r.agent_name:
            agent_counts[r.agent_name] = agent_counts.get(r.agent_name, 0) + 1
    top_agents = sorted(agent_counts.items(), key=lambda kv: -kv[1])[:10]

    # Top moment types in flagged calls
    call_ids = [r.call_id for r in rows]
    moment_type_counts: dict[str, int] = {}

    if call_ids:
        moment_rows = (
            await db.scalars(
                select(MomentRecord).where(MomentRecord.call_id.in_(call_ids))
            )
        ).all()
        for m in moment_rows:
            moment_type_counts[m.moment_type] = moment_type_counts.get(m.moment_type, 0) + 1

    top_moment_types = sorted(moment_type_counts.items(), key=lambda kv: -kv[1])[:10]

    # Unresolved within flagged
    unresolved = sum(1 for r in rows if r.outcome == "UNRESOLVED")
    escalated = sum(1 for r in rows if r.outcome == "ESCALATED")

    return {
        "total_flagged": total,
        "critical_count": critical_count,
        "high_count": high_count,
        "avg_attention_score": avg_att,
        "unresolved_count": unresolved,
        "escalated_count": escalated,
        "top_agents": [{"agent_name": a, "count": c} for a, c in top_agents],
        "top_moment_types": [{"type": t, "count": c} for t, c in top_moment_types],
    }
