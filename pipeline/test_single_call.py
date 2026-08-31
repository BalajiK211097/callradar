"""
Test harness for running the full AI pipeline on a single call.

Usage:
    python test_single_call.py <path/to/call.mp3> [call_id]
    python test_single_call.py data/audio/call_001.mp3
    python test_single_call.py data/audio/call_001.mp3 call_001

Prints the complete CallAnalysis as formatted JSON with per-stage timing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# Ensure the repo root is on the Python path so `pipeline.*` imports work
# when this script is run directly with `python pipeline/test_single_call.py`.
repo_root = Path(__file__).parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from pipeline import metadata as meta_loader  # noqa: E402
from pipeline import orchestrator  # noqa: E402

# ---------------------------------------------------------------------------
# Logging — INFO to stdout, one line per record
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("test_single_call")


def _pydantic_json_default(obj):
    """Fallback serialiser for types not natively handled by json.dumps."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "value"):
        return obj.value
    return str(obj)


async def run(mp3_path: Path, call_id: str) -> None:
    """Run the full pipeline and print results.

    Args:
        mp3_path: Path to the stereo MP3 file.
        call_id: Identifier to use for this call.
    """
    if not mp3_path.exists():
        logger.error("File not found: %s", mp3_path)
        sys.exit(1)

    logger.info("Starting pipeline for call_id=%s (%s)", call_id, mp3_path)
    wall = time.perf_counter()

    # Load companion metadata (auto-resolved by orchestrator, but we also
    # want it here so the banner can show survey and MOS scores).
    meta = meta_loader.load(mp3_path) or {}

    analysis = await orchestrator.process_call(
        call_id=call_id,
        mp3_path=mp3_path,
        metadata=meta or None,
    )

    elapsed = time.perf_counter() - wall

    # ------------------------------------------------------------------
    # Summary banner
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"  CallRadar — Analysis Complete")
    print("=" * 70)
    print(f"  call_id        : {analysis.call_id}")
    if meta:
        print(f"  session        : {meta.get('session', 'n/a')}")
        print(f"  agent          : {meta.get('agent_name', 'n/a')}")
        print(f"  customer       : {meta.get('customer_name', 'n/a')}")
        labels = meta.get("labels", {})
        if labels:
            print(f"  caller_mos     : {labels.get('caller_mos', 'n/a')}")
            print(f"  agent_mos      : {labels.get('agent_mos', 'n/a')}")
            print(f"  lhvb_script    : {labels.get('lhvb_script', 'n/a')}")
        caller_survey = meta.get("caller_survey", {})
        if caller_survey:
            print(f"  caller survey  : ease={caller_survey.get('ease_of_connection')}  rating={caller_survey.get('partner_rating')}")
    print(f"  wall time      : {elapsed:.2f}s")
    print(f"  pipeline time  : {analysis.processing_time_seconds:.2f}s")
    print(f"  duration       : {analysis.conversation.duration_seconds:.1f}s")
    print(f"  turns          : {len(analysis.conversation.turns)}")
    print(f"  topics         : {', '.join(analysis.conversation.topics) or 'none'}")
    print(f"  intent         : {analysis.intent}")
    print(f"  summary        : {analysis.summary}")
    print(f"  resolved       : {analysis.resolved}")
    print(f"  outcome        : {analysis.outcome}")
    print(f"  risk_level     : {analysis.risk_level}")
    print(f"  attention_score: {analysis.attention_score.total}/100")
    print(f"  qa_score       : {analysis.qa_score}/100")
    print(f"  moments        : {len(analysis.moments)}")
    print(f"  evidence items : {len(analysis.evidence)}")
    print("=" * 70)

    # Per-moment summary
    if analysis.moments:
        print("\n  MOMENTS DETECTED:")
        for m in analysis.moments:
            print(
                f"    [{m.severity.value:8s}] {m.type.value:25s} "
                f"@ {m.start_time:.1f}s  — \"{m.trigger_phrase[:60]}\""
            )

    # Attention score breakdown
    if analysis.attention_score.components:
        print("\n  ATTENTION SCORE BREAKDOWN:")
        for c in analysis.attention_score.components:
            print(f"    +{c.points:3d}  {c.label}")
        print(f"    {'─' * 20}")
        print(f"    ={analysis.attention_score.total:3d}  TOTAL (capped at 100)")

    # Evidence summary
    if analysis.evidence:
        print("\n  EVIDENCE ITEMS:")
        for ev in analysis.evidence[:10]:  # show first 10
            print(
                f"    [{ev.strength.value:8s}] turn={ev.turn_id} "
                f"{ev.speaker.upper():8s}: \"{ev.quote[:80]}\""
            )
        if len(analysis.evidence) > 10:
            print(f"    ... and {len(analysis.evidence) - 10} more")

    print("\n")

    # ------------------------------------------------------------------
    # Full JSON output
    # ------------------------------------------------------------------
    print("FULL JSON OUTPUT:")
    print("-" * 70)
    try:
        json_str = analysis.model_dump_json(indent=2)
        print(json_str)
    except Exception:
        # Fallback if model_dump_json encounters enum serialisation issues
        raw = analysis.model_dump()
        print(json.dumps(raw, indent=2, default=_pydantic_json_default))


def main() -> None:
    """Entry point for the test harness."""
    if len(sys.argv) < 2:
        print(f"Usage: python {Path(__file__).name} <path/to/call.mp3> [call_id]")
        sys.exit(1)

    mp3_path = Path(sys.argv[1])
    call_id = sys.argv[2] if len(sys.argv) >= 3 else mp3_path.stem

    asyncio.run(run(mp3_path, call_id))


if __name__ == "__main__":
    main()
