"""Dashboard API: settings persistence, permissions, workspace isolation, secret handling."""

import json
from unittest import mock

from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.models import AISettings
from apps.ai.service import AIService
from apps.conversations.models import Conversation, Draft, MediaAsset
from apps.core.models import Membership

from .helpers import BaseTestCase, FakeResponse, fake_graph, fake_llm


class ProviderSelectorApiTests(BaseTestCase):
    def test_switching_provider_persists_and_changes_backend(self):
        r = self.client.put("/api/ai/settings/", {"provider": "deepseek"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["provider"], "deepseek")
        # "refresh": a new GET returns the persisted selection
        self.assertEqual(self.client.get("/api/ai/settings/").json()["active"]["provider"], "deepseek")
        # "restart": a brand-new service object reads it from the DB
        with fake_llm() as llm:
            AIService(self.workspace).preview_reply("hello")
        self.assertEqual(llm.providers_called(), ["deepseek"])

    @override_settings(DEEPSEEK_API_KEY="")
    def test_cannot_select_unconfigured_provider(self):
        r = self.client.put("/api/ai/settings/", {"provider": "deepseek"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("DEEPSEEK_API_KEY", json.dumps(r.json()))
        self.assertEqual(AISettings.objects.get(workspace=self.workspace).provider, "gemini")

    def test_unknown_provider_rejected(self):
        r = self.client.put("/api/ai/settings/", {"provider": "openai"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_save_with_failed_connection_test_is_not_saved(self):
        with fake_llm() as llm:
            llm.fail.add("deepseek")
            r = self.client.put("/api/ai/settings/", {"provider": "deepseek", "test_connection": True}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(AISettings.objects.get(workspace=self.workspace).provider, "gemini")

    def test_connection_test_endpoint(self):
        with fake_llm():
            r = self.client.post("/api/ai/test/", {"provider": "deepseek"}, format="json")
        self.assertTrue(r.json()["ok"])
        self.assertEqual(r.json()["model"], "deepseek-flash")

    @override_settings(DEEPSEEK_API_KEY="")
    def test_fallback_requires_other_provider(self):
        r = self.client.put("/api/ai/settings/", {"fallback_enabled": True}, format="json")
        self.assertEqual(r.status_code, 400)  # no fallback provider chosen
        r = self.client.put("/api/ai/settings/", {"fallback_enabled": True, "fallback_provider": "deepseek"}, format="json")
        self.assertEqual(r.status_code, 400)  # deepseek not configured
        self.assertIn("DEEPSEEK_API_KEY", json.dumps(r.json()))
        r = self.client.put("/api/ai/settings/", {"fallback_enabled": True, "fallback_provider": "gemini"}, format="json")
        self.assertEqual(r.status_code, 400)  # same as selected provider
        r = self.client.put("/api/ai/settings/", {"fallback_enabled": True, "fallback_provider": "groq"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["fallback_provider"], "groq")

    def test_fallback_disabled_by_default(self):
        self.assertFalse(AISettings.objects.get(workspace=self.workspace).fallback_enabled)

    def test_no_secrets_in_api_responses(self):
        bodies = [self.client.get(u).content.decode() for u in
                  ("/api/ai/settings/", "/api/integrations/", "/api/whatsapp/", "/api/dashboard/", "/api/voice/")]
        for secret in ("test-gemini-key-123456", "test-deepseek-key-123456", "test-groq-key-123456", "test-wa-access-token-123456", "test-app-secret", "test-verify-token"):
            for body in bodies:
                self.assertNotIn(secret, body)


class SettingsPersistenceTests(BaseTestCase):
    def test_automatic_mode_requires_explicit_confirmation(self):
        r = self.client.put("/api/automation/", {"mode": "automatic"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.put("/api/automation/", {"mode": "automatic", "confirm_automatic": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/automation/").json()["mode"], "automatic")

    def test_operating_hours_validation(self):
        r = self.client.put("/api/automation/", {"operating_hours": {"mon": [["18:00", "09:00"]]}}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.put("/api/automation/", {"operating_hours_enabled": True, "operating_hours": {"mon": [["09:00", "18:00"]]}}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_persona_and_knowledge_crud(self):
        r = self.client.put("/api/persona/", {"formality": 2, "greetings": "Hey!"}, format="json")
        self.assertEqual(r.json()["greetings"], "Hey!")
        self.assertEqual(self.client.get("/api/persona/").json()["formality"], 2)
        r = self.client.post("/api/knowledge/", {"category": "hours", "title": "Hours", "content": "Mon-Fri 9-6"}, format="json")
        self.assertEqual(r.status_code, 201)
        kid = r.json()["id"]
        self.client.patch(f"/api/knowledge/{kid}/", {"content": "Mon-Sat 9-6"}, format="json")
        self.assertEqual(self.client.get("/api/knowledge/").json()[0]["content"], "Mon-Sat 9-6")
        self.assertEqual(self.client.delete(f"/api/knowledge/{kid}/").status_code, 204)
        r = self.client.post("/api/examples/", {"customer_message": "hi", "preferred_reply": "hey!"}, format="json")
        self.assertEqual(r.status_code, 201)

    def test_preview_returns_structured_reply_and_sends_nothing(self):
        with fake_llm(), fake_graph() as graph:
            r = self.client.post("/api/persona/preview/", {"customer_message": "Any slots?", "persona": {"formality": 1}}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("reply_text", r.json()["reply"])
        self.assertEqual(graph.requests, [])

    def test_whatsapp_integration_setup_validates_with_graph(self):
        with fake_graph() as graph:
            r = self.client.put("/api/whatsapp/", {"phone_number_id": "123456789012"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "connected")
        self.assertEqual(r.json()["integration"]["verified_name"], "Test Biz")
        self.assertIn("/v26.0/123456789012", graph.requests[0]["url"])

    @override_settings(WHATSAPP_ACCESS_TOKEN="")
    def test_missing_whatsapp_token_shows_not_configured(self):
        r = self.client.get("/api/integrations/")
        self.assertEqual(r.json()["whatsapp"]["status"], "not_configured")
        self.assertFalse(r.json()["whatsapp"]["env"]["access_token_configured"])


class IsolationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.set_mode("approval")
        with fake_llm(), fake_graph():
            self.post_webhook(self.webhook_payload())
        self.conv = Conversation.objects.get()
        self.draft = Draft.objects.get()
        self.intruder, self.other_ws = self.make_workspace("intruder", "Other Co")
        self.other = APIClient()
        self.other.force_authenticate(self.intruder)

    def test_other_workspace_cannot_see_or_act(self):
        self.assertEqual(self.other.get("/api/conversations/").json(), [])
        self.assertEqual(self.other.get(f"/api/conversations/{self.conv.pk}/").status_code, 404)
        self.assertEqual(self.other.get(f"/api/conversations/{self.conv.pk}/messages/").status_code, 404)
        self.assertEqual(self.other.post(f"/api/drafts/{self.draft.pk}/approve/", {}, format="json").status_code, 404)
        self.assertEqual(self.other.post(f"/api/conversations/{self.conv.pk}/takeover/").status_code, 404)

    def test_workspace_header_cannot_select_foreign_workspace(self):
        r = self.other.get("/api/conversations/", HTTP_X_WORKSPACE_ID=str(self.workspace.pk))
        self.assertEqual(r.status_code, 404)

    def test_media_is_workspace_scoped(self):
        m = MediaAsset.objects.create(workspace=self.workspace, source="voice_generated", mime_type="audio/ogg")
        self.assertEqual(self.other.get(f"/api/media/{m.pk}/").status_code, 404)

    def test_unauthenticated_access_denied(self):
        anon = APIClient()
        for url in ("/api/conversations/", "/api/dashboard/", "/api/ai/settings/", f"/api/media/1/"):
            self.assertIn(anon.get(url).status_code, (401, 403))

    def test_agents_cannot_change_settings(self):
        Membership.objects.create(user=self.intruder, workspace=self.workspace, role="agent")
        r = self.other.put("/api/ai/settings/", {"provider": "deepseek"}, format="json", HTTP_X_WORKSPACE_ID=str(self.workspace.pk))
        self.assertEqual(r.status_code, 403)
        r = self.other.get("/api/conversations/", HTTP_X_WORKSPACE_ID=str(self.workspace.pk))
        self.assertEqual(len(r.json()), 1)  # agents can work the inbox

    def test_dashboard_reflects_real_data(self):
        r = self.client.get("/api/dashboard/").json()
        self.assertEqual(r["totals"]["conversations"], 1)
        self.assertEqual(r["totals"]["messages_received"], 1)
        self.assertEqual(r["totals"]["drafts_pending"], 1)
        self.assertEqual(r["provider"]["selected"], "gemini")
        self.assertEqual(r["ai_usage_30d"][0]["source"], "gemini")


class AuthFlowTests(BaseTestCase):
    @override_settings(ALLOW_REGISTRATION=True)
    def test_register_login_logout_with_csrf(self):
        c = APIClient(enforce_csrf_checks=True)
        token = c.get("/api/auth/csrf/").json()["csrfToken"]
        r = c.post("/api/auth/register/", {"username": "newowner", "password": "A-strong-pass-991", "business_name": "Bloom"},
                   format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["workspaces"][0]["name"], "Bloom")
        token = c.cookies["csrftoken"].value
        self.assertEqual(c.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code, 200)
        r = c.post("/api/auth/login/", {"username": "newowner", "password": "wrong"}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 400)

    def test_csrf_enforced_for_session_writes(self):
        c = APIClient(enforce_csrf_checks=True)
        c.login(username="owner", password="S3cure-pass-123")
        r = c.put("/api/ai/settings/", {"provider": "deepseek"}, format="json")
        self.assertEqual(r.status_code, 403)
