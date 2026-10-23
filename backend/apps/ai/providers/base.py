"""
Shared AI provider interface.

Adapters implement only `_complete()` (request formatting, response parsing and
error mapping for their API). The operations below are provider-agnostic and are
what the conversation/automation services call. Services never import an SDK.
"""

import json
import re
import time
from dataclasses import dataclass, field


class ProviderError(Exception):
    def __init__(self, message, code="provider_error", retryable=False, http_status=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.http_status = http_status
        self.completion = None
        self.retry_after = 0  # seconds the server asked us to wait (e.g. 429 retry-after)
        self.attempts = 1
        self.validation_errors = []


class ProviderNotConfigured(ProviderError):
    def __init__(self, provider_label, missing):
        super().__init__(
            f"{provider_label} is not configured on the server (missing: {', '.join(missing)}).",
            code="provider_not_configured",
        )
        self.missing = missing


@dataclass
class CompletionResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    raw_finish_reason: str = ""


@dataclass
class OperationResult:
    data: dict
    completion: CompletionResult
    attempts: int = 1
    validation_errors: list = field(default_factory=list)


@dataclass
class Prompt:
    system: str
    user: str
    version: str
    max_tokens: int = 1024
    temperature: float = 0.4
    context: dict = field(default_factory=dict)  # retrieval metadata, e.g. knowledge ids offered


def parse_json_object(text):
    """Parse a JSON object from model output, tolerating ```json fences. Raises ValueError."""
    if not text:
        raise ValueError("empty output")
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.S)
    if fence:
        cleaned = fence.group(1).strip()
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in output")
        cleaned = cleaned[start : end + 1]
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("output is not a JSON object")
    return data


class AIProvider:
    name = "base"
    label = "Base"
    retry_backoff = 2.0  # seconds, multiplied by the attempt number
    max_retry_wait = 20.0  # never block a job longer than this waiting to retry

    def __init__(self, api_key, model, timeout=30, max_retries=1):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    # ---- adapter hook ------------------------------------------------------
    def _complete(self, system_prompt, user_prompt, *, json_mode=True, max_tokens=1024, temperature=0.4):
        """Return a CompletionResult or raise ProviderError."""
        raise NotImplementedError

    # ---- shared helpers ----------------------------------------------------
    def complete_json(self, system_prompt, user_prompt, validator=None, *, max_tokens=1024, temperature=0.4):
        """Call the model, parse + validate JSON. Bounded retry on invalid output / transient errors."""
        attempts = 0
        last_errors = []
        last_completion = None
        while attempts <= self.max_retries:
            attempts += 1
            prompt = user_prompt
            if last_errors:
                prompt += (
                    "\n\nYour previous output was rejected: "
                    + "; ".join(last_errors)[:500]
                    + ". Return ONLY one valid JSON object that matches the schema."
                )
            try:
                completion = self._complete(
                    system_prompt, prompt, json_mode=True, max_tokens=max_tokens, temperature=temperature
                )
            except ProviderError as exc:
                wait = max(self.retry_backoff * attempts, exc.retry_after or 0)
                if exc.retryable and attempts <= self.max_retries and wait <= self.max_retry_wait:
                    time.sleep(wait)  # e.g. 503 "high demand" or 429 rate limit: pause, then retry
                    continue
                exc.attempts = attempts
                raise
            last_completion = completion
            try:
                data = parse_json_object(completion.text)
            except (ValueError, json.JSONDecodeError) as exc:
                last_errors = [f"invalid JSON ({exc})"]
                continue
            if validator is None:
                return OperationResult(data=data, completion=completion, attempts=attempts)
            cleaned, errors = validator(data)
            if not errors:
                return OperationResult(data=cleaned, completion=completion, attempts=attempts)
            last_errors = errors
        err = ProviderError("Model output failed validation: " + "; ".join(last_errors)[:300], code="invalid_output")
        err.completion = last_completion
        err.attempts = attempts
        err.validation_errors = last_errors
        raise err

    # ---- operations used by the application --------------------------------
    def generate_reply(self, prompt, validator):
        return self.complete_json(
            prompt.system, prompt.user, validator, max_tokens=prompt.max_tokens, temperature=prompt.temperature
        )

    def classify_message(self, prompt, validator):
        return self.complete_json(prompt.system, prompt.user, validator, max_tokens=prompt.max_tokens, temperature=0.0)

    def summarize_conversation(self, prompt, validator):
        return self.complete_json(prompt.system, prompt.user, validator, max_tokens=prompt.max_tokens, temperature=0.2)

    def evaluate_reply(self, prompt, validator):
        return self.complete_json(prompt.system, prompt.user, validator, max_tokens=prompt.max_tokens, temperature=0.0)

    def generate_structured(self, prompt, validator):
        """Generic structured call (style profile generation etc.)."""
        return self.complete_json(
            prompt.system, prompt.user, validator, max_tokens=prompt.max_tokens, temperature=prompt.temperature
        )

    def test_connection(self):
        return self._complete(
            'You are a health check endpoint. Respond with the JSON object {"ok": true} and nothing else.',
            'Return {"ok": true} as JSON.',
            json_mode=True,
            max_tokens=256,
            temperature=0.0,
        )
