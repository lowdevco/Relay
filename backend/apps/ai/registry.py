"""Provider allowlist + construction from server-side configuration (.env via python-decouple)."""

from django.conf import settings

from .providers.base import ProviderNotConfigured
from .providers.deepseek import DeepSeekProvider
from .providers.gemini import GeminiProvider
from .providers.groq import GroqProvider

SUPPORTED = {
    "gemini": GeminiProvider,
    "deepseek": DeepSeekProvider,
    "groq": GroqProvider,
}

# provider -> (settings prefix used for <PREFIX>_API_KEY / <PREFIX>_MODEL)
_PREFIX = {"gemini": "GEMINI", "deepseek": "DEEPSEEK", "groq": "GROQ"}


def _config(name):
    if name not in SUPPORTED:
        raise ValueError(f"Unsupported AI provider: {name}")
    prefix = _PREFIX[name]
    return {
        "api_key": getattr(settings, f"{prefix}_API_KEY", ""),
        "model": getattr(settings, f"{prefix}_MODEL", ""),
        "prefix": prefix,
    }


def provider_status(name):
    cfg = _config(name)
    missing = []
    if not cfg["api_key"]:
        missing.append(f"{cfg['prefix']}_API_KEY")
    if not cfg["model"]:
        missing.append(f"{cfg['prefix']}_MODEL")
    return {
        "provider": name,
        "label": SUPPORTED[name].label,
        "configured": not missing,
        "model": cfg["model"],
        "missing": missing,
    }


def get_provider(name):
    status = provider_status(name)
    if not status["configured"]:
        raise ProviderNotConfigured(SUPPORTED[name].label, status["missing"])
    cfg = _config(name)
    common = dict(
        api_key=cfg["api_key"],
        model=cfg["model"],
        timeout=settings.AI_REQUEST_TIMEOUT,
        max_retries=settings.AI_MAX_RETRIES,
    )
    if name == "gemini":
        return GeminiProvider(thinking_level=settings.GEMINI_THINKING_LEVEL, **common)
    if name == "deepseek":
        return DeepSeekProvider(base_url=settings.DEEPSEEK_BASE_URL, **common)
    return GroqProvider(base_url=settings.GROQ_BASE_URL, reasoning_effort=settings.GROQ_REASONING_EFFORT, **common)
