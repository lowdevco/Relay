import logging
import re

from django.conf import settings

_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.I),
    re.compile(r"((?:api[_-]?key|access_token|xi-api-key|key|token|secret)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,]+", re.I),
]

_SECRET_SETTINGS = (
    "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GROQ_API_KEY",
    "ELEVENLABS_API_KEY",
    "WHATSAPP_ACCESS_TOKEN",
    "META_APP_SECRET",
    "WHATSAPP_VERIFY_TOKEN",
    "SECRET_KEY",
)


def redact(text: str) -> str:
    if not text:
        return text
    for name in _SECRET_SETTINGS:
        value = getattr(settings, name, "") or ""
        if len(value) >= 6:
            text = text.replace(value, "[REDACTED]")
    for pattern in _PATTERNS:
        text = pattern.sub(r"\1[REDACTED]", text)
    return text


def mask_secret(value: str) -> str:
    """Show only a tiny hint of a configured secret, never the full value."""
    if not value:
        return ""
    if len(value) <= 8:
        return "••••"
    return f"••••{value[-4:]}"


class RedactSecretsFilter(logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover - defensive
            return True
        record.msg = redact(msg)
        record.args = ()
        return True
