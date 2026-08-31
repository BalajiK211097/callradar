"""
Deepgram Nova-3 ingestion — single API call for the full call intelligence.

Replaces: splitter.py + transcriber.py + entities.py

Sends the raw stereo MP3 to Deepgram with multichannel=True so channel 0
(left) = agent and channel 1 (right) = customer.  All intelligence features
(sentiment, topics, summary, intents, entities) are requested in the same call.
Silence and overtalk are reconstructed from utterance timestamp gaps.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from deepgram import DeepgramClient, PrerecordedOptions
from dotenv import load_dotenv

load_dotenv()

from pipeline import config
from pipeline.models import OvertalkSegment, SilenceSegment

logger = logging.getLogger(__name__)

_client: DeepgramClient | None = None


def _get_client() -> DeepgramClient:
    """Return (and cache) the Deepgram client singleton."""
    global _client
    if _client is None:
        _client = DeepgramClient(os.environ["DEEPGRAM_API_KEY"])
    return _client


@dataclass
class UtteranceSegment:
    """A single utterance from one audio channel, enriched with Deepgram sentiment."""

    channel: int            # 0 = agent, 1 = customer
    start: float
    end: float
    transcript: str
    confidence: float
    sentiment_label: str    # "positive" | "negative" | "neutral"
    sentiment_score: float  # composite mapped to [-1, +1]


@dataclass
class DeepgramResult:
    """Everything returned by the single Deepgram multichannel API call."""

    utterances: list[UtteranceSegment]
    entities: list[dict]              # raw Deepgram entity dicts
    topics: list[str]
    summary: str
    intent: str
    duration_seconds: float
    silence_segments: list[SilenceSegment] = field(default_factory=list)
    overtalk_segments: list[OvertalkSegment] = field(default_factory=list)


def _composite_sentiment(label: str, score: float) -> float:
    """Map Deepgram label + confidence to a [-1, +1] composite score."""
    if label == "positive":
        return round(score, 4)
    if label == "negative":
        return round(-score, 4)
    return 0.0


def _extract_topics(response) -> list[str]:
    """Safely extract topic strings from a Deepgram response."""
    topics: list[str] = []
    try:
        if not response.results or not response.results.topics:
            return topics
        segments = getattr(response.results.topics, "segments", None) or response.results.topics
        for segment in segments:
            for item in (getattr(segment, "topics", []) or []):
                t = getattr(item, "topic", None)
                if t:
                    topics.append(t)
    except Exception:
        pass
    return topics


def _extract_summary(response) -> str:
    """Safely extract the short summary from a Deepgram response."""
    try:
        if response.results and response.results.summary:
            return getattr(response.results.summary, "short", "") or ""
    except Exception:
        pass
    return ""


def _extract_intent(response) -> str:
    """Safely extract the top intent string from a Deepgram response."""
    try:
        if response.results and response.results.intents:
            segments = getattr(response.results.intents, "segments", []) or []
            if segments:
                return getattr(segments[0], "intent", "") or ""
    except Exception:
        pass
    return ""


def _extract_entities(response) -> list[dict]:
    """Collect entity dicts from all channels in a Deepgram response."""
    entities: list[dict] = []
    try:
        if not response.results or not response.results.channels:
            return entities
        for ch_idx, channel in enumerate(response.results.channels):
            alt = (channel.alternatives or [None])[0]
            if not alt:
                continue
            ent_data = getattr(alt, "entities", None)
            if not ent_data:
                continue
            for e in (getattr(ent_data, "values", []) or []):
                entities.append(
                    {
                        "label": getattr(e, "label", "MISC"),
                        "value": getattr(e, "value", ""),
                        "confidence": getattr(e, "confidence", 0.0),
                        "channel": ch_idx,
                    }
                )
    except Exception:
        pass
    return entities


def _detect_silence_and_overtalk(
    utterances: list[UtteranceSegment],
) -> tuple[list[SilenceSegment], list[OvertalkSegment]]:
    """Reconstruct silence and overtalk regions from utterance timestamps.

    Silence  = gap > SILENCE_MIN_DURATION_S where neither channel is active.
    Overtalk = overlap > OVERTALK_MIN_DURATION_S where both channels speak simultaneously.

    Args:
        utterances: All utterances from both channels.

    Returns:
        (silence_segments, overtalk_segments)
    """
    sorted_all = sorted(utterances, key=lambda u: u.start)

    silence: list[SilenceSegment] = []
    prev_end = 0.0
    for utt in sorted_all:
        gap = utt.start - prev_end
        if gap > config.SILENCE_MIN_DURATION_S:
            silence.append(SilenceSegment(start=prev_end, end=utt.start))
        prev_end = max(prev_end, utt.end)

    agent_utts = [u for u in utterances if u.channel == 0]
    cust_utts = [u for u in utterances if u.channel == 1]
    overtalk: list[OvertalkSegment] = []
    for a in agent_utts:
        for c in cust_utts:
            overlap_start = max(a.start, c.start)
            overlap_end = min(a.end, c.end)
            if overlap_end - overlap_start > config.OVERTALK_MIN_DURATION_S:
                overtalk.append(OvertalkSegment(start=overlap_start, end=overlap_end))

    return silence, overtalk


async def ingest(call_id: str, mp3_path: Path | str) -> DeepgramResult:
    """Send the stereo MP3 to Deepgram Nova-3 and return the full intelligence result.

    One API call returns transcription for both channels plus sentiment,
    entities, topics, summary, and intent.

    Accepts either a local Path or an HTTPS presigned URL (e.g. from S3).
    When a URL is passed the audio is streamed directly by Deepgram — no local
    download required.

    Args:
        call_id: Unique call identifier (for logging).
        mp3_path: Path to the local stereo MP3, or an HTTPS URL Deepgram can fetch.

    Returns:
        DeepgramResult with utterances, entities, topics, summary, intent,
        silence segments, and overtalk segments.

    Raises:
        FileNotFoundError: If a local path is given but the file does not exist.
        RuntimeError: If the Deepgram API call fails.
    """
    options = PrerecordedOptions(
        model=config.DEEPGRAM_MODEL,
        language=config.TRANSCRIPTION_LANGUAGE,
        multichannel=True,
        utterances=True,
        sentiment=True,
        topics=True,
        summarize="v2",
        intents=True,
        detect_entities=True,
        smart_format=True,
    )

    try:
        is_url = isinstance(mp3_path, str) and mp3_path.startswith("https://")
        if is_url:
            logger.info("call_id=%s: sending S3 URL to Deepgram Nova-3 (multichannel + intelligence)", call_id)
            source: dict = {"url": mp3_path}
        else:
            local = Path(mp3_path) if isinstance(mp3_path, str) else mp3_path
            if not local.exists():
                raise FileNotFoundError(f"MP3 not found: {local}")
            logger.info("call_id=%s: sending to Deepgram Nova-3 (multichannel + intelligence)", call_id)
            with open(local, "rb") as f:
                audio_data = f.read()
            source = {"buffer": audio_data}

        client = _get_client().listen.asyncprerecorded.v("1")
        last_exc: Exception | None = None
        for attempt in range(4):
            try:
                if is_url:
                    response = await client.transcribe_url(source, options)
                else:
                    response = await client.transcribe_file(source, options)
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if "429" in str(exc):
                    wait = 10 * (2 ** attempt)
                    logger.warning(
                        "call_id=%s: Deepgram 429 rate limit (attempt %d/4), retrying in %ds",
                        call_id, attempt + 1, wait,
                    )
                    import asyncio as _asyncio
                    await _asyncio.sleep(wait)
                else:
                    break
        if last_exc is not None:
            raise last_exc
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Deepgram ingest failed for call_id={call_id}: {exc}"
        ) from exc

    raw_utterances = []
    if response.results and response.results.utterances:
        raw_utterances = response.results.utterances

    utterances: list[UtteranceSegment] = []
    for utt in raw_utterances:
        channel = int(getattr(utt, "channel", 0))
        label = getattr(utt, "sentiment", "neutral") or "neutral"
        raw_score = float(getattr(utt, "sentiment_score", 0.0) or 0.0)
        utterances.append(
            UtteranceSegment(
                channel=channel,
                start=float(utt.start),
                end=float(utt.end),
                transcript=(utt.transcript or "").strip(),
                confidence=round(float(getattr(utt, "confidence", 1.0)), 4),
                sentiment_label=label,
                sentiment_score=_composite_sentiment(label, raw_score),
            )
        )

    duration = 0.0
    try:
        if response.metadata and hasattr(response.metadata, "duration"):
            duration = float(response.metadata.duration)
    except Exception:
        pass
    if duration == 0.0 and utterances:
        duration = max(u.end for u in utterances)

    silence_segs, overtalk_segs = _detect_silence_and_overtalk(utterances)

    result = DeepgramResult(
        utterances=utterances,
        entities=_extract_entities(response),
        topics=_extract_topics(response),
        summary=_extract_summary(response),
        intent=_extract_intent(response),
        duration_seconds=round(duration, 2),
        silence_segments=silence_segs,
        overtalk_segments=overtalk_segs,
    )

    logger.info(
        "call_id=%s: Deepgram complete — %d utterances, %d entities, "
        "topics=%s, summary_len=%d, intent='%.60s'",
        call_id,
        len(utterances),
        len(result.entities),
        result.topics,
        len(result.summary),
        result.intent,
    )

    return result
