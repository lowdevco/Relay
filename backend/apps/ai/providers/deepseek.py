"""DeepSeek adapter (OpenAI-compatible Chat Completions API, https://api-docs.deepseek.com/)."""

from .openai_compat import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    label = "DeepSeek"
    default_base_url = "https://api.deepseek.com"

    def extra_body(self):
        # Thinking mode is enabled by default. We only need the structured answer and
        # never store reasoning, so disable it (this also makes temperature effective).
        return {"thinking": {"type": "disabled"}}
