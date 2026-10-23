"""Provider adapters + selection. HTTP / SDK calls are MOCKED."""

import json
from unittest import mock

from django.test import override_settings

from apps.ai.models import AIGeneration, AISettings
from apps.ai.providers.base import ProviderNotConfigured, parse_json_object
from apps.ai.providers.deepseek import DeepSeekProvider
from apps.ai.providers.gemini import GeminiProvider
from apps.ai.providers.groq import GroqProvider
from apps.ai.registry import get_provider
from apps.ai.schema import make_reply_validator
from apps.ai.service import AIService, AIServiceError
from apps.core.models import UsageEvent

from .helpers import BaseTestCase, FakeResponse, fake_llm, reply_json


class AdapterTests(BaseTestCase):
    def test_deepseek_adapter_calls_official_endpoint(self):
        session = mock.Mock()
        session.post.return_value = FakeResponse(200, {
            "model": "deepseek-flash",
            "choices": [{"message": {"content": reply_json()}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 40},
        })
        provider = DeepSeekProvider(api_key="sk-test", model="deepseek-flash", session=session)
        result = provider.complete_json("sys", "user", make_reply_validator([], 700))
        url = session.post.call_args.args[0]
        kwargs = session.post.call_args.kwargs
        self.assertEqual(url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(kwargs["json"]["model"], "deepseek-flash")
        self.assertEqual(kwargs["json"]["response_format"], {"type": "json_object"})
        self.assertEqual(kwargs["json"]["thinking"], {"type": "disabled"})
        self.assertEqual(result.completion.input_tokens, 120)
        self.assertEqual(result.data["intent"], "availability_question")

    def test_deepseek_http_error_is_reported(self):
        session = mock.Mock()
        session.post.return_value = FakeResponse(401, {"error": {"message": "Authentication Fails"}})
        provider = DeepSeekProvider(api_key="bad", model="deepseek-flash", session=session, max_retries=0)
        with self.assertRaises(Exception) as ctx:
            provider.complete_json("s", "u")
        self.assertIn("401", str(ctx.exception))

    def _groq_session(self, *responses):
        session = mock.Mock()
        session.post.side_effect = list(responses)
        return session

    def _ok(self):
        return FakeResponse(200, {"model": "openai/gpt-oss-120b",
                                  "choices": [{"message": {"content": reply_json()}, "finish_reason": "stop"}],
                                  "usage": {"prompt_tokens": 90, "completion_tokens": 40}})

    def test_groq_adapter_calls_official_endpoint_with_hidden_reasoning(self):
        session = self._groq_session(self._ok())
        provider = GroqProvider(api_key="gsk-test", model="openai/gpt-oss-120b", session=session, reasoning_effort="low")
        result = provider.complete_json("sys", "user", make_reply_validator([], 700))
        url = session.post.call_args.args[0]
        body = session.post.call_args.kwargs["json"]
        self.assertEqual(url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(session.post.call_args.kwargs["headers"]["Authorization"], "Bearer gsk-test")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["reasoning_format"], "hidden")  # required for JSON mode; never returns reasoning
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertNotIn("thinking", body)
        self.assertEqual(result.data["intent"], "availability_question")

    def test_groq_non_reasoning_model_gets_no_reasoning_params(self):
        session = self._groq_session(self._ok())
        GroqProvider(api_key="k", model="llama-3.3-70b-versatile", session=session).complete_json("s", "u")
        body = session.post.call_args.kwargs["json"]
        self.assertNotIn("reasoning_format", body)
        self.assertNotIn("reasoning_effort", body)

    def test_groq_free_plan_429_waits_for_retry_after_then_succeeds(self):
        limited = FakeResponse(429, {"error": {"message": "Rate limit reached on tokens per minute (TPM)"}}, headers={"retry-after": "3"})
        session = self._groq_session(limited, self._ok())
        provider = GroqProvider(api_key="k", model="openai/gpt-oss-120b", session=session, max_retries=1)
        with mock.patch("apps.ai.providers.base.time.sleep") as sleep:
            result = provider.complete_json("s", "u", make_reply_validator([], 700))
        sleep.assert_called_once_with(3.0)
        self.assertEqual(result.attempts, 2)

    def test_groq_long_retry_after_fails_fast_with_clear_message(self):
        limited = FakeResponse(429, {"error": {"message": "Rate limit reached on requests per day (RPD)"}}, headers={"retry-after": "3600"})
        session = self._groq_session(limited)
        provider = GroqProvider(api_key="k", model="openai/gpt-oss-120b", session=session, max_retries=1)
        with mock.patch("apps.ai.providers.base.time.sleep") as sleep, self.assertRaises(Exception) as ctx:
            provider.complete_json("s", "u")
        sleep.assert_not_called()
        self.assertEqual(ctx.exception.code, "groq_429")
        self.assertIn("rate limit reached", ctx.exception.message)

    @override_settings(GROQ_API_KEY="")
    def test_groq_unconfigured_names_the_missing_variable(self):
        with self.assertRaises(ProviderNotConfigured) as ctx:
            get_provider("groq")
        self.assertIn("GROQ_API_KEY", ctx.exception.message)

    def test_gemini_adapter_uses_sdk_with_json_mode(self):
        provider = GeminiProvider(api_key="g-test", model="gemini-3.8-flash")
        fake_client = mock.Mock()
        fake_client.models.generate_content.return_value = mock.Mock(
            text=reply_json(), candidates=[mock.Mock(finish_reason="STOP")],
            usage_metadata=mock.Mock(prompt_token_count=99, candidates_token_count=33),
        )
        provider._client = fake_client
        result = provider.complete_json("system text", "user text", make_reply_validator([], 700))
        call = fake_client.models.generate_content.call_args.kwargs
        self.assertEqual(call["model"], "gemini-3.8-flash")
        self.assertEqual(call["config"].response_mime_type, "application/json")
        self.assertEqual(call["config"].system_instruction, "system text")
        self.assertEqual(result.completion.output_tokens, 33)

    @override_settings(DEEPSEEK_API_KEY="")
    def test_unconfigured_provider_raises_informative_error(self):
        with self.assertRaises(ProviderNotConfigured) as ctx:
            get_provider("deepseek")
        self.assertIn("DEEPSEEK_API_KEY", ctx.exception.message)

    def test_parse_json_tolerates_code_fences(self):
        self.assertEqual(parse_json_object('```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(ValueError):
            parse_json_object("not json")


class SelectionTests(BaseTestCase):
    def test_selected_provider_is_the_one_called(self):
        with fake_llm() as llm:
            AISettings.objects.filter(workspace=self.workspace).update(provider="deepseek")
            AIService(self.workspace).preview_reply("Do you have slots tomorrow?")
            self.assertEqual(llm.providers_called(), ["deepseek"])
            AISettings.objects.filter(workspace=self.workspace).update(provider="gemini")
            AIService(self.workspace).preview_reply("Do you have slots tomorrow?")
            self.assertEqual(llm.providers_called(), ["deepseek", "gemini"])
        gens = list(AIGeneration.objects.filter(workspace=self.workspace).order_by("created_at").values_list("provider", "model"))
        self.assertEqual(gens, [("deepseek", "deepseek-flash"), ("gemini", "gemini-3.8-flash")])

    def test_groq_selected_routes_every_operation_to_groq(self):
        AISettings.objects.filter(workspace=self.workspace).update(provider="groq")
        with fake_llm() as llm:
            svc = AIService(self.workspace)
            result = svc.preview_reply("Do you have slots tomorrow?")
            svc.evaluate_reply("q", "a", [])
        self.assertEqual(set(llm.providers_called()), {"groq"})
        self.assertEqual((result.provider, result.generation.model), ("groq", "openai/gpt-oss-120b"))

    def test_fallback_to_groq_when_chosen(self):
        AISettings.objects.filter(workspace=self.workspace).update(fallback_enabled=True, fallback_provider="groq")
        with fake_llm() as llm:
            llm.fail.add("gemini")
            result = AIService(self.workspace).preview_reply("hello")
        self.assertEqual(llm.providers_called(), ["gemini", "groq"])
        self.assertTrue(result.fallback_used)

    def test_no_silent_switch_when_fallback_disabled(self):
        with fake_llm() as llm:
            llm.fail.add("gemini")
            with self.assertRaises(AIServiceError) as ctx:
                AIService(self.workspace).preview_reply("hello")
            self.assertEqual(llm.providers_called(), ["gemini"])  # deepseek never called
        self.assertIn("gemini", ctx.exception.code)
        self.assertFalse(UsageEvent.objects.filter(kind="ai_fallback").exists())

    def test_explicit_fallback_is_used_and_recorded(self):
        AISettings.objects.filter(workspace=self.workspace).update(fallback_enabled=True, fallback_provider="deepseek")
        with fake_llm() as llm:
            llm.fail.add("gemini")
            result = AIService(self.workspace).preview_reply("hello")
        self.assertEqual(llm.providers_called(), ["gemini", "deepseek"])
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.provider, "deepseek")
        self.assertTrue(result.generation.fallback_used)
        self.assertEqual(result.generation.requested_provider, "gemini")
        ev = UsageEvent.objects.get(kind="ai_fallback")
        self.assertEqual(ev.details, {"from": "gemini", "to": "deepseek", "error_code": "gemini_503"})

    def test_invalid_output_retried_then_rejected(self):
        with fake_llm() as llm:
            llm.queue("gemini", "not json at all", json.dumps({"reply_text": "x"}))
            with self.assertRaises(AIServiceError) as ctx:
                AIService(self.workspace).preview_reply("hello")
            self.assertEqual(len(llm.calls), 2)  # one bounded retry
        self.assertEqual(ctx.exception.code, "invalid_output")
        gen = AIGeneration.objects.get()
        self.assertEqual(gen.status, "invalid_output")
        self.assertTrue(gen.validation_errors)

    def test_invalid_then_valid_output_succeeds(self):
        with fake_llm() as llm:
            llm.queue("gemini", "{broken", reply_json())
            result = AIService(self.workspace).preview_reply("hello")
        self.assertEqual(result.generation.attempts, 2)

    def test_reply_validator_rules(self):
        v = make_reply_validator([5], 50)
        cleaned, errors = v(json.loads(reply_json(knowledge_references=["5", "999"], suggested_action="refund_now")))
        self.assertIn("'suggested_action' must be one of reply, clarify, escalate, no_reply", errors)
        self.assertTrue(any("exceeds 50" in e for e in errors))
        self.assertEqual(cleaned["knowledge_references"], ["5"])
        self.assertEqual(cleaned["invalid_knowledge_references"], ["999"])
        _, errors = v({"reply_text": "hi", "confidence": "high", "needs_human_review": "no", "suggested_action": "reply"})
        self.assertTrue(any("confidence" in e for e in errors))
        self.assertTrue(any("needs_human_review" in e for e in errors))

    def test_other_operations_respect_selected_provider(self):
        AISettings.objects.filter(workspace=self.workspace).update(provider="deepseek")
        with fake_llm() as llm:
            llm.queue("deepseek", json.dumps({"intent": "greeting", "language": "en", "sentiment": "positive",
                                              "urgency": "low", "wants_human": False, "topics": []}))
            llm.queue("deepseek", json.dumps({"summary": "Customer asked about slots.", "customer_facts": [], "open_questions": []}))
            svc = AIService(self.workspace)
            self.assertEqual(svc.classify_message("hi there").data["intent"], "greeting")
            self.assertEqual(svc.summarize_conversation(None, []).data["summary"], "Customer asked about slots.")
            self.assertEqual(svc.evaluate_reply("q", "a", []).data["verdict"], "pass")
        self.assertEqual(set(llm.providers_called()), {"deepseek"})
