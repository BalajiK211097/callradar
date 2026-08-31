"""
Metadata loader and normaliser for CallRadar call records.

Each call has a companion JSON file in data/metadata/<sid>.json whose
structure mirrors the example below.  This module reads that file and
flattens it into a normalised dict that the rest of the pipeline and
the backend can consume without knowing the raw schema.

Raw JSON structure (key fields):
    {
      "sid": "00d676d7058c49bb",
      "start_time_ms": 1591059888619,
      "end_time_ms":   1591059941090,
      "session": "Little Harper Valley 3",
      "agent":  { "metadata": {"agent_name": "Jennifer"},
                  "speaker_id": 17,
                  "survey_response": {"data": {"ease_of_connection": "10",
                                               "partner_rating": "10"}} },
      "caller": { "metadata": {"first and last name": "Robert Johnson"},
                  "speaker_id": 60,
                  "survey_response": {"data": {"ease_of_connection": "10",
                                               "partner_rating": "10"}} },
      "labels": {"lhvb_script": 5.0, "caller_mos": 5.0, "agent_mos": 5.0}
    }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Resolved once at import time — the directory that contains this file is
# pipeline/, so the repo root is one level up.
_REPO_ROOT = Path(__file__).parent.parent
_METADATA_DIR = _REPO_ROOT / "data" / "metadata"


def load(mp3_path: Path) -> dict[str, Any] | None:
    """Find and parse the companion JSON metadata file for an MP3.

    Search order:
      1. data/metadata/<stem>.json  (canonical location)
      2. <mp3_parent>/../metadata/<stem>.json  (fallback for alternative layouts)

    Args:
        mp3_path: Path to the MP3 recording.

    Returns:
        Normalised metadata dict, or None if no JSON file was found.
    """
    stem = mp3_path.stem

    candidates = [
        _METADATA_DIR / f"{stem}.json",
        mp3_path.parent.parent / "metadata" / f"{stem}.json",
    ]

    for path in candidates:
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                normalised = normalize(raw)
                logger.debug("Loaded metadata for %s from %s", stem, path)
                return normalised
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Could not read metadata file %s: %s", path, exc)
                return None

    logger.debug("No metadata file found for %s", stem)
    return None


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten the raw call JSON into a normalised pipeline-ready dict.

    All keys are optional in the raw payload — missing fields are set
    to None rather than raising.

    Args:
        raw: Parsed JSON dict from the metadata file.

    Returns:
        Normalised dict with well-known keys (see field list below).

    Keys in the returned dict
    -------------------------
    sid                 str | None   — call session ID
    agent_name          str | None   — agent's display name
    customer_name       str | None   — caller's full name
    call_start_ms       int | None   — Unix epoch ms when call started
    call_end_ms         int | None   — Unix epoch ms when call ended
    session             str | None   — batch / dataset label
    agent_speaker_id    int | None   — internal speaker ID for the agent
    caller_speaker_id   int | None   — internal speaker ID for the caller
    agent_survey        dict         — post-call survey answers from the agent
    caller_survey       dict         — post-call survey answers from the caller
    labels              dict         — ground-truth quality labels (MOS etc.)
    """
    agent_block = raw.get("agent", {}) or {}
    caller_block = raw.get("caller", {}) or {}

    agent_meta = agent_block.get("metadata", {}) or {}
    caller_meta = caller_block.get("metadata", {}) or {}

    agent_survey_block = agent_block.get("survey_response", {}) or {}
    caller_survey_block = caller_block.get("survey_response", {}) or {}

    # Customer name may live under different keys depending on the dataset
    customer_name = (
        caller_meta.get("first and last name")
        or caller_meta.get("name")
        or caller_meta.get("customer_name")
        or caller_meta.get("full_name")
    )

    return {
        "sid": raw.get("sid"),
        "agent_name": agent_meta.get("agent_name"),
        "customer_name": customer_name,
        "call_start_ms": raw.get("start_time_ms"),
        "call_end_ms": raw.get("end_time_ms"),
        "session": raw.get("session"),
        "agent_speaker_id": agent_block.get("speaker_id"),
        "caller_speaker_id": caller_block.get("speaker_id"),
        "agent_survey": agent_survey_block.get("data", {}),
        "caller_survey": caller_survey_block.get("data", {}),
        "labels": raw.get("labels", {}),
    }
