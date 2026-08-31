"""
CallRadar pipeline configuration.

All model names, thresholds, and engine settings live here.
Engine files must import from this module — never hardcode values inline.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Model identifiers
# ---------------------------------------------------------------------------

DEEPGRAM_MODEL = "nova-3"
USE_CLAUDE_SEMANTIC: bool = True   # False = use Deepgram summary/intent/topics (no extra API call)

# DeepSeek — used by semantic and evidence engines (OpenAI-compatible API)
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# ---------------------------------------------------------------------------
# Audio processing
# ---------------------------------------------------------------------------

SILENCE_MIN_DURATION_S: float = 2.0          # gap > this between turns is silence
SILENCE_ALERT_DURATION_S: float = 10.0       # silence longer than this raises a Moment
OVERTALK_MIN_DURATION_S: float = 3.0         # simultaneous speech > this is overtalk
OVERTALK_ALERT_DURATION_S: float = 5.0       # overtalk longer than this raises a Moment

# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

TRANSCRIPTION_LANGUAGE: str = "en"

# ---------------------------------------------------------------------------
# Conversation model — topic keywords (used for conversation-level tagging)
# ---------------------------------------------------------------------------

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "card": ["card", "visa", "mastercard", "debit", "credit"],
    "payment": ["payment", "pay", "paid", "charge", "transaction"],
    "fraud": ["fraud", "fraudulent", "scam", "scammed", "unauthorised",
              "unauthorized", "didn't authorise", "didn't make"],
    "account": ["account", "balance", "statement"],
    "complaint": ["complaint", "complain", "unhappy", "dissatisfied",
                  "unacceptable", "disgusted"],
    "transfer": ["transfer", "send money", "wire", "bank transfer"],
    "mortgage": ["mortgage", "remortgage", "rate", "fixed rate"],
    "loan": ["loan", "borrow", "borrowing", "personal loan"],
    "insurance": ["insurance", "policy", "insured", "claim"],
}

# ---------------------------------------------------------------------------
# Behavioural engine thresholds
# ---------------------------------------------------------------------------

MOOD_SHIFT_MIN_DROP: float = 0.3       # minimum sentiment drop to flag a shift
MOOD_SHIFT_HIGH_DROP: float = 0.5     # drop > this → HIGH severity
MOOD_SHIFT_CRITICAL_DROP: float = 0.7  # drop > this → CRITICAL severity

SILENCE_SCORE_THRESHOLD_S: float = 5.0  # silence > this penalised in acoustic score
OVERTALK_SCORE_THRESHOLD_S: float = 3.0  # overtalk > this penalised

# ---------------------------------------------------------------------------
# Evidence engine
# ---------------------------------------------------------------------------

EVIDENCE_MAX_TURNS_PER_MOMENT: int = 5   # ask Claude to select up to this many turns
EVIDENCE_HAIKU_MAX_TOKENS: int = 512
EVIDENCE_SONNET_MAX_TOKENS: int = 1024

# ---------------------------------------------------------------------------
# Semantic engine
# ---------------------------------------------------------------------------

SEMANTIC_SUMMARY_MAX_WORDS: int = 40
SEMANTIC_MAX_TRANSCRIPT_CHARS: int = 12_000  # truncate if call is very long
SEMANTIC_MAX_TOKENS: int = 16384            # deepseek-v4-flash is a reasoning model; thinking tokens eat the budget first
DEEPSEEK_SEMANTIC_TIMEOUT: float = 120.0    # seconds before giving up on a stalled semantic call
DEEPSEEK_EVIDENCE_TIMEOUT: float = 60.0     # seconds before giving up on a stalled evidence call

