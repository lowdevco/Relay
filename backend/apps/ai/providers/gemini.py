"""Google Gemini adapter using the official `google-genai` SDK."""

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from .base import AIProvider, CompletionResult, ProviderError

RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504)


class GeminiProvider(AIProvider):
    name = "gemini"
    label = "Google Gemini"

    def __init__(self, *args, thinking_level="", **kwargs):
        super().__init__(*args, **kwargs)
        self.thinking_level = thinking_level
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(timeout=int(self.timeout * 1000)),
            )
        return self._client

    def _complete(self, system_prompt, user_prompt, *, json_mode=True, max_tokens=1024, temperature=0.4):
        config_kwargs = {
            "system_instruction": system_prompt,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        if self.thinking_level:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=self.thinking_level)
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except genai_errors.APIError as exc:
            status = getattr(exc, "code", None)
            detail = getattr(exc, "message", "") or str(exc)
            raise ProviderError(
                f"Gemini API error ({status}): {detail[:200]}",
                code=f"gemini_{status or 'error'}",
                retryable=status in RETRYABLE_STATUS,
                http_status=status,
            ) from exc
        except Exception as exc:  # network errors, timeouts
            raise ProviderError(
                f"Gemini request failed: {exc.__class__.__name__}", code="gemini_network", retryable=True
            ) from exc

        finish = ""
        if getattr(response, "candidates", None):
            finish = str(getattr(response.candidates[0], "finish_reason", "") or "")
        text = getattr(response, "text", None) or ""
        if not text:
            raise ProviderError(f"Gemini returned no text (finish_reason={finish or 'unknown'}).", code="gemini_empty")
        usage = getattr(response, "usage_metadata", None)
        return CompletionResult(
            text=text,
            model=self.model,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            raw_finish_reason=finish,
        )
