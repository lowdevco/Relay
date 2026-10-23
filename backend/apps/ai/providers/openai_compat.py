"""Shared adapter for providers exposing an OpenAI-compatible Chat Completions API."""

import requests

from .base import AIProvider, CompletionResult, ProviderError

RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504)


class OpenAICompatibleProvider(AIProvider):
    """Subclasses set `name`, `label`, `default_base_url` and may add provider-specific body fields."""

    default_base_url = ""

    def __init__(self, *args, base_url=None, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.session = session or requests.Session()

    @property
    def endpoint(self):
        return f"{self.base_url}/chat/completions"

    def extra_body(self):
        """Provider-specific request fields."""
        return {}

    def _complete(self, system_prompt, user_prompt, *, json_mode=True, max_tokens=1024, temperature=0.4):
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            **self.extra_body(),
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        code = self.name
        try:
            resp = self.session.post(
                self.endpoint,
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
        except requests.Timeout as exc:
            raise ProviderError(f"{self.label} request timed out.", code=f"{code}_timeout", retryable=True) from exc
        except requests.RequestException as exc:
            raise ProviderError(
                f"{self.label} request failed: {exc.__class__.__name__}", code=f"{code}_network", retryable=True
            ) from exc

        if resp.status_code != 200:
            try:
                err = resp.json().get("error")
                detail = err.get("message", "") if isinstance(err, dict) else str(err or "")
            except (ValueError, AttributeError):
                detail = resp.text[:200]
            if resp.status_code == 429:
                detail = f"rate limit reached (check your plan's limits). {detail}"
            err = ProviderError(
                f"{self.label} API error ({resp.status_code}): {detail[:200]}",
                code=f"{code}_{resp.status_code}",
                retryable=resp.status_code in RETRYABLE_STATUS,
                http_status=resp.status_code,
            )
            try:
                err.retry_after = float((getattr(resp, "headers", None) or {}).get("retry-after") or 0)
            except (TypeError, ValueError):
                err.retry_after = 0
            raise err
        try:
            data = resp.json()
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.label} returned an unexpected response shape.", code=f"{code}_bad_response") from exc
        if not text.strip():
            raise ProviderError(f"{self.label} returned empty content.", code=f"{code}_empty", retryable=True)
        usage = data.get("usage") or {}
        return CompletionResult(
            text=text,
            model=data.get("model", self.model),
            input_tokens=usage.get("prompt_tokens", 0) or 0,
            output_tokens=usage.get("completion_tokens", 0) or 0,
            raw_finish_reason=choice.get("finish_reason") or "",
        )
