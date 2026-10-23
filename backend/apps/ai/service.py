"""
AI service: the only entry point the rest of the app uses for model calls.

* Resolves the workspace's selected provider (AISettings.provider).
* Never switches provider silently. If `fallback_enabled` is on, a failure of the
  selected provider is retried on the other provider and recorded as an
  `ai_fallback` usage event + warning log.
* Records an AIGeneration (structured output only) and a UsageEvent per call.
"""

import logging
import time
from dataclasses import dataclass

from apps.core.exceptions import ServiceError
from apps.core.models import UsageEvent
from apps.core.services import record_usage

from . import prompts, retrieval, schema
from .models import AIGeneration, AISettings, PersonaProfile
from .providers.base import ProviderError
from .registry import get_provider

logger = logging.getLogger(__name__)


class AIServiceError(ServiceError):
    def __init__(self, message, code="ai_error", generation=None):
        super().__init__(message, code=code, status_code=502)
        self.generation = generation


@dataclass
class AIResult:
    data: dict
    generation: AIGeneration
    provider: str
    fallback_used: bool


class AIService:
    def __init__(self, workspace):
        self.workspace = workspace
        self.settings, _ = AISettings.objects.get_or_create(workspace=workspace)

    # -------------------------------------------------------------------
    def provider_order(self):
        order = [self.settings.provider]
        fb = self.settings.fallback_provider
        if self.settings.fallback_enabled and fb and fb != self.settings.provider:
            order.append(fb)
        return order

    def run(self, operation, prompt, validator, *, method, conversation=None, message=None, provider_name=None):
        """Execute `method` ("generate_reply", ...) on the selected provider (with optional explicit fallback)."""
        order = [provider_name] if provider_name else self.provider_order()
        requested = order[0]
        last_error = None
        for idx, name in enumerate(order):
            fallback = idx > 0
            started = time.monotonic()
            model = ""
            try:
                provider = get_provider(name)
                model = provider.model
                result = getattr(provider, method)(prompt, validator)
            except ProviderError as exc:
                latency = int((time.monotonic() - started) * 1000)
                completion = getattr(exc, "completion", None)
                gen = AIGeneration.objects.create(
                    workspace=self.workspace,
                    conversation=conversation,
                    message=message,
                    operation=operation,
                    provider=name,
                    requested_provider=requested,
                    model=model,
                    fallback_used=fallback,
                    prompt_version=prompt.version,
                    status=AIGeneration.Status.INVALID_OUTPUT if exc.code == "invalid_output" else AIGeneration.Status.ERROR,
                    validation_errors=list(getattr(exc, "validation_errors", []))[:10],
                    error_code=exc.code[:64],
                    error_message=exc.message[:500],
                    attempts=getattr(exc, "attempts", 1),
                    latency_ms=latency,
                    input_tokens=getattr(completion, "input_tokens", 0) or 0,
                    output_tokens=getattr(completion, "output_tokens", 0) or 0,
                )
                record_usage(
                    self.workspace,
                    UsageEvent.Kind.AI_REQUEST,
                    source=name,
                    operation=operation,
                    model=model,
                    success=False,
                    error_code=exc.code[:64],
                    message=exc.message,
                    latency_ms=latency,
                )
                logger.warning("AI %s via %s failed: %s", operation, name, exc.message)
                last_error = AIServiceError(exc.message, code=exc.code, generation=gen)
                if idx + 1 < len(order):
                    logger.warning(
                        "AI fallback enabled for workspace %s: retrying %s with %s",
                        self.workspace.pk,
                        operation,
                        order[idx + 1],
                    )
                    record_usage(
                        self.workspace,
                        UsageEvent.Kind.AI_FALLBACK,
                        source=order[idx + 1],
                        operation=operation,
                        message=f"Fallback from {name} to {order[idx + 1]} after error {exc.code}",
                        details={"from": name, "to": order[idx + 1], "error_code": exc.code},
                    )
                continue

            latency = int((time.monotonic() - started) * 1000)
            gen = AIGeneration.objects.create(
                workspace=self.workspace,
                conversation=conversation,
                message=message,
                operation=operation,
                provider=name,
                requested_provider=requested,
                model=result.completion.model or model,
                fallback_used=fallback,
                prompt_version=prompt.version,
                status=AIGeneration.Status.SUCCESS,
                output=result.data,
                attempts=result.attempts,
                latency_ms=latency,
                input_tokens=result.completion.input_tokens,
                output_tokens=result.completion.output_tokens,
            )
            record_usage(
                self.workspace,
                UsageEvent.Kind.AI_REQUEST,
                source=name,
                operation=operation,
                model=gen.model,
                input_tokens=result.completion.input_tokens,
                output_tokens=result.completion.output_tokens,
                latency_ms=latency,
                details={"fallback_used": fallback} if fallback else {},
            )
            return AIResult(data=result.data, generation=gen, provider=name, fallback_used=fallback)
        raise last_error

    # -------------------------------------------------------------------
    def build_reply_prompt(self, conversation, message, reply_format="text", persona=None, current_text=None):
        from apps.conversations.models import ConversationSummary, Message

        persona = persona or PersonaProfile.objects.get_or_create(workspace=self.workspace)[0]
        text = current_text if current_text is not None else (message.text if message else "")
        history = []
        summary = ""
        contact = None
        if conversation is not None:
            contact = conversation.contact
            qs = Message.objects.filter(conversation=conversation, workspace=self.workspace)
            if message is not None:
                qs = qs.filter(created_at__lte=message.created_at).exclude(pk=message.pk)
            history = list(qs.order_by("-created_at", "-id")[: self.settings.history_messages])[::-1]
            summary_obj = ConversationSummary.objects.filter(conversation=conversation).first()
            summary = summary_obj.summary if summary_obj else ""
        recent_customer = " ".join(m.text for m in history[-4:] if m.direction == "in")
        query = f"{text} {recent_customer}"
        return prompts.build_reply_prompt(
            persona=persona,
            instructions=retrieval.business_instructions(self.workspace),
            examples=retrieval.retrieve_examples(self.workspace, text),
            knowledge=retrieval.retrieve_knowledge(self.workspace, query),
            history=history,
            summary=summary,
            contact=contact,
            current_text=text,
            max_chars=self.settings.max_reply_chars,
            temperature=self.settings.temperature,
            reply_format=reply_format,
            tz_name=self.workspace.timezone,
        )

    def generate_reply(self, conversation, message, reply_format="text", operation=AIGeneration.Operation.REPLY):
        prompt = self.build_reply_prompt(conversation, message, reply_format)
        validator = schema.make_reply_validator(prompt.context["knowledge_ids"], self.settings.max_reply_chars)
        result = self.run(operation, prompt, validator, method="generate_reply", conversation=conversation, message=message)
        result.prompt = prompt
        return result

    def preview_reply(self, customer_text, persona=None):
        prompt = self.build_reply_prompt(None, None, persona=persona, current_text=customer_text)
        validator = schema.make_reply_validator(prompt.context["knowledge_ids"], self.settings.max_reply_chars)
        result = self.run(AIGeneration.Operation.PREVIEW, prompt, validator, method="generate_reply")
        result.prompt = prompt
        return result

    def classify_message(self, text, conversation=None, message=None, history=None):
        prompt = prompts.build_classify_prompt(text, history)
        return self.run(
            AIGeneration.Operation.CLASSIFY,
            prompt,
            schema.validate_classification,
            method="classify_message",
            conversation=conversation,
            message=message,
        )

    def summarize_conversation(self, conversation, messages, previous_summary=""):
        prompt = prompts.build_summary_prompt(messages, previous_summary)
        return self.run(
            AIGeneration.Operation.SUMMARIZE,
            prompt,
            schema.validate_summary,
            method="summarize_conversation",
            conversation=conversation,
        )

    def evaluate_reply(self, customer_text, reply_text, knowledge, conversation=None, message=None):
        prompt = prompts.build_evaluate_prompt(customer_text=customer_text, reply_text=reply_text, knowledge=knowledge)
        return self.run(
            AIGeneration.Operation.EVALUATE,
            prompt,
            schema.validate_evaluation,
            method="evaluate_reply",
            conversation=conversation,
            message=message,
        )

    def generate_style_profile(self, examples):
        prompt = prompts.build_style_profile_prompt(examples)
        return self.run(
            AIGeneration.Operation.STYLE_PROFILE, prompt, schema.validate_style_profile, method="generate_structured"
        )


def test_provider_connection(workspace, provider_name):
    """Live connection test for one provider. Returns dict; never raises for provider errors."""
    started = time.monotonic()
    try:
        provider = get_provider(provider_name)
        completion = provider.test_connection()
    except ProviderError as exc:
        latency = int((time.monotonic() - started) * 1000)
        record_usage(
            workspace,
            UsageEvent.Kind.AI_REQUEST,
            source=provider_name,
            operation="test",
            success=False,
            error_code=exc.code[:64],
            message=exc.message,
            latency_ms=latency,
        )
        return {"ok": False, "provider": provider_name, "error": exc.message, "code": exc.code, "latency_ms": latency}
    latency = int((time.monotonic() - started) * 1000)
    record_usage(
        workspace,
        UsageEvent.Kind.AI_REQUEST,
        source=provider_name,
        operation="test",
        model=completion.model,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        latency_ms=latency,
    )
    return {"ok": True, "provider": provider_name, "model": completion.model, "latency_ms": latency}
