"""Deterministic business rules applied on top of (uncalibrated) model output."""

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.utils import timezone

SENSITIVE_INTENT_WORDS = (
    "refund", "complaint", "dispute", "chargeback", "payment", "legal", "lawsuit", "medical",
    "emergency", "harassment", "threat", "cancel", "invoice", "contract",
)
ESCALATION_REASON_CODES = {"human_requested", "complaint", "refund_or_dispute", "sensitive_topic", "commitment_requested"}

COMMITMENT_PATTERNS = re.compile(
    r"\b("
    r"(your|the) (booking|appointment|reservation|order) (is|has been) (confirmed|booked|placed|scheduled)"
    r"|i('| ha)ve (booked|refunded|processed|cancelled|canceled|scheduled|reserved|sent you|issued)"
    r"|we('| ha)ve (booked|refunded|processed|cancelled|canceled|scheduled|reserved|issued)"
    r"|refund (has been|is|was) (issued|processed|approved|sent)"
    r"|payment (has been |is |was )?(received|confirmed|processed)"
    r"|(we|i) guarantee|guaranteed"
    r"|(you('| wi)ll|you will) (get|receive) a (full )?refund"
    r"|free of charge|discount (of|for you)"
    r")\b",
    re.I,
)
LEAK_PATTERNS = re.compile(r"(untrusted_|hard rules|system prompt|<business_knowledge>|my instructions)", re.I)
NUMBER = re.compile(r"\d+")

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def effective_mode(conversation, automation):
    """Returns 'off' | 'manual' | 'approval' | 'automatic'. Enforced server-side."""
    if not automation.automation_enabled:
        return "off"
    if conversation.human_takeover or conversation.automation_paused:
        return "off"
    override = conversation.automation_override
    if override == "off":
        return "off"
    if override in ("manual", "approval", "automatic"):
        return override
    return automation.mode


def keyword_flags(text, automation):
    lowered = (text or "").lower()
    escalate = [k for k in (automation.escalation_keywords or []) if k and k.lower() in lowered]
    review = [k for k in (automation.review_topics or []) if k and k.lower() in lowered]
    return {"escalate": escalate, "review": review}


def _numbers(text):
    return {int(n) for n in NUMBER.findall(text or "")}


def unsupported_figures(reply_text, allowed_texts):
    """Numbers in the reply that appear in none of the allowed sources (knowledge, customer text)."""
    allowed = set()
    for t in allowed_texts:
        allowed |= _numbers(t)
    return sorted(_numbers(reply_text) - allowed)


def review_reasons(reply, *, customer_text, knowledge_texts, automation, history_texts=()):
    """Reasons a reply must not be sent automatically. Empty list = eligible."""
    reasons = []
    if reply.get("needs_human_review"):
        reasons.append("model_requested_review")
    if reply.get("suggested_action") not in ("reply", "clarify"):
        reasons.append(f"action_{reply.get('suggested_action')}")
    if float(reply.get("confidence", 0)) < automation.confidence_threshold:
        reasons.append("low_confidence")
    if reply.get("invalid_knowledge_references"):
        reasons.append("invalid_knowledge_reference")
    if reply.get("reason_code") in ESCALATION_REASON_CODES or reply.get("reason_code") == "missing_information":
        reasons.append(f"reason_{reply.get('reason_code')}")
    intent = reply.get("intent", "")
    if any(w in intent for w in SENSITIVE_INTENT_WORDS):
        reasons.append("sensitive_intent")
    if automation.allowed_auto_intents and intent not in automation.allowed_auto_intents:
        reasons.append("intent_not_allowed_for_auto")
    text = reply.get("reply_text", "")
    if COMMITMENT_PATTERNS.search(text):
        reasons.append("possible_commitment")
    if LEAK_PATTERNS.search(text):
        reasons.append("possible_instruction_leak")
    figures = unsupported_figures(text, [customer_text, *knowledge_texts, *history_texts])
    if figures:
        reasons.append("unverified_figures")
    for kw in keyword_flags(customer_text, automation)["review"]:
        reasons.append(f"review_topic:{kw}")
    return reasons


def should_escalate(reply, flags):
    return bool(
        flags["escalate"]
        or reply.get("suggested_action") == "escalate"
        or reply.get("reason_code") in ESCALATION_REASON_CODES
    )


def within_operating_hours(automation, tz_name, now=None):
    if not automation.operating_hours_enabled:
        return True
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
    local = (now or timezone.now()).astimezone(tz)
    ranges = (automation.operating_hours or {}).get(DAYS[local.weekday()], [])
    current = local.strftime("%H:%M")
    for rng in ranges:
        try:
            start, end = rng
            datetime.strptime(start, "%H:%M")
            datetime.strptime(end, "%H:%M")
        except (ValueError, TypeError):
            continue
        if start <= current < end:
            return True
    return False
