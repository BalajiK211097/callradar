"""
Batch submit all 1441 calls to the running CallRadar backend API.

Run this on your host machine while docker-compose is up:

    python scripts/batch_submit.py                  # submit all unprocessed
    python scripts/batch_submit.py --limit 10       # test with 10 first
    python scripts/batch_submit.py --force          # resubmit even done calls
    python scripts/batch_submit.py --concurrency 3  # adjust parallelism

The script reads SID list from data/metadata/ (local files) and submits
each call to http://localhost:8000/calls/submit. The backend fetches audio
from S3 automatically — no local MP3s needed.

Already-processed calls (status=done) are skipped unless --force is passed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

API_BASE = "http://localhost:8000"
METADATA_DIR = Path(__file__).resolve().parents[1] / "data" / "metadata"


def get_sids() -> list[str]:
    """Return all SIDs from local data/metadata/ directory."""
    if not METADATA_DIR.exists():
        print(f"ERROR: {METADATA_DIR} not found. Make sure data/metadata/ exists locally.")
        sys.exit(1)
    sids = sorted(p.stem for p in METADATA_DIR.glob("*.json"))
    if not sids:
        print(f"ERROR: No JSON files found in {METADATA_DIR}")
        sys.exit(1)
    return sids


async def check_status(client: httpx.AsyncClient, call_id: str, api_base: str) -> str | None:
    """Return call status ('pending','processing','done','failed') or None if not found."""
    try:
        r = await client.get(f"{api_base}/calls/{call_id}", timeout=5)
        if r.status_code == 200:
            return r.json().get("status")
        return None
    except Exception:
        return None


async def submit(client: httpx.AsyncClient, call_id: str, api_base: str, force: bool = False) -> tuple[str, str]:
    """Submit one call with up to 3 retries on connection errors. Returns (call_id, result_message)."""
    payload = {
        "call_id": call_id,
        "mp3_path": f"audio/{call_id}.mp3",
    }
    last_err = ""
    for attempt in range(3):
        try:
            r = await client.post(
                f"{api_base}/calls/submit",
                json=payload,
                timeout=30,
            )
            if r.status_code in (200, 202):
                return call_id, "submitted"
            if r.status_code == 409 and force:
                r2 = await client.post(f"{api_base}/calls/{call_id}/reprocess", timeout=30)
                if r2.status_code in (200, 202):
                    return call_id, "reprocessing"
                return call_id, f"error reprocess {r2.status_code}: {r2.text[:80]}"
            if r.status_code == 409:
                return call_id, "already_exists"
            return call_id, f"error {r.status_code}: {r.text[:80]}"
        except Exception as exc:
            exc_type = type(exc).__name__
            exc_msg = str(exc) or "(no message)"
            last_err = f"{exc_type}: {exc_msg}"
            if attempt < 2:
                wait = 5 * (attempt + 1)
                await asyncio.sleep(wait)
    return call_id, f"error: {last_err}"


async def wait_for_completion(client: httpx.AsyncClient, call_id: str, api_base: str, timeout_s: int = 300) -> str:
    """Poll until a call reaches done/failed or timeout. Returns final status."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        await asyncio.sleep(5)
        status = await check_status(client, call_id, api_base)
        if status in ("done", "failed"):
            return status or "unknown"
    return "timeout"


async def run(sids: list[str], force: bool, concurrency: int, sequential: bool = False, api_base: str = API_BASE) -> None:
    """Main async runner — checks status, submits pending calls."""
    print(f"API: {api_base}")
    print(f"Total SIDs: {len(sids)}")
    print(f"Mode: {'sequential (one at a time)' if sequential else f'parallel (concurrency={concurrency})'}")
    print()

    async with httpx.AsyncClient() as client:
        # Verify API is reachable
        try:
            r = await client.get(f"{api_base}/health", timeout=5)
            r.raise_for_status()
        except Exception as exc:
            print(f"ERROR: Cannot reach API at {api_base}: {exc}")
            print("Make sure docker-compose is running: docker-compose up")
            sys.exit(1)

        print("API is reachable.")

        # Check which calls are already done (skip unless --force)
        if not force:
            print("Checking existing call statuses (this may take a moment)…")
            to_submit = []
            for i, sid in enumerate(sids):
                status = await check_status(client, sid, api_base)
                if status == "done":
                    pass  # skip
                elif status in ("pending", "processing"):
                    pass  # already in flight, skip
                else:
                    to_submit.append(sid)
                if (i + 1) % 100 == 0:
                    print(f"  checked {i + 1}/{len(sids)} …")
            print(f"  {len(sids) - len(to_submit)} already done/in-flight, {len(to_submit)} to submit")
        else:
            to_submit = sids
            print(f"--force: submitting all {len(to_submit)} calls")

        if not to_submit:
            print("Nothing to submit. All calls are already processed.")
            return

        print(f"\nSubmitting {len(to_submit)} calls…\n")

        done = 0
        errors = 0
        start = time.time()

        if sequential:
            # One call at a time — submit, wait for completion, then next
            for call_id in to_submit:
                _, result = await submit(client, call_id, api_base, force=force)
                done += 1
                elapsed = time.time() - start
                print(f"  [{done}/{len(to_submit)}] {call_id}: {result}", end="", flush=True)
                if "error" not in result and result != "already_exists":
                    final = await wait_for_completion(client, call_id, api_base)
                    print(f" → {final} ({elapsed:.0f}s elapsed)")
                    if final == "failed":
                        errors += 1
                else:
                    print()
                    if "error" in result:
                        errors += 1
        else:
            sem = asyncio.Semaphore(concurrency)

            async def bounded_submit(call_id: str) -> None:
                nonlocal done, errors
                async with sem:
                    _, result = await submit(client, call_id, api_base, force=force)
                    done += 1
                    if "error" in result:
                        errors += 1
                        print(f"  [{done}/{len(to_submit)}] {call_id}: {result}")
                    elif done % 50 == 0 or done <= 5:
                        elapsed = time.time() - start
                        rate = done / elapsed if elapsed > 0 else 0
                        eta = (len(to_submit) - done) / rate if rate > 0 else 0
                        print(f"  [{done}/{len(to_submit)}] {result}  ({rate:.1f}/s, ETA {eta/60:.1f}m)")

            await asyncio.gather(*[bounded_submit(sid) for sid in to_submit])

        elapsed = time.time() - start
        print(f"\nDone. {done} submitted ({errors} errors) in {elapsed:.0f}s")
        print(f"Monitor progress: GET {api_base}/calls/stats")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch submit calls to CallRadar API")
    parser.add_argument("--limit", type=int, default=None, help="Only submit the first N calls")
    parser.add_argument("--force", action="store_true", help="Resubmit even calls with status=done")
    parser.add_argument("--concurrency", type=int, default=2, help="Max parallel submissions (default 2)")
    parser.add_argument("--sequential", action="store_true", help="Process one call at a time, wait for each to finish")
    parser.add_argument("--api", default=API_BASE, help=f"API base URL (default {API_BASE})")
    args = parser.parse_args()

    api_base = args.api.rstrip("/")

    sids = get_sids()
    if args.limit:
        sids = sids[: args.limit]

    asyncio.run(run(sids, force=args.force, concurrency=args.concurrency, sequential=args.sequential, api_base=api_base))


if __name__ == "__main__":
    main()
