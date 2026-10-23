"""Groq adapter (GroqCloud, OpenAI-compatible API: https://console.groq.com/docs/openai).

GroqCloud has an official free plan with per-model rate limits (e.g. 30 requests/min,
1K requests/day, 8K tokens/min for openai/gpt-oss-120b, Oct 2026). 429 responses are
retried after the server's retry-after delay.
"""

from .openai_compat import OpenAICompatibleProvider

# Models that accept `reasoning_effort` (https://console.groq.com/docs/reasoning).
REASONING_MODELS = ("openai/gpt-oss-", "qwen/")


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    label = "Groq"
    default_base_url = "https://api.groq.com/openai/v1"

    def __init__(self, *args, reasoning_effort="low", **kwargs):
        super().__init__(*args, **kwargs)
        self.reasoning_effort = reasoning_effort

    def extra_body(self):
        if not self.model.startswith(REASONING_MODELS):
            return {}
        body = {
            # JSON mode requires "parsed" or "hidden"; hidden keeps reasoning out of the
            # response entirely (we never store chain-of-thought).
            "reasoning_format": "hidden",
        }
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort  # low = fewer tokens against free-plan limits
        return body
