"""
Batch ingestion — process all calls in data/audio/.

Pairs each MP3 with its companion JSON from data/metadata/, runs the
full AI pipeline, and writes the result to data/results/<call_id>.json.
Already-processed calls are skipped unless --force is given.

Usage
-----
    # Process everything
    python pipeline/ingest.py

    # Process first 10 calls only (useful for testing)
    python pipeline/ingest.py --limit 10

    # Re-run even if a result file already exists
    python pipeline/ingest.py --force

    # Both
    python pipeline/ingest.py --limit 5 --force
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Ensure the repo root is on the Python path so `pipeline.*` imports work
# when this script is run directly with `python pipeline/ingest.py`.
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline import orchestrator  # noqa: E402

_AUDIO_DIR = _REPO_ROOT / "data" / "audio"
_RESULTS_DIR = _REPO_ROOT / "data" / "results"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingest")


async def _process_one(mp3_path: Path, force: bool) -> bool:
    """Run the pipeline for a single call and save the result JSON.

    Args:
        mp3_path: Path to the MP3 file.
        force: If True, overwrite an existing result file.

    Returns:
        True if the call was processed, False if it was skipped.
    """
    call_id = mp3_path.stem
    result_path = _RESULTS_DIR / f"{call_id}.json"

    if result_path.exists() and not force:
        logger.info("  SKIP  %s (result exists — use --force to rerun)", call_id)
        return False

    t0 = time.perf_counter()
    try:
        analysis = await orchestrator.process_call(
            call_id=call_id,
            mp3_path=mp3_path,
            # metadata=None → orchestrator auto-loads from data/metadata/
        )
        result_path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
        elapsed = time.perf_counter() - t0
        logger.info(
            "  DONE  %s  (%.1fs | risk=%s | qa=%d | moments=%d)",
            call_id,
            elapsed,
            analysis.risk_level,
            analysis.qa_score,
            len(analysis.moments),
        )
        return True

    except Exception:
        logger.exception("  FAIL  %s", call_id)
        return False


async def run(limit: int | None, force: bool) -> None:
    """Scan data/audio/ and process all MP3 files found.

    Args:
        limit: Maximum number of calls to process (None = all).
        force: Overwrite existing result files if True.

    Raises:
        SystemExit: If data/audio/ does not exist or contains no MP3 files.
    """
    if not _AUDIO_DIR.exists():
        logger.error("Audio directory not found: %s", _AUDIO_DIR)
        sys.exit(1)

    mp3_files = sorted(_AUDIO_DIR.glob("*.mp3"))
    if not mp3_files:
        logger.error("No MP3 files found in %s", _AUDIO_DIR)
        sys.exit(1)

    if limit is not None:
        mp3_files = mp3_files[:limit]

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    total = len(mp3_files)
    logger.info(
        "Starting batch ingest — %d calls | results → %s",
        total,
        _RESULTS_DIR,
    )

    wall = time.perf_counter()
    processed = skipped = failed = 0

    for idx, mp3_path in enumerate(mp3_files, 1):
        logger.info("[%d/%d] %s", idx, total, mp3_path.name)
        try:
            did_process = await _process_one(mp3_path, force=force)
            if did_process:
                processed += 1
            else:
                skipped += 1
        except Exception:
            failed += 1

    elapsed = time.perf_counter() - wall
    logger.info(
        "Ingest complete — processed=%d  skipped=%d  failed=%d  total_time=%.1fs",
        processed,
        skipped,
        failed,
        elapsed,
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Batch-process all calls in data/audio/ through the CallRadar pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process at most N calls (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess calls that already have a result file",
    )
    args = parser.parse_args()
    asyncio.run(run(limit=args.limit, force=args.force))


if __name__ == "__main__":
    main()
