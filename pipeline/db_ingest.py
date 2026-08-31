"""
Batch ingestion directly into PostgreSQL.

Pairs each MP3 with its companion JSON from data/metadata/, runs the full
AI pipeline, and persists the result to the database via backend.db.
Already-processed calls (status='done') are skipped unless --force is given.

Usage
-----
    # Process everything
    python pipeline/db_ingest.py

    # Process first 10 calls only
    python pipeline/db_ingest.py --limit 10

    # Re-run even if already done in DB
    python pipeline/db_ingest.py --force

    # Both
    python pipeline/db_ingest.py --limit 5 --force
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Repo root on path so both `pipeline.*` and `backend.*` imports work
_REPO_ROOT = Path(__file__).parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / ".env")

from sqlalchemy import select

from backend.db import (
    AsyncSessionLocal,
    CallRecord,
    init_db,
    mark_failed,
    save_analysis,
)
from pipeline import metadata as meta_loader
from pipeline import orchestrator

_AUDIO_DIR = _REPO_ROOT / "data" / "audio"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("db_ingest")


async def _process_one(mp3_path: Path, force: bool) -> bool:
    """Run the pipeline for a single call and save the result to the database.

    Args:
        mp3_path: Path to the MP3 file.
        force: If True, reprocess even if the call is already done.

    Returns:
        True if the call was processed, False if it was skipped.
    """
    call_id = mp3_path.stem

    async with AsyncSessionLocal() as db:
        existing: CallRecord | None = await db.scalar(
            select(CallRecord).where(CallRecord.call_id == call_id)
        )

        if existing is not None and existing.status == "done" and not force:
            logger.info("  SKIP  %s (already done — use --force to rerun)", call_id)
            return False

        # Upsert: create if missing, otherwise reset to pending
        if existing is None:
            record = CallRecord(call_id=call_id, mp3_path=str(mp3_path), status="processing")
            db.add(record)
        else:
            existing.status = "processing"
            existing.error_message = None
            existing.analysis_json = None
        await db.commit()

    t0 = time.perf_counter()
    try:
        raw_metadata = meta_loader.load(mp3_path) or {}
        analysis = await orchestrator.process_call(
            call_id=call_id,
            mp3_path=mp3_path,
            metadata=raw_metadata or None,
        )
        async with AsyncSessionLocal() as db:
            await save_analysis(db, call_id, analysis, raw_metadata=raw_metadata)

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
        async with AsyncSessionLocal() as db:
            await mark_failed(db, call_id, f"db_ingest failed for {call_id}")
        return False


async def run(limit: int | None, force: bool) -> None:
    """Scan data/audio/ and process all MP3 files into the database.

    Args:
        limit: Maximum number of calls to process (None = all).
        force: Reprocess calls already marked done if True.

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

    # Ensure tables exist (safe no-op if they already do)
    await init_db()

    total = len(mp3_files)
    logger.info("Starting DB ingest — %d calls → PostgreSQL", total)

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
        description="Batch-process all calls in data/audio/ and save to PostgreSQL.",
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
        help="Reprocess calls that are already done in the DB",
    )
    args = parser.parse_args()
    asyncio.run(run(limit=args.limit, force=args.force))


if __name__ == "__main__":
    main()
