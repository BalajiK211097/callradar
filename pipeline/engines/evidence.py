"""
Evidence assembly engine.

Two-stage Claude-powered process:
  Stage 1 — Claude Haiku selects candidate turn IDs for each Moment.
  Stage 2 — Backend validates those IDs exist in the transcript.
  Stage 3 — Claude Sonnet verifies the evidence supports the claim.

Quotes always come from the actual transcript; Claude never generates them.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import os

import openai

from pipeline import config
from pipeline.models import (
    ConversationModel,
    Evidence,
    EvidenceStrength,
    Moment,
    MomentType,
    Turn,
)

# Physical-signal moments have no transcript quote to verify — skip them entirely.
_SKIP_EVIDENCE_TYPES: frozenset[MomentType] = frozenset({
    MomentType.LONG_SILENCE,
    MomentType.OVERTALK,
})

logger = logging.getLogger(__name__)

_client: openai.OpenAI | None = None


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from a Claude response before JSON parsing."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _get_client() -> openai.OpenAI:
    """Return (and cache) the DeepSeek API client."""
    global _client
    if _client is None:
        _client = openai.OpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=config.DEEPSEEK_EVIDENCE_TIMEOUT,
        )
    return _client


def _format_transcript_for_prompt(turns: list[Turn]) -> str:
    """Render turns as a compact numbered list for prompt injection."""
    lines = [
        f"[turn_id={t.id}] [{t.start_time:.1f}s] {t.speaker.upper()}: {t.text}"
        for t in turns
    ]
    return "\n".join(lines)


def _stage1_select_turn_ids(
    moment: Moment,
    conversation: ConversationModel,
) -> list[int]:
    """Ask Claude Haiku which turn IDs best support a given moment.

    Args:
        moment: The Moment to find evidence for.
        conversation: The ConversationModel containing all turns.

    Returns:
        List of candidate turn IDs (may be empty if Haiku returns none).

    Raises:
        openai.APIError: If the DeepSeek API call fails.
    """
    client = _get_client()
    transcript = _format_transcript_for_prompt(conversation.turns)

    prompt = (
        f"You are reviewing a bank support call transcript.\n\n"
        f"Moment type: {moment.type.value}\n"
        f"Moment description: {moment.trigger_phrase or moment.type.value}\n"
        f"Moment time: {moment.start_time:.1f}s – {moment.end_time:.1f}s\n\n"
        f"Transcript:\n{transcript}\n\n"
        f"Select up to {config.EVIDENCE_MAX_TURNS_PER_MOMENT} turn_ids from the "
        f"transcript that best support this moment.\n"
        f"Return ONLY valid JSON: {{\"evidence_turn_ids\": [int, ...]}}\n"
        f"No preamble. No explanation."
    )

    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        max_tokens=config.EVIDENCE_HAIKU_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content or "" if response.choices else ""
    try:
        data = json.loads(_strip_code_fences(raw))
        return [int(tid) for tid in data.get("evidence_turn_ids", [])]
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning(
            "Stage 1 JSON parse error for moment %s: %s — raw: %.200s",
            moment.type.value,
            exc,
            raw,
        )
        return []


def _stage2_validate_ids(
    candidate_ids: list[int],
    conversation: ConversationModel,
) -> list[Turn]:
    """Filter candidate IDs to those that actually exist in the transcript.

    This is the anti-hallucination gate — Claude cannot invent quotes
    because we always retrieve text from the real Turn objects.

    Args:
        candidate_ids: Turn IDs returned by Haiku.
        conversation: Source of truth for turn existence.

    Returns:
        List of real Turn objects matching the validated IDs.
    """
    turn_map = {t.id: t for t in conversation.turns}
    validated = [turn_map[tid] for tid in candidate_ids if tid in turn_map]
    return validated


def _stage3_verify_evidence(
    moment: Moment,
    candidate_turns: list[Turn],
) -> dict[str, Any]:
    """Ask Claude Sonnet whether the candidate turns support the moment claim.

    Args:
        moment: The Moment to verify.
        candidate_turns: Real Turn objects fetched from the transcript.

    Returns:
        Dict with keys: supported (bool), strength (str),
        evidence_turn_ids (list[int]), reasoning (str).

    Raises:
        openai.APIError: If the DeepSeek API call fails.
    """
    client = _get_client()

    turn_text = "\n".join(
        f"[turn_id={t.id}] {t.speaker.upper()}: {t.text}"
        for t in candidate_turns
    )

    prompt = (
        f"You are a quality analyst verifying evidence for a call centre audit.\n\n"
        f"Claim: This call contains a {moment.type.value} moment.\n"
        f"Trigger: \"{moment.trigger_phrase}\"\n\n"
        f"Candidate evidence turns:\n{turn_text}\n\n"
        f"Does this evidence support the claim? Return ONLY valid JSON:\n"
        f"{{\n"
        f"  \"supported\": bool,\n"
        f"  \"strength\": \"WEAK\" | \"MODERATE\" | \"STRONG\",\n"
        f"  \"evidence_turn_ids\": [int, ...],\n"
        f"  \"reasoning\": \"one sentence\"\n"
        f"}}\n"
        f"No preamble. No explanation."
    )

    response = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        max_tokens=config.EVIDENCE_SONNET_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content or "" if response.choices else ""
    try:
        data = json.loads(_strip_code_fences(raw))
        return data
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "Stage 3 JSON parse error for moment %s: %s — raw: %.200s",
            moment.type.value,
            exc,
            raw,
        )
        return {
            "supported": False,
            "strength": "WEAK",
            "evidence_turn_ids": [],
            "reasoning": "parse error",
        }


def _strength_from_str(raw: str) -> EvidenceStrength:
    """Safely convert a string to EvidenceStrength enum."""
    mapping = {
        "WEAK": EvidenceStrength.WEAK,
        "MODERATE": EvidenceStrength.MODERATE,
        "STRONG": EvidenceStrength.STRONG,
    }
    return mapping.get(str(raw).upper(), EvidenceStrength.WEAK)


async def assemble(
    conversation: ConversationModel,
    moments: list[Moment],
) -> list[Evidence]:
    """Assemble verified evidence objects for all detected moments.

    For each Moment:
      1. Haiku selects candidate turn IDs.
      2. Backend validates those IDs exist in the transcript.
      3. Sonnet verifies the evidence supports the claim.
      4. Evidence objects are built from real transcript text only.

    Moments with no validated turns or where Sonnet rejects the evidence
    are skipped — no evidence is fabricated.

    Args:
        conversation: The ConversationModel with all transcript turns.
        moments: List of Moments detected by the moment engine.

    Returns:
        List of Evidence objects referencing real transcript turns.

    Raises:
        openai.APIError: If either DeepSeek API call fails after retries.
    """
    if not moments:
        return []

    turn_map = {t.id: t for t in conversation.turns}
    all_evidence: list[Evidence] = []

    for moment in moments:
        # Physical-signal moments (silence, overtalk) have no transcript quote.
        if moment.type in _SKIP_EVIDENCE_TYPES:
            logger.debug(
                "call_id=%s: skipping evidence for physical moment %s",
                conversation.call_id,
                moment.type.value,
            )
            continue

        logger.debug(
            "call_id=%s: assembling evidence for moment %s (id=%d)",
            conversation.call_id,
            moment.type.value,
            moment.id,
        )

        try:
            if moment.evidence_turn_ids:
                # Claude or behavioral engine already identified the supporting turn(s).
                # Skip Haiku and go straight to validation + Sonnet verification.
                logger.debug(
                    "call_id=%s: moment %s — using pre-supplied turn_ids %s (skipping Haiku)",
                    conversation.call_id,
                    moment.type.value,
                    moment.evidence_turn_ids,
                )
                candidate_turns = _stage2_validate_ids(moment.evidence_turn_ids, conversation)
            else:
                # No turn IDs supplied — ask Haiku to find candidate turns.
                candidate_ids = _stage1_select_turn_ids(moment, conversation)
                candidate_turns = _stage2_validate_ids(candidate_ids, conversation)

            if not candidate_turns:
                logger.debug(
                    "call_id=%s: moment %s — no valid candidate turns",
                    conversation.call_id,
                    moment.type.value,
                )
                continue

            # Sonnet verifies the evidence supports the moment claim.
            verification = _stage3_verify_evidence(moment, candidate_turns)

            if not verification.get("supported", False):
                logger.debug(
                    "call_id=%s: moment %s — evidence not supported by Sonnet",
                    conversation.call_id,
                    moment.type.value,
                )
                continue

            strength = _strength_from_str(verification.get("strength", "WEAK"))
            verified_ids: list[int] = [
                int(tid) for tid in verification.get("evidence_turn_ids", [])
                if int(tid) in turn_map
            ]

            # Build Evidence from the actual validated turn text
            for tid in verified_ids:
                turn = turn_map[tid]
                all_evidence.append(
                    Evidence(
                        claim=f"{moment.type.value}: {moment.trigger_phrase}",
                        turn_id=tid,
                        timestamp=turn.start_time,
                        speaker=turn.speaker,
                        quote=turn.text,  # always from real transcript
                        strength=strength,
                        confidence=round(moment.confidence, 4),
                    )
                )

        except openai.APIError as exc:
            logger.error(
                "call_id=%s: evidence engine API error for moment %s: %s",
                conversation.call_id,
                moment.type.value,
                exc,
            )
            raise

    logger.info(
        "call_id=%s: evidence assembled — %d evidence items from %d moments",
        conversation.call_id,
        len(all_evidence),
        len(moments),
    )

    return all_evidence
