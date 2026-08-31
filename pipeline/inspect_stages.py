"""
Stage-by-stage pipeline inspector.

Runs each pipeline stage individually and pretty-prints the output model
after every stage so you can see exactly what each API returns.

Usage:
    python pipeline/inspect_stages.py data/audio/<sid>.mp3
    python pipeline/inspect_stages.py data/audio/<sid>.mp3 --stage 1
    python pipeline/inspect_stages.py data/audio/<sid>.mp3 --stage 3a

Stages:
    1    Deepgram ingest     (transcription + sentiment + entities + topics)
    2    Conversation model  (Turn list, silence, overtalk)
    3a   Semantic engine     (DeepSeek — moments, scores, intent, summary)
    3b   Behavioral engine   (mood trajectory, sentiment per turn)
    4    Moment detection    (typed Moment list)
    5    Evidence assembly   (DeepSeek-verified quotes)
    6    Decision scoring    (attention score, QA score, risk level, outcome)
    all  Run all stages (default)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

repo_root = Path(__file__).parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("inspect_stages")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dump(obj: Any) -> str:
    """Serialise a Pydantic model or plain dict to indented JSON."""
    if hasattr(obj, "model_dump_json"):
        return obj.model_dump_json(indent=2)
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(), indent=2, default=str)
    if isinstance(obj, list):
        return json.dumps(
            [o.model_dump() if hasattr(o, "model_dump") else o for o in obj],
            indent=2,
            default=str,
        )
    return json.dumps(obj, indent=2, default=str)


def _banner(title: str, elapsed: float) -> None:
    """Print a section banner."""
    print(f"\n{'=' * 70}")
    print(f"  {title}  ({elapsed:.2f}s)")
    print(f"{'=' * 70}")


# ---------------------------------------------------------------------------
# Individual stage runners
# ---------------------------------------------------------------------------

async def run_stage_1(mp3_path: Path, call_id: str) -> Any:
    """Stage 1 — Deepgram ingest."""
    from pipeline.audio_intelligence import deepgram_ingest

    t = time.perf_counter()
    result = await deepgram_ingest.ingest(call_id=call_id, mp3_path=mp3_path)
    _banner("STAGE 1 — Deepgram Ingest", time.perf_counter() - t)

    # Print a human-readable summary before the full JSON
    raw = result.model_dump() if hasattr(result, "model_dump") else {}
    utterances = raw.get("utterances", [])
    print(f"  utterances      : {len(utterances)}")
    print(f"  topics          : {raw.get('topics', [])}")
    print(f"  intent          : {raw.get('intent', '')}")
    print(f"  summary         : {raw.get('summary', '')[:120]}")
    print(f"  entities        : {len(raw.get('entities', []))}")
    if utterances:
        print(f"\n  First 5 utterances:")
        for u in utterances[:5]:
            channel = u.get("channel", "?")
            text = u.get("text", "")[:80]
            sentiment = u.get("sentiment_score", "n/a")
            start = u.get("start", 0)
            print(f"    [{channel:8s}] {start:6.1f}s  sentiment={sentiment:+.2f}  \"{text}\"")
    print(f"\nFULL JSON:")
    print(_dump(result))
    return result


async def run_stage_2(ingest_result: Any, call_id: str, metadata: dict) -> Any:
    """Stage 2 — Conversation model."""
    from pipeline.conversation_model import builder

    t = time.perf_counter()
    conversation = builder.build(
        ingest_result=ingest_result,
        call_id=call_id,
        metadata=metadata,
    )
    _banner("STAGE 2 — Conversation Model", time.perf_counter() - t)

    print(f"  turns           : {len(conversation.turns)}")
    print(f"  duration        : {conversation.duration_seconds:.1f}s")
    print(f"  silence segs    : {len(conversation.silence_segments)}")
    print(f"  overtalk segs   : {len(conversation.overtalk_segments)}")
    print(f"  entities        : {len(conversation.entities)}")
    print(f"  topics          : {conversation.topics}")
    for p in conversation.participants:
        print(f"  participant     : {p.role:8s} '{p.name}'  talk={p.talk_time_seconds:.1f}s  turns={p.turn_count}")
    if conversation.turns:
        print(f"\n  First 5 turns:")
        for turn in conversation.turns[:5]:
            sentiment = f"{turn.sentiment_score:+.2f}" if turn.sentiment_score is not None else "n/a"
            print(f"    [{turn.id:3d}] {turn.speaker:8s}  {turn.start_time:6.1f}s  sentiment={sentiment}  \"{turn.text[:70]}\"")
    print(f"\nFULL JSON:")
    print(_dump(conversation))
    return conversation


async def run_stage_3(conversation: Any, metadata: dict) -> tuple[Any, Any]:
    """Stages 3a/3b — Semantic (DeepSeek) + Behavioral engines (parallel)."""
    from pipeline.engines import behavioral, semantic

    t = time.perf_counter()
    semantic_result, behavioral_result = await asyncio.gather(
        semantic.analyse(conversation, metadata=metadata),
        behavioral.analyse(conversation),
    )
    elapsed = time.perf_counter() - t

    _banner("STAGE 3a — Semantic Engine (DeepSeek)", elapsed)
    print(f"  intent          : {semantic_result.intent}")
    print(f"  summary         : {semantic_result.summary[:120]}")
    print(f"  resolved        : {semantic_result.resolved}")
    print(f"  semantic_topics : {semantic_result.semantic_topics}")
    print(f"  customer_name   : {semantic_result.customer_name!r}")
    print(f"  agent_name      : {semantic_result.agent_name!r}")
    print(f"  identity_verified        : {semantic_result.identity_verified}")
    print(f"  reference_number_given   : {semantic_result.reference_number_given}")
    print(f"  escalation_detected      : {semantic_result.escalation_detected}")
    print(f"  repeat_contact           : {semantic_result.repeat_contact}")
    print(f"  fraud_signals            : {semantic_result.fraud_signals}")
    print(f"\n  DETECTED MOMENTS ({len(semantic_result.detected_moments)}):")
    for dm in semantic_result.detected_moments:
        print(f"    [{dm.severity:8s}] {dm.type:25s} turn={dm.turn_id}  {dm.description[:70]}")
    print(f"\n  SCORES:")
    print(f"    attention_score : {semantic_result.attention_score}/100  — {semantic_result.attention_reasoning}")
    print(f"    qa_score        : {semantic_result.qa_score}/100  — {semantic_result.qa_reasoning}")
    print(f"    risk_level      : {semantic_result.risk_level}")
    print(f"\nFULL JSON:")
    print(_dump(semantic_result))

    _banner("STAGE 3b — Behavioral Engine", elapsed)
    raw_b = behavioral_result.model_dump() if hasattr(behavioral_result, "model_dump") else {}
    traj = raw_b.get("mood_trajectory", [])
    print(f"  mood trajectory : {len(traj)} data points")
    print(f"  mood_start      : {raw_b.get('mood_start')}")
    print(f"  mood_end        : {raw_b.get('mood_end')}")
    print(f"  mood_shift_time : {raw_b.get('mood_shift_time')}")
    print(f"  mood_shift_mag  : {raw_b.get('mood_shift_magnitude')}")
    print(f"  mood_shift_quote: {str(raw_b.get('mood_shift_quote', ''))[:80]}")
    if traj:
        print(f"\n  Mood trajectory (first 10 points):")
        for pt in traj[:10]:
            print(f"    {pt}")
    print(f"\nFULL JSON:")
    print(_dump(behavioral_result))

    return semantic_result, behavioral_result


async def run_stage_4(
    conversation: Any,
    behavioral_result: Any,
    semantic_result: Any,
) -> list[Any]:
    """Stage 4 — Moment detection."""
    from pipeline.engines import moment

    effective_resolved = semantic_result.resolved if semantic_result.resolved is not None else False

    t = time.perf_counter()
    moments = moment.detect(
        conversation=conversation,
        behavioral=behavioral_result,
        semantic=semantic_result,
    )
    _banner("STAGE 4 — Moment Detection", time.perf_counter() - t)

    print(f"  total moments   : {len(moments)}")
    print(f"  effective_resolved (passed to moment.detect): {effective_resolved}")
    if moments:
        print(f"\n  All moments:")
        for m in moments:
            raw_m = m.model_dump() if hasattr(m, "model_dump") else {}
            print(
                f"    [{raw_m.get('severity', '?'):8s}] {raw_m.get('type', '?'):25s} "
                f"@ {raw_m.get('start_time', 0):.1f}s  \"{str(raw_m.get('trigger_phrase', ''))[:60]}\""
            )
    print(f"\nFULL JSON:")
    print(_dump(moments))
    return moments


async def run_stage_5(conversation: Any, moments: list[Any]) -> list[Any]:
    """Stage 5 — Evidence assembly."""
    from pipeline.engines import evidence

    t = time.perf_counter()
    evidence_list = await evidence.assemble(
        conversation=conversation,
        moments=moments,
    )
    _banner("STAGE 5 — Evidence Assembly (DeepSeek)", time.perf_counter() - t)

    print(f"  total evidence  : {len(evidence_list)}")
    if evidence_list:
        print(f"\n  All evidence items:")
        for ev in evidence_list:
            raw_ev = ev.model_dump() if hasattr(ev, "model_dump") else {}
            print(
                f"    [{raw_ev.get('strength', '?'):8s}] turn={raw_ev.get('turn_id'):3d} "
                f"{raw_ev.get('speaker', '?').upper():8s}: \"{str(raw_ev.get('quote', ''))[:80]}\""
            )
            if raw_ev.get("reasoning"):
                print(f"                 reason: \"{str(raw_ev.get('reasoning', ''))[:80]}\"")
    print(f"\nFULL JSON:")
    print(_dump(evidence_list))
    return evidence_list


async def run_stage_6(
    moments: list[Any],
    semantic_result: Any,
    conversation: Any,
) -> Any:
    """Stage 6 — Decision scoring."""
    from pipeline.engines import decision

    effective_resolved = semantic_result.resolved if semantic_result.resolved is not None else False

    t = time.perf_counter()
    decision_result = decision.score(
        moments=moments,
        semantic=semantic_result,
        resolved=effective_resolved,
    )
    _banner("STAGE 6 — Decision Scoring", time.perf_counter() - t)

    raw_d = decision_result.model_dump() if hasattr(decision_result, "model_dump") else {}
    att = raw_d.get("attention_score", {})
    print(f"  qa_score        : {raw_d.get('qa_score')}/100")
    print(f"  attention_score : {att.get('total')}/100")
    print(f"  risk_level      : {raw_d.get('risk_level')}")
    print(f"  outcome         : {raw_d.get('outcome')}")
    print(f"  effective_resolved passed: {effective_resolved}")
    components = att.get("components", [])
    if components:
        print(f"\n  Attention score breakdown:")
        for c in components:
            print(f"    +{c.get('points', 0):3d}  {c.get('label', '')}")
        print(f"    {'─' * 20}")
        print(f"    ={att.get('total', 0):3d}  TOTAL")
    print(f"\nFULL JSON:")
    print(_dump(decision_result))
    return decision_result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

VALID_STAGES = {"1", "2", "3a", "3b", "4", "5", "6", "all"}


async def main(mp3_path: Path, target_stage: str) -> None:
    """Run the pipeline up to (and including) the requested stage.

    Args:
        mp3_path: Path to the stereo MP3 recording.
        target_stage: Which stage to stop at — '1' through '6', or 'all'.
    """
    from pipeline import metadata as meta_loader

    if not mp3_path.exists():
        logger.error("File not found: %s", mp3_path)
        sys.exit(1)

    call_id = mp3_path.stem
    logger.info("Inspector starting — call_id=%s  target_stage=%s", call_id, target_stage)

    meta = meta_loader.load(mp3_path) or {}
    if meta:
        logger.info("  Loaded metadata: agent=%s  customer=%s", meta.get("agent_name"), meta.get("customer_name"))

    wall = time.perf_counter()

    # Stage 1 — always runs
    ingest_result = await run_stage_1(mp3_path, call_id)
    if target_stage == "1":
        return

    # Stage 2
    conversation = await run_stage_2(ingest_result, call_id, meta)
    if target_stage == "2":
        return

    # Stage 3 (semantic + behavioral in parallel)
    semantic_result, behavioral_result = await run_stage_3(conversation, meta)
    if target_stage in ("3a", "3b"):
        return

    # Stage 4
    moments = await run_stage_4(conversation, behavioral_result, semantic_result)
    if target_stage == "4":
        return

    # Stage 5
    evidence_list = await run_stage_5(conversation, moments)
    if target_stage == "5":
        return

    # Stage 6
    decision_result = await run_stage_6(
        moments, semantic_result, conversation
    )

    print(f"\n{'=' * 70}")
    print(f"  All stages complete in {time.perf_counter() - wall:.2f}s")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run pipeline stages and inspect output")
    parser.add_argument("mp3_path", type=Path, help="Path to the stereo MP3 file")
    parser.add_argument(
        "--stage",
        default="all",
        choices=sorted(VALID_STAGES),
        help="Stop after this stage (default: all)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.mp3_path, args.stage))
