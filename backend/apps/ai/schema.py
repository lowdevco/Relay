"""Validators for structured model output. Each returns (cleaned_dict, errors)."""

import re

ALLOWED_ACTIONS = ("reply", "clarify", "escalate", "no_reply")
REASON_CODES = (
    "known_information",
    "clarification_needed",
    "missing_information",
    "human_requested",
    "complaint",
    "refund_or_dispute",
    "commitment_requested",
    "sensitive_topic",
    "greeting",
    "small_talk",
    "out_of_scope",
    "other",
)
EMOJI_LEVELS = ("none", "rare", "moderate", "frequent")

_SLUG = re.compile(r"[^a-z0-9_]+")


def _slug(value, default="other", max_len=64):
    if not isinstance(value, str) or not value.strip():
        return default
    s = _SLUG.sub("_", value.strip().lower()).strip("_")
    return (s or default)[:max_len]


def _bool(data, key, errors, default=None):
    v = data.get(key, default)
    if isinstance(v, bool):
        return v
    if v is None and default is not None:
        return default
    errors.append(f"'{key}' must be a boolean")
    return bool(v)


def _number(data, key, errors, lo=0.0, hi=1.0):
    v = data.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        errors.append(f"'{key}' must be a number between {lo} and {hi}")
        return lo
    if not lo <= float(v) <= hi:
        errors.append(f"'{key}' must be between {lo} and {hi}")
    return max(lo, min(hi, float(v)))


def _str_list(value, max_items=10, max_len=200):
    if not isinstance(value, list):
        return []
    return [str(x)[:max_len] for x in value if isinstance(x, (str, int, float))][:max_items]


def make_reply_validator(allowed_knowledge_ids, max_chars):
    allowed = {str(i) for i in allowed_knowledge_ids}

    def validate(data):
        errors = []
        cleaned = {}
        cleaned["intent"] = _slug(data.get("intent"))
        lang = data.get("language")
        cleaned["language"] = lang.strip()[:16] if isinstance(lang, str) and lang.strip() else "und"

        action = data.get("suggested_action")
        if action not in ALLOWED_ACTIONS:
            errors.append(f"'suggested_action' must be one of {', '.join(ALLOWED_ACTIONS)}")
        cleaned["suggested_action"] = action if action in ALLOWED_ACTIONS else "escalate"

        text = data.get("reply_text")
        if not isinstance(text, str):
            errors.append("'reply_text' must be a string")
            text = ""
        text = text.strip()
        if not text and cleaned["suggested_action"] != "no_reply":
            errors.append("'reply_text' must not be empty")
        if len(text) > max_chars:
            errors.append(f"'reply_text' exceeds {max_chars} characters")
        cleaned["reply_text"] = text

        cleaned["confidence"] = _number(data, "confidence", errors)
        cleaned["needs_human_review"] = _bool(data, "needs_human_review", errors)
        reason = _slug(data.get("reason_code"))
        cleaned["reason_code"] = reason if reason in REASON_CODES else "other"
        cleaned["voice_note_eligible"] = _bool(data, "voice_note_eligible", errors, default=False)

        refs = data.get("knowledge_references", [])
        if not isinstance(refs, list):
            errors.append("'knowledge_references' must be a list")
            refs = []
        valid_refs, invalid_refs = [], []
        for r in refs:
            (valid_refs if str(r) in allowed else invalid_refs).append(str(r))
        cleaned["knowledge_references"] = valid_refs
        cleaned["invalid_knowledge_references"] = invalid_refs

        rationale = data.get("rationale", "")
        cleaned["rationale"] = rationale.strip()[:300] if isinstance(rationale, str) else ""
        return cleaned, errors

    return validate


def validate_classification(data):
    errors = []
    sentiment = data.get("sentiment")
    urgency = data.get("urgency")
    cleaned = {
        "intent": _slug(data.get("intent")),
        "language": (data.get("language") or "und")[:16] if isinstance(data.get("language"), str) else "und",
        "sentiment": sentiment if sentiment in ("positive", "neutral", "negative") else "neutral",
        "urgency": urgency if urgency in ("low", "normal", "high") else "normal",
        "wants_human": _bool(data, "wants_human", errors, default=False),
        "topics": _str_list(data.get("topics"), 8, 60),
    }
    if "intent" not in data:
        errors.append("'intent' is required")
    return cleaned, errors


def validate_summary(data):
    errors = []
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("'summary' must be a non-empty string")
        summary = ""
    return {
        "summary": summary.strip()[:2000],
        "customer_facts": _str_list(data.get("customer_facts"), 10, 200),
        "open_questions": _str_list(data.get("open_questions"), 10, 200),
    }, errors


def validate_evaluation(data):
    errors = []
    verdict = data.get("verdict")
    if verdict not in ("pass", "fail"):
        errors.append("'verdict' must be 'pass' or 'fail'")
    return {
        "verdict": verdict if verdict in ("pass", "fail") else "fail",
        "grounded": _bool(data, "grounded", errors),
        "unsupported_claims": _str_list(data.get("unsupported_claims"), 10, 200),
        "commitments": _str_list(data.get("commitments"), 10, 200),
        "tone_ok": _bool(data, "tone_ok", errors, default=True),
        "score": _number(data, "score", errors),
    }, errors


def validate_style_profile(data):
    errors = []

    def lvl(key):
        v = data.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            errors.append(f"'{key}' must be a number 1-5")
            return 3
        return int(max(1, min(5, round(v))))

    emoji = data.get("emoji_frequency")
    words = data.get("average_reply_words")
    return {
        "typical_greetings": _str_list(data.get("typical_greetings"), 8, 80),
        "formality": lvl("formality"),
        "friendliness": lvl("friendliness"),
        "common_vocabulary": _str_list(data.get("common_vocabulary"), 20, 40),
        "average_reply_words": int(words) if isinstance(words, (int, float)) and not isinstance(words, bool) else 0,
        "emoji_frequency": emoji if emoji in EMOJI_LEVELS else "rare",
        "languages": _str_list(data.get("languages"), 5, 30),
        "follow_up_patterns": _str_list(data.get("follow_up_patterns"), 8, 120),
        "notes": str(data.get("notes") or "")[:500],
    }, errors
