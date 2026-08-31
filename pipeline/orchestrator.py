"""
Pipeline orchestrator.

Coordinates all pipeline stages for a single call.  The Deepgram ingest
stage (Stage 1) replaces the old split + transcribe + entity-extract steps,
reducing the total stage count from 8 to 6.

Stage map:
  1. Deepgram ingest  — transcription, sentiment, entities, topics, summary,
                        intent — ONE API call on the raw stereo MP3
  2. Conversation model — structures the Deepgram response into ConversationModel
  3a/3b. Semantic (Claude) + Behavioral — parallel
         Semantic gets post-call metadata (surveys, MOS) for grounded scoring
  4. Moment detection — Claude's detected moments + deterministic physical signals
  5. Evidence assembly  — two-stage Claude verification
  6. Decision scoring — thin formatter using Claude's scores
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from pipeline import metadata as meta_loader
from pipeline.audio_intelligence import deepgram_ingest
from pipeline.conversation_model import builder
from pipeline.engines import behavioral, decision, evidence, moment, semantic
from pipeline.models import CallAnalysis

logger = logging.getLogger(__name__)


async def process_call(
    call_id: str,
    mp3_path: str | Path,
    metadata: dict[str, Any] | None = None,
) -> CallAnalysis:
    """Run the full AI intelligence pipeline for a single call.

    Pipeline stages:
      1. Deepgram ingest — multichannel transcription + full intelligence (one API call)
      2. Conversation model — builds ConversationModel from DeepgramResult
      3a. Semantic engine — Claude Sonnet or Deepgram data (config toggle)
      3b. Behavioral engine — mood trajectory from pre-scored turns
      4. Moment detection — combines engine outputs into typed Moment list
      5. Evidence assembly — two-stage Claude verification (Haiku → Sonnet)
      6. Decision scoring — thin formatter using Claude's scores

    Args:
        call_id: Unique identifier for this call.
        mp3_path: Path to the stereo MP3 recording.
        metadata: Optional flat dict with "agent_name", "customer_name", etc.
                  Auto-loaded from data/metadata/<sid>.json if not supplied.

    Returns:
        Complete CallAnalysis object.

    Raises:
        FileNotFoundError: If the MP3 file is missing.
        RuntimeError: If any critical pipeline stage fails.
    """
    wall_start = time.perf_counter()
    # Only convert to Path for local files — presigned URLs must stay as strings
    is_url = isinstance(mp3_path, str) and mp3_path.startswith("https://")
    if not is_url:
        mp3_path = Path(mp3_path)
    logger.info("=== Processing call_id=%s ===", call_id)

    if metadata is None:
        metadata = meta_loader.load(mp3_path) if not is_url else {}
        if metadata:
            logger.info(
                "  Loaded metadata: agent=%s customer=%s session=%s",
                metadata.get("agent_name"),
                metadata.get("customer_name"),
                metadata.get("session"),
            )

    # ------------------------------------------------------------------
    # Stage 1 — Deepgram ingest
    # ------------------------------------------------------------------
    t0 = time.perf_counter()
    logger.info("[1/6] Deepgram ingest")
    ingest_result = await deepgram_ingest.ingest(call_id=call_id, mp3_path=mp3_path)
    logger.info("  Deepgram ingest complete in %.2fs", time.perf_counter() - t0)

    # ------------------------------------------------------------------
    # Stage 2 — Conversation model
    # ------------------------------------------------------------------
    t0 = time.perf_counter()
    logger.info("[2/6] Conversation model")
    conversation = builder.build(
        ingest_result=ingest_result,
        call_id=call_id,
        metadata=metadata,
    )
    logger.info("  Conversation model built in %.2fs", time.perf_counter() - t0)

    # ------------------------------------------------------------------
    # Stages 3a/3b — Two engines in parallel
    # Semantic gets metadata so Claude can use survey/MOS scores in scoring
    # ------------------------------------------------------------------
    t0 = time.perf_counter()
    logger.info("[3/6] Semantic + behavioral engines (parallel)")
    semantic_result, behavioral_result = await asyncio.gather(
        semantic.analyse(conversation, metadata=metadata),
        behavioral.analyse(conversation),
    )
    logger.info("  Parallel engine stage complete in %.2fs", time.perf_counter() - t0)

    # ------------------------------------------------------------------
    # Backfill participant names from semantic engine if still generic
    # (covers the case where no metadata JSON exists and Stage 2 regex
    # didn't find a match — Claude's reading of the full transcript is
    # more reliable for unusual phrasings)
    # ------------------------------------------------------------------
    _participant_map = {p.role: p for p in conversation.participants}
    if semantic_result.agent_name:
        p = _participant_map.get("agent")
        if p and p.name in ("", "Agent"):
            p.name = semantic_result.agent_name
            logger.info("Backfilled agent name from semantic engine: %r", p.name)
    if semantic_result.customer_name:
        p = _participant_map.get("customer")
        if p and p.name in ("", "Customer"):
            p.name = semantic_result.customer_name
            logger.info("Backfilled customer name from semantic engine: %r", p.name)

    # ------------------------------------------------------------------
    # Stage 4 — Moment detection
    # ------------------------------------------------------------------
    t0 = time.perf_counter()
    logger.info("[4/6] Moment detection")
    moments = moment.detect(
        conversation=conversation,
        behavioral=behavioral_result,
        semantic=semantic_result,
    )
    logger.info("  Detected %d moments in %.2fs", len(moments), time.perf_counter() - t0)

    # ------------------------------------------------------------------
    # Stage 5 — Evidence assembly
    # ------------------------------------------------------------------
    t0 = time.perf_counter()
    logger.info("[5/6] Evidence assembly (DeepSeek two-stage)")
    evidence_list = await evidence.assemble(
        conversation=conversation,
        moments=moments,
    )
    logger.info(
        "  Assembled %d evidence items in %.2fs",
        len(evidence_list),
        time.perf_counter() - t0,
    )

    # ------------------------------------------------------------------
    # Stage 6 — Decision scoring
    # ------------------------------------------------------------------
    t0 = time.perf_counter()
    logger.info("[6/6] Decision scoring")
    effective_resolved = semantic_result.resolved if semantic_result.resolved is not None else False
    decision_result = decision.score(
        moments=moments,
        semantic=semantic_result,
        resolved=effective_resolved,
    )
    logger.info("  Decision scoring complete in %.2fs", time.perf_counter() - t0)

    # ------------------------------------------------------------------
    # Assemble final output
    # ------------------------------------------------------------------
    processing_time = time.perf_counter() - wall_start

    analysis = CallAnalysis(
        call_id=call_id,
        conversation=conversation,
        moments=moments,
        evidence=evidence_list,
        attention_score=decision_result.attention_score,
        qa_score=decision_result.qa_score,
        risk_level=decision_result.risk_level,
        outcome=decision_result.outcome,
        mood_trajectory=behavioral_result.mood_trajectory,
        mood_shift_time=behavioral_result.mood_shift_time,
        mood_shift_magnitude=behavioral_result.mood_shift_magnitude,
        mood_shift_quote=behavioral_result.mood_shift_quote,
        summary=semantic_result.summary,
        intent=semantic_result.intent,
        resolved=effective_resolved,
        processing_time_seconds=round(processing_time, 2),
    )

    logger.info(
        "=== call_id=%s complete — %.2fs | risk=%s | outcome=%s | "
        "attention=%d | qa=%d | moments=%d ===",
        call_id,
        processing_time,
        analysis.risk_level,
        analysis.outcome,
        analysis.attention_score.total,
        analysis.qa_score,
        len(moments),
    )

    return analysis
