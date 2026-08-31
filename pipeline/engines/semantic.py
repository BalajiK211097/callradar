"""
Semantic intelligence engine.

When config.USE_CLAUDE_SEMANTIC is True (default), calls Claude Sonnet with the
full transcript AND post-call metadata (surveys, MOS, script-adherence score) to:
  - Detect moments contextually (no phrase lists)
  - Compute attention score and QA score informed by ground-truth survey data
  - Return intent, summary, resolution, and business signals

When config.USE_CLAUDE_SEMANTIC is False, returns Deepgram-provided summary/intent
and zero-filled scores — useful for rapid offline testing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

import os

import openai

from pipeline import config
from pipeline.models import ConversationModel, DetectedMoment, SemanticResult

logger = logging.getLogger(__name__)

_client: openai.AsyncOpenAI | None = None


def _get_client() -> openai.AsyncOpenAI:
    """Return (and cache) the async DeepSeek client."""
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI(
            api_key=os.environ["DEEPSEEK_API_KEY"],
            base_url=config.DEEPSEEK_BASE_URL,
            timeout=config.DEEPSEEK_SEMANTIC_TIMEOUT,
        )
    return _client


def _build_transcript_text(
    conversation: ConversationModel,
    max_chars: int = config.SEMANTIC_MAX_TRANSCRIPT_CHARS,
) -> str:
    """Render turns as a compact plain-text transcript with turn IDs and timestamps.

    Args:
        conversation: ConversationModel to render.
        max_chars: Maximum character count before truncation.

    Returns:
        Formatted transcript string.
    """
    lines: list[str] = []
    for turn in conversation.turns:
        lines.append(
            f"[turn_id={turn.id}] [{turn.start_time:.1f}s] {turn.speaker.upper()}: {turn.text}"
        )
    full = "\n".join(lines)
    if len(full) > max_chars:
        full = full[:max_chars] + "\n[TRANSCRIPT TRUNCATED]"
    return full


def _build_metadata_block(metadata: dict[str, Any] | None) -> str:
    """Format post-call metadata as a readable context block for Claude.

    Args:
        metadata: Normalised metadata dict from pipeline/metadata.py.

    Returns:
        Formatted string, or empty string if no metadata.
    """
    if not metadata:
        return ""

    caller_survey = metadata.get("caller_survey") or {}
    agent_survey = metadata.get("agent_survey") or {}
    labels = metadata.get("labels") or {}

    lines: list[str] = []

    caller_partner = caller_survey.get("partner_rating")
    caller_ease = caller_survey.get("ease_of_connection")
    agent_partner = agent_survey.get("partner_rating")

    if caller_partner is not None:
        lines.append(
            f"  caller_partner_rating: {caller_partner}/10  "
            f"(customer's post-call rating of the agent — strongest QA signal)"
        )
    if caller_ease is not None:
        lines.append(f"  caller_ease_of_connection: {caller_ease}/10")
    if agent_partner is not None:
        lines.append(f"  agent_partner_rating: {agent_partner}/10  (agent's self-rating)")

    lhvb = labels.get("lhvb_script")
    caller_mos = labels.get("caller_mos")
    agent_mos = labels.get("agent_mos")

    if lhvb is not None:
        lines.append(f"  script_adherence: {lhvb}/5  (how closely agent followed required script)")
    if caller_mos is not None:
        lines.append(f"  caller_audio_mos: {caller_mos}/5")
    if agent_mos is not None:
        lines.append(f"  agent_audio_mos: {agent_mos}/5")

    if not lines:
        return ""
    return "## Post-Call Metadata\n" + "\n".join(lines)


def _build_conversation_stats(conversation: ConversationModel) -> str:
    """Build a short stats block from the conversation model.

    Args:
        conversation: Fully populated ConversationModel.

    Returns:
        Formatted stats string.
    """
    total_silence = sum(s.duration for s in conversation.silence_segments)
    total_overtalk = sum(o.duration for o in conversation.overtalk_segments)
    return (
        "## Call Statistics\n"
        f"  duration: {conversation.duration_seconds:.0f}s\n"
        f"  silence_total: {total_silence:.0f}s\n"
        f"  overtalk_total: {total_overtalk:.0f}s"
    )


def _build_prompt(
    transcript: str,
    call_id: str,
    metadata_block: str,
    stats_block: str,
) -> str:
    """Construct the Claude user prompt for semantic analysis.

    Args:
        transcript: Rendered plain-text transcript with turn IDs.
        call_id: Call identifier for context.
        metadata_block: Formatted post-call metadata context.
        stats_block: Call statistics (duration, silence, overtalk).

    Returns:
        Formatted user-turn prompt string.
    """
    metadata_section = f"\n\n{metadata_block}" if metadata_block else ""
    stats_section = f"\n\n{stats_block}"

    return (
        f"## Call ID\n{call_id}\n\n"
        f"## Transcript\n{transcript}"
        f"{metadata_section}"
        f"{stats_section}\n\n"
        f"## Task\n"
        f"Analyse this bank support call. Return a SINGLE flat JSON object with EXACTLY the keys shown "
        f"below — no nesting, no section grouping, no extra keys:\n\n"
        f"{{\n"
        f'  "intent": "one sentence — what the customer called about",\n'
        f'  "summary": "max {config.SEMANTIC_SUMMARY_MAX_WORDS} words — what happened and the outcome",\n'
        f'  "semantic_topics": ["topic1", "topic2"],\n'
        f'  "customer_name_mentioned": true or false,\n'
        f'  "customer_name": "full name if used, else empty string",\n'
        f'  "agent_name": "agent name if introduced, else empty string",\n'
        f'  "resolved": true or false — did agent fully address the request by end of call,\n'
        f'  "identity_verified": false,\n'
        f'  "reference_number_given": true or false,\n'
        f'  "escalation_detected": true or false,\n'
        f'  "repeat_contact": true or false — did customer mention calling before about same issue,\n'
        f'  "fraud_signals": ["verbatim phrase"] or [],\n'
        f'  "detected_moments": [\n'
        f'    {{\n'
        f'      "type": "COMPLAINT|ESCALATION_REQUEST|MANAGER_REQUEST|REPEAT_CONTACT|APOLOGY|'
        f'RESOLUTION_ATTEMPT|UNRESOLVED|FRAUD_SIGNAL|COMPLIANCE_BREACH|POSITIVE_FEEDBACK|HOLD_PLACED",\n'
        f'      "turn_id": integer or null,\n'
        f'      "start_time": float seconds,\n'
        f'      "severity": "LOW|MEDIUM|HIGH|CRITICAL",\n'
        f'      "speaker": "agent|customer|both",\n'
        f'      "description": "one sentence"\n'
        f"    }}\n"
        f"  ],\n"
        f'  "attention_score": integer 0-100 (SUPERVISOR REVIEW URGENCY — 0=routine call no action needed; 100=urgent immediate supervisor intervention required),\n'
        f'  "attention_reasoning": "If score > 10: bullet-list each specific issue needing supervisor attention (what happened, which turn, what was wrong). If score <= 10: one sentence confirming why no action is needed.",\n'
        f'  "qa_score": integer 0-100,\n'
        f'  "qa_reasoning": "one sentence",\n'
        f'  "risk_level": "CRITICAL|HIGH|MEDIUM|LOW"\n'
        f"}}\n\n"
        f"Scoring rules:\n"
        f"- attention_score: caller_partner_rating ≤4 → 40-70+; 5-7 → 20-40; ≥8 → 0-20 (raise for fraud/escalation/compliance)\n"
        f"- qa_score: base from caller_partner_rating (10→100, 5→50, 1→10); adjust for empathy, resolution, script adherence\n"
        f"- risk_level: CRITICAL=fraud/rating≤2/compliance; HIGH=escalation/unresolved/rating 3-4; MEDIUM=repeat/mood drop/rating 5-6; LOW=clean resolved\n"
        f"- COMPLIANCE_BREACH only for: no ref number after formal complaint; action outside authority; materially wrong info; missed escalation procedure\n"
        f"- NEVER flag absence of identity verification (IVR handles it before call connects)\n\n"
        f"Return valid JSON only. No preamble. No explanation. No markdown code fences."
    )


SYSTEM_PROMPT = (
    "You are a call centre quality analyst for a consumer bank. "
    "You receive structured call transcripts with speaker labels and timestamps, "
    "plus post-call survey scores and audio quality labels. "
    "Your job is to understand the semantic content, detect significant moments, "
    "and score the call based on both what was said and the post-call feedback. "
    "IMPORTANT CONTEXT: Customer identity verification is handled automatically by the IVR "
    "system before the call is connected to the agent. Agents are NOT required to re-verify "
    "identity during the call — the IVR has already done it. Never flag absence of identity "
    "verification as a compliance breach. "
    "Always respond in valid JSON only. No preamble. No explanation."
)


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from a response before JSON parsing."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _salvage_partial(raw: str) -> dict:
    """Extract key fields from a truncated JSON string using regex.

    Used when the response is cut off before the closing brace.
    Recovers whatever fields arrived before the truncation point.
    """
    data: dict = {}
    # String fields
    for field in ("intent", "summary", "risk_level", "attention_reasoning", "qa_reasoning",
                  "customer_name", "agent_name"):
        m = re.search(rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        if m:
            data[field] = m.group(1)
    # Integer fields
    for field in ("attention_score", "qa_score"):
        m = re.search(rf'"{field}"\s*:\s*(\d+)', raw)
        if m:
            data[field] = int(m.group(1))
    # Boolean fields
    for field in ("resolved", "escalation_detected", "repeat_contact",
                  "reference_number_given", "customer_name_mentioned", "identity_verified"):
        m = re.search(rf'"{field}"\s*:\s*(true|false)', raw)
        if m:
            data[field] = m.group(1) == "true"
    return data


def _flatten_response(data: dict) -> dict:
    """Flatten a nested DeepSeek response into a single dict.

    DeepSeek groups fields under section labels (NARRATIVE, NAMES, etc.)
    instead of a flat JSON object. Merge any nested dicts into the top level.
    """
    flat: dict = {}
    for key, value in data.items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


def _parse_response(raw: str) -> SemanticResult:
    """Parse the LLM JSON response into a SemanticResult, falling back to defaults.

    Args:
        raw: Raw text response from the LLM.

    Returns:
        SemanticResult populated from JSON, or safe defaults on parse error.
    """
    try:
        data = _flatten_response(json.loads(_strip_code_fences(raw)))
    except json.JSONDecodeError as exc:
        logger.warning("Semantic engine JSON parse error: %s — raw: %.200s", exc, raw)
        data = _salvage_partial(raw)
        if not data:
            return SemanticResult()
        logger.info("Salvaged %d fields from truncated response", len(data))

    resolved_raw = data.get("resolved")
    resolved = bool(resolved_raw) if resolved_raw is not None else None

    # Parse detected moments
    raw_moments = data.get("detected_moments", []) or []
    detected_moments: list[DetectedMoment] = []
    for m in raw_moments:
        if not isinstance(m, dict):
            continue
        try:
            detected_moments.append(DetectedMoment(
                type=str(m.get("type", "")),
                turn_id=int(m["turn_id"]) if m.get("turn_id") is not None else None,
                start_time=float(m.get("start_time", 0.0)),
                severity=str(m.get("severity", "LOW")),
                speaker=str(m.get("speaker", "both")),
                description=str(m.get("description", "")),
            ))
        except (ValueError, TypeError) as exc:
            logger.warning("Could not parse detected_moment %s: %s", m, exc)

    # Clamp scores
    attention = max(0, min(int(data.get("attention_score", 0)), 100))
    qa = max(0, min(int(data.get("qa_score", 100)), 100))

    risk_raw = str(data.get("risk_level", "LOW")).upper()
    risk = risk_raw if risk_raw in ("CRITICAL", "HIGH", "MEDIUM", "LOW") else "LOW"

    return SemanticResult(
        intent=str(data.get("intent", "")),
        summary=str(data.get("summary", "")),
        semantic_topics=list(data.get("semantic_topics", [])),
        customer_name_mentioned=bool(data.get("customer_name_mentioned", False)),
        customer_name=str(data.get("customer_name", "")),
        agent_name=str(data.get("agent_name", "")),
        resolved=resolved,
        identity_verified=bool(data.get("identity_verified", False)),
        reference_number_given=bool(data.get("reference_number_given", False)),
        escalation_detected=bool(data.get("escalation_detected", False)),
        repeat_contact=bool(data.get("repeat_contact", False)),
        fraud_signals=list(data.get("fraud_signals", [])),
        detected_moments=detected_moments,
        attention_score=attention,
        attention_reasoning=str(data.get("attention_reasoning", "")),
        qa_score=qa,
        qa_reasoning=str(data.get("qa_reasoning", "")),
        risk_level=risk,
    )


async def analyse(
    conversation: ConversationModel,
    metadata: dict[str, Any] | None = None,
) -> SemanticResult:
    """Run semantic analysis on a conversation.

    Calls Claude Sonnet with the transcript and post-call metadata to detect
    moments contextually and compute attention/QA scores grounded in survey data.

    If config.USE_CLAUDE_SEMANTIC is False, returns Deepgram-provided intelligence
    with zero-filled scores — no API call.

    Args:
        conversation: Fully populated ConversationModel.
        metadata: Normalised metadata dict from pipeline/metadata.py (surveys, MOS, etc.).

    Returns:
        SemanticResult with narrative, moments, and scores.

    Raises:
        openai.APIError: If the DeepSeek API call fails (only when USE_CLAUDE_SEMANTIC=True).
    """
    if not config.USE_CLAUDE_SEMANTIC:
        logger.info(
            "call_id=%s: semantic engine using Deepgram data (USE_CLAUDE_SEMANTIC=False)",
            conversation.call_id,
        )
        return SemanticResult(
            intent=conversation.deepgram_intent,
            summary=conversation.deepgram_summary,
            semantic_topics=conversation.deepgram_topics,
        )

    client = _get_client()
    transcript = _build_transcript_text(conversation)
    metadata_block = _build_metadata_block(metadata)
    stats_block = _build_conversation_stats(conversation)
    user_prompt = _build_prompt(transcript, conversation.call_id, metadata_block, stats_block)

    logger.info(
        "call_id=%s: calling DeepSeek semantic engine (transcript_len=%d chars, has_metadata=%s)",
        conversation.call_id,
        len(transcript),
        bool(metadata),
    )

    raw_text = ""
    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                max_tokens=config.SEMANTIC_MAX_TOKENS,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except openai.APIError as exc:
            logger.error("call_id=%s: semantic engine API error: %s", conversation.call_id, exc)
            raise

        if response.choices:
            msg = response.choices[0].message
            raw_text = msg.content or ""
            usage = getattr(response, "usage", None)
            if usage:
                thinking = getattr(usage, "completion_tokens_details", None)
                logger.debug(
                    "call_id=%s: DeepSeek usage — prompt=%s completion=%s thinking_detail=%s",
                    conversation.call_id,
                    getattr(usage, "prompt_tokens", "?"),
                    getattr(usage, "completion_tokens", "?"),
                    thinking,
                )
        else:
            raw_text = ""
        if raw_text.strip():
            break
        logger.warning(
            "call_id=%s: DeepSeek returned empty response (attempt %d/3), retrying…",
            conversation.call_id, attempt + 1,
        )
        await asyncio.sleep(2 ** attempt)

    result = _parse_response(raw_text)

    logger.info(
        "call_id=%s: semantic engine done — intent='%.80s' moments=%d attention=%d qa=%d risk=%s",
        conversation.call_id,
        result.intent,
        len(result.detected_moments),
        result.attention_score,
        result.qa_score,
        result.risk_level,
    )

    return result
