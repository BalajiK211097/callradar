"""
Conversation model builder.

Assembles a ConversationModel from a DeepgramResult, mapping utterances
to Turn objects, computing participant statistics, reconstructing entities
from Deepgram data, and merging Deepgram topics with keyword-based topics.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pipeline import config
from pipeline.audio_intelligence.deepgram_ingest import DeepgramResult
from pipeline.models import ConversationModel, Entity, Participant, Turn

logger = logging.getLogger(__name__)

_CHANNEL_ROLE: dict[int, str] = {0: "agent", 1: "customer"}

# Patterns for extracting names from call-centre introductions.
# Matched against the first few turns of the relevant speaker.
_NAME_PATTERNS = [
    re.compile(r"my name is ([A-Z][a-z]+(?: [A-Z][a-z]+)*)", re.IGNORECASE),
    re.compile(r"this is ([A-Z][a-z]+(?: [A-Z][a-z]+)*)", re.IGNORECASE),
    re.compile(r"i(?:'m| am) ([A-Z][a-z]+(?: [A-Z][a-z]+)*)", re.IGNORECASE),
    re.compile(r"my name's ([A-Z][a-z]+(?: [A-Z][a-z]+)*)", re.IGNORECASE),
]

# Words that look like names but aren't — filter these out
_NAME_STOPWORDS = {
    "calling", "here", "available", "sorry", "glad", "happy",
    "sure", "ok", "okay", "hi", "hello", "yes", "no",
}


def _extract_name_from_turns(turns: list[Turn], role: str, scan_turns: int = 4) -> str:
    """Scan the first few turns from a given speaker for a name introduction.

    Args:
        turns: All turns in the conversation.
        role: Speaker role to scan ('agent' or 'customer').
        scan_turns: How many of the speaker's turns to check.

    Returns:
        Extracted name string, or empty string if not found.
    """
    speaker_turns = [t for t in turns if t.speaker == role][:scan_turns]
    for turn in speaker_turns:
        for pattern in _NAME_PATTERNS:
            match = pattern.search(turn.text)
            if match:
                candidate = match.group(1).strip()
                if candidate.lower() not in _NAME_STOPWORDS and len(candidate) >= 2:
                    return candidate
    return ""


def _build_turns(utterances: list, call_id: str) -> list[Turn]:
    """Merge per-channel Deepgram utterances into a time-sorted Turn list.

    Consecutive utterances from the same channel with a gap smaller than
    SILENCE_MIN_DURATION_S are merged into one Turn.  Sentiment score is
    averaged across merged utterances.

    Args:
        utterances: UtteranceSegment list from DeepgramResult.
        call_id: Unique call identifier.

    Returns:
        Sorted list of Turn objects with sentiment_score populated.
    """
    sorted_utts = sorted(utterances, key=lambda u: u.start)
    turns: list[Turn] = []
    turn_id = 0
    i = 0

    while i < len(sorted_utts):
        utt = sorted_utts[i]
        merged_text = utt.transcript
        merged_end = utt.end
        merged_sentiment = utt.sentiment_score
        merge_count = 1
        j = i + 1

        while j < len(sorted_utts):
            nxt = sorted_utts[j]
            gap = nxt.start - merged_end
            if nxt.channel == utt.channel and gap < config.SILENCE_MIN_DURATION_S:
                merged_text = merged_text + " " + nxt.transcript
                merged_end = nxt.end
                merged_sentiment += nxt.sentiment_score
                merge_count += 1
                j += 1
            else:
                break

        turns.append(
            Turn(
                id=turn_id,
                call_id=call_id,
                speaker=_CHANNEL_ROLE.get(utt.channel, "agent"),
                start_time=utt.start,
                end_time=merged_end,
                text=merged_text.strip(),
                word_count=len(merged_text.split()),
                sentiment_score=round(merged_sentiment / merge_count, 4),
            )
        )
        turn_id += 1
        i = j

    return turns


def _build_participants(
    turns: list[Turn],
    metadata: dict[str, Any] | None,
) -> list[Participant]:
    """Compute per-speaker stats and resolve names from metadata or transcript.

    Name resolution priority:
      1. metadata dict ("agent_name" / "customer_name") — most reliable
      2. Transcript pattern match ("My name is X", "This is X") — fallback
      3. Generic role label ("Agent" / "Customer") — last resort

    Args:
        turns: All turns in the conversation.
        metadata: Optional dict with "agent_name" and "customer_name" keys.

    Returns:
        List of Participant objects.
    """
    stats: dict[str, dict] = {}
    for turn in turns:
        role = turn.speaker
        if role not in stats:
            stats[role] = {"talk_time_seconds": 0.0, "turn_count": 0}
        stats[role]["talk_time_seconds"] += turn.end_time - turn.start_time
        stats[role]["turn_count"] += 1

    # Priority 1: metadata
    name_map: dict[str, str] = {}
    if metadata:
        name_map = {
            "agent": metadata.get("agent_name", "") or "",
            "customer": metadata.get("customer_name", "") or "",
        }

    # Priority 2: transcript pattern match for any role still missing a name
    for role in stats:
        if not name_map.get(role):
            extracted = _extract_name_from_turns(turns, role)
            if extracted:
                name_map[role] = extracted
                logger.info("Extracted %s name from transcript: %r", role, extracted)

    participants: list[Participant] = []
    for role, data in stats.items():
        name = name_map.get(role) or role.capitalize()
        participants.append(
            Participant(
                name=name,
                role=role,
                talk_time_seconds=round(float(data["talk_time_seconds"]), 2),
                turn_count=int(data["turn_count"]),
            )
        )
    return participants


def _map_entities(raw_entities: list[dict], turns: list[Turn]) -> list[Entity]:
    """Map Deepgram entity dicts to Entity model objects.

    Matches entity text against turn transcripts to find the owning turn and
    character positions within it.

    Args:
        raw_entities: List of Deepgram entity dicts with "value", "label", "channel".
        turns: All Turn objects (used to locate entity text).

    Returns:
        List of Entity objects.
    """
    entities: list[Entity] = []
    for raw in raw_entities:
        entity_text = raw.get("value", "")
        entity_label = raw.get("label", "MISC")
        entity_channel = raw.get("channel", 0)
        speaker_role = _CHANNEL_ROLE.get(entity_channel, "agent")

        if not entity_text:
            continue

        for turn in turns:
            if turn.speaker != speaker_role:
                continue
            idx = turn.text.lower().find(entity_text.lower())
            if idx != -1:
                entities.append(
                    Entity(
                        text=entity_text,
                        label=entity_label,
                        start_char=idx,
                        end_char=idx + len(entity_text),
                        turn_id=turn.id,
                    )
                )
                break

    return entities


def _identify_topics(turns: list[Turn], deepgram_topics: list[str]) -> list[str]:
    """Merge Deepgram topics with keyword-matched topics from config.TOPIC_KEYWORDS.

    Args:
        turns: All turns (used for keyword search).
        deepgram_topics: Topic strings returned by Deepgram.

    Returns:
        Sorted deduplicated list of topic label strings.
    """
    full_text = " ".join(t.text.lower() for t in turns)
    found: set[str] = set(deepgram_topics)

    for topic, keywords in config.TOPIC_KEYWORDS.items():
        if any(kw in full_text for kw in keywords):
            found.add(topic)

    return sorted(found)


def build(
    ingest_result: DeepgramResult,
    call_id: str,
    metadata: dict[str, Any] | None = None,
) -> ConversationModel:
    """Assemble a ConversationModel from a DeepgramResult.

    Args:
        ingest_result: Output from deepgram_ingest.ingest().
        call_id: Unique call identifier.
        metadata: Optional dict with "agent_name", "customer_name", etc.

    Returns:
        Fully populated ConversationModel with entities, sentiment scores on
        every Turn, and Deepgram intelligence fields (deepgram_summary,
        deepgram_intent, deepgram_topics).

    Raises:
        ValueError: If no turns are produced from the utterances.
    """
    turns = _build_turns(ingest_result.utterances, call_id)
    if not turns:
        raise ValueError(f"No turns produced for call_id={call_id!r}")

    participants = _build_participants(turns, metadata)
    entities = _map_entities(ingest_result.entities, turns)
    topics = _identify_topics(turns, ingest_result.topics)

    model = ConversationModel(
        call_id=call_id,
        turns=turns,
        entities=entities,
        participants=participants,
        topics=topics,
        duration_seconds=round(ingest_result.duration_seconds, 2),
        silence_segments=ingest_result.silence_segments,
        overtalk_segments=ingest_result.overtalk_segments,
        deepgram_summary=ingest_result.summary,
        deepgram_intent=ingest_result.intent,
        deepgram_topics=ingest_result.topics,
    )

    logger.info(
        "call_id=%s: ConversationModel built — %d turns, %d entities, "
        "%d topics, duration=%.1fs, %d silence, %d overtalk",
        call_id,
        len(turns),
        len(entities),
        len(topics),
        model.duration_seconds,
        len(model.silence_segments),
        len(model.overtalk_segments),
    )

    return model
