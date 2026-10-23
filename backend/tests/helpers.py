"""
Shared test helpers.

All external APIs (Gemini, DeepSeek, WhatsApp Graph API, ElevenLabs) are MOCKED in
these tests. Passing tests prove the application logic, request formatting and
safety rules - NOT that live credentials work.
"""

import hashlib
import hmac
import itertools
import json
import time
from contextlib import contextmanager
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.ai.providers.base import CompletionResult, ProviderError
from apps.core.models import Membership, Workspace
from apps.core.services import ensure_workspace_defaults
from apps.whatsapp.models import WhatsAppIntegration

TEST_SETTINGS = dict(
    JOBS_MODE="sync",
    GEMINI_API_KEY="test-gemini-key-123456",
    GEMINI_MODEL="gemini-3.8-flash",
    DEEPSEEK_API_KEY="test-deepseek-key-123456",
    DEEPSEEK_MODEL="deepseek-flash",
    GROQ_API_KEY="test-groq-key-123456",
    GROQ_MODEL="openai/gpt-oss-120b",
    GROQ_BASE_URL="https://api.groq.com/openai/v1",
    GROQ_REASONING_EFFORT="low",
    META_APP_SECRET="test-app-secret",
    WHATSAPP_VERIFY_TOKEN="test-verify-token",
    WHATSAPP_ACCESS_TOKEN="test-wa-access-token-123456",
    ELEVENLABS_API_KEY="",
    AI_MAX_RETRIES=1,
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
        "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
        "DEFAULT_THROTTLE_RATES": {"auth": "1000/min", "ai": "1000/min", "send": "1000/min", "webhook": "1000/min"},
        "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    },
)

_counter = itertools.count(1)


def reply_json(**overrides):
    data = {
        "intent": "availability_question",
        "language": "en",
        "reply_text": "Hey! Yes, we have a couple of slots tomorrow. What time works best for you?",
        "confidence": 0.92,
        "needs_human_review": False,
        "reason_code": "known_information",
        "knowledge_references": [],
        "suggested_action": "reply",
        "voice_note_eligible": True,
        "rationale": "Answered from booking info.",
    }
    data.update(overrides)
    return json.dumps(data)


EVAL_PASS = json.dumps(
    {"verdict": "pass", "grounded": True, "unsupported_claims": [], "commitments": [], "tone_ok": True, "score": 0.9}
)


class FakeLLM:
    """Records calls per provider and returns scripted outputs (MOCK)."""

    def __init__(self):
        self.calls = []  # (provider_name, system, user)
        self.replies = {"gemini": [], "deepseek": [], "groq": []}
        self.default = reply_json()
        self.fail = set()
        self.hook = None

    def queue(self, provider, *outputs):
        self.replies[provider].extend(outputs)

    def make(self, provider_name):
        fake = self

        def _complete(self_, system_prompt, user_prompt, *, json_mode=True, max_tokens=1024, temperature=0.4):
            fake.calls.append((provider_name, system_prompt, user_prompt))
            if fake.hook:
                fake.hook(provider_name, system_prompt, user_prompt)
            if provider_name in fake.fail:
                raise ProviderError(f"{provider_name} is down (mock)", code=f"{provider_name}_503", retryable=False)
            if "quality checker" in system_prompt:
                return CompletionResult(text=EVAL_PASS, model=self_.model, input_tokens=5, output_tokens=5)
            queue = fake.replies[provider_name]
            text = queue.pop(0) if queue else fake.default
            return CompletionResult(text=text, model=self_.model, input_tokens=10, output_tokens=20)

        return _complete

    def providers_called(self):
        return [c[0] for c in self.calls]

    def reply_calls(self):
        return [c for c in self.calls if "quality checker" not in c[1]]


@contextmanager
def fake_llm():
    llm = FakeLLM()
    with mock.patch("apps.ai.providers.gemini.GeminiProvider._complete", llm.make("gemini")), mock.patch(
        "apps.ai.providers.deepseek.DeepSeekProvider._complete", llm.make("deepseek")
    ), mock.patch(
        "apps.ai.providers.groq.GroqProvider._complete", llm.make("groq")
    ):
        yield llm


class FakeResponse:
    def __init__(self, status=200, data=None, content=b"", headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._data = data
        self.content = content or (json.dumps(data).encode() if data is not None else b"")
        self.text = self.content.decode(errors="ignore")

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data

    def iter_content(self, size):
        yield self.content


class FakeGraph:
    """MOCK of graph.facebook.com used by WhatsAppClient (patched requests.Session.request)."""

    def __init__(self):
        self.requests = []
        self.fail_with = None  # (status, error_dict)

    def __call__(self, session, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        if self.fail_with:
            status, err = self.fail_with
            return FakeResponse(status, {"error": err})
        if url.endswith("/messages"):
            return FakeResponse(200, {"messaging_product": "whatsapp", "messages": [{"id": f"wamid.OUT{next(_counter)}"}]})
        if url.endswith("/media"):
            return FakeResponse(200, {"id": f"media{next(_counter)}"})
        return FakeResponse(200, {"display_phone_number": "+1 555 0100", "verified_name": "Test Biz", "quality_rating": "GREEN"})

    @property
    def sends(self):
        return [r for r in self.requests if r["url"].endswith("/messages") and r.get("json", {}).get("type")]


@contextmanager
def fake_graph():
    graph = FakeGraph()
    def request(session, method, url, **kwargs):  # a real function so it binds as a method
        return graph(session, method, url, **kwargs)

    with mock.patch("requests.Session.request", request):
        yield graph


@override_settings(**TEST_SETTINGS)
class BaseTestCase(TestCase):
    phone_number_id = "100200300400"

    def setUp(self):
        super().setUp()
        self.user, self.workspace = self.make_workspace("owner", "Acme Salon", self.phone_number_id)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def make_workspace(self, username, name, phone_number_id=None):
        user = get_user_model().objects.create_user(username, f"{username}@example.com", "S3cure-pass-123")
        ws = Workspace.objects.create(name=name)
        Membership.objects.create(user=user, workspace=ws, role="owner")
        ensure_workspace_defaults(ws)
        if phone_number_id:
            WhatsAppIntegration.objects.create(workspace=ws, phone_number_id=phone_number_id, status="connected")
        return user, ws

    def set_mode(self, mode, workspace=None):
        from apps.automation.models import AutomationSettings

        AutomationSettings.objects.filter(workspace=workspace or self.workspace).update(mode=mode)

    def webhook_payload(self, text="Hi, do you have any slots available tomorrow?", wa_id="15551234567", wamid=None,
                        phone_number_id=None, name="Jane", msg_type="text", ts=None):
        message = {"from": wa_id, "id": wamid or f"wamid.IN{next(_counter)}", "timestamp": str(ts or int(time.time())), "type": msg_type}
        if msg_type == "text":
            message["text"] = {"body": text}
        elif msg_type == "audio":
            message["audio"] = {"id": "audio-media-1", "mime_type": "audio/ogg; codecs=opus"}
        return {
            "object": "whatsapp_business_account",
            "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
                "messaging_product": "whatsapp",
                "metadata": {"display_phone_number": "15550100", "phone_number_id": phone_number_id or self.phone_number_id},
                "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
                "messages": [message],
            }}]}],
        }

    def status_payload(self, wamid, status, errors=None):
        st = {"id": wamid, "status": status, "timestamp": str(int(time.time())), "recipient_id": "15551234567"}
        if errors:
            st["errors"] = errors
        return {
            "object": "whatsapp_business_account",
            "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
                "messaging_product": "whatsapp",
                "metadata": {"phone_number_id": self.phone_number_id},
                "statuses": [st],
            }}]}],
        }

    def post_webhook(self, payload=None, raw=None, secret="test-app-secret", signature=None):
        body = raw if raw is not None else json.dumps(payload).encode()
        sig = signature if signature is not None else "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return APIClient().post("/api/webhooks/whatsapp/", data=body, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=sig)
