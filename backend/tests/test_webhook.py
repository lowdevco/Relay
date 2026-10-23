"""WhatsApp webhook verification, ingestion, idempotency and status updates (Graph API MOCKED)."""

import json

from django.test import override_settings

from apps.conversations.models import Contact, Conversation, Message
from apps.core.models import Job
from apps.whatsapp.models import WebhookEvent

from .helpers import BaseTestCase, fake_graph, fake_llm


class WebhookVerificationTests(BaseTestCase):
    def test_verification_challenge(self):
        r = self.client.get("/api/webhooks/whatsapp/", {"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "12345"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"12345")

    def test_verification_wrong_token(self):
        r = self.client.get("/api/webhooks/whatsapp/", {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"})
        self.assertEqual(r.status_code, 403)

    def test_invalid_signature_rejected(self):
        r = self.post_webhook(self.webhook_payload(), signature="sha256=deadbeef")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Message.objects.exists())

    def test_missing_signature_rejected(self):
        r = self.post_webhook(self.webhook_payload(), signature="")
        self.assertEqual(r.status_code, 403)

    @override_settings(DEBUG=True, META_APP_SECRET="", WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS=True)
    def test_unsigned_allowed_only_in_explicit_dev_mode(self):
        self.set_mode("manual")
        with fake_llm(), fake_graph():
            r = self.post_webhook(self.webhook_payload(), signature="")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(WebhookEvent.objects.get().signature_valid)


class WebhookIngestionTests(BaseTestCase):
    def test_valid_webhook_creates_contact_conversation_message(self):
        self.set_mode("manual")
        with fake_llm(), fake_graph() as graph:
            r = self.post_webhook(self.webhook_payload(text="Hello there", wa_id="15559990000", name="Jane Doe"))
        self.assertEqual(r.status_code, 200)
        contact = Contact.objects.get(workspace=self.workspace, wa_id="15559990000")
        self.assertEqual(contact.profile_name, "Jane Doe")
        conv = Conversation.objects.get(contact=contact)
        msg = Message.objects.get(conversation=conv)
        self.assertEqual((msg.direction, msg.sender_type, msg.text), ("in", "customer", "Hello there"))
        self.assertEqual(conv.unread_count, 1)
        self.assertTrue(conv.within_service_window())
        self.assertEqual(graph.sends, [])  # manual mode

    def test_duplicate_delivery_creates_no_duplicates_or_double_reply(self):
        self.set_mode("automatic")
        payload = self.webhook_payload(wamid="wamid.SAME")
        with fake_llm(), fake_graph() as graph:
            self.post_webhook(payload)
            self.post_webhook(payload)  # identical redelivery
            alt = self.webhook_payload(wamid="wamid.SAME")
            alt["entry"][0]["id"] = "WABA-redelivered"  # different envelope, same message id
            self.post_webhook(alt)
        self.assertEqual(Message.objects.filter(direction="in").count(), 1)
        self.assertEqual(Message.objects.filter(direction="out").count(), 1)
        self.assertEqual(len(graph.sends), 1)
        self.assertEqual(Job.objects.filter(kind="automation.process_inbound").count(), 1)

    def test_unknown_phone_number_is_ignored(self):
        with fake_llm(), fake_graph():
            r = self.post_webhook(self.webhook_payload(phone_number_id="999999"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Message.objects.exists())

    def test_messages_routed_to_correct_workspace(self):
        _, other_ws = self.make_workspace("other", "Other Biz", "555666777888")
        self.set_mode("manual")
        self.set_mode("manual", other_ws)
        with fake_llm(), fake_graph():
            self.post_webhook(self.webhook_payload(phone_number_id="555666777888", text="for other"))
        self.assertEqual(Message.objects.get().workspace, other_ws)

    def test_status_updates_and_failures_visible(self):
        self.set_mode("automatic")
        with fake_llm(), fake_graph():
            self.post_webhook(self.webhook_payload())
        out = Message.objects.get(direction="out")
        self.assertEqual(out.status, "sent")
        self.post_webhook(self.status_payload(out.provider_message_id, "delivered"))
        out.refresh_from_db()
        self.assertEqual(out.status, "delivered")
        self.post_webhook(self.status_payload(out.provider_message_id, "sent"))  # late/out-of-order
        out.refresh_from_db()
        self.assertEqual(out.status, "delivered")
        self.post_webhook(self.status_payload(out.provider_message_id, "failed", errors=[{"code": 131026, "title": "Message undeliverable"}]))
        out.refresh_from_db()
        self.assertEqual((out.status, out.error_code), ("failed", "131026"))
        conv = out.conversation
        conv.refresh_from_db()
        self.assertTrue(conv.needs_attention)
        r = self.client.get(f"/api/conversations/{conv.pk}/messages/")
        failed = [m for m in r.json() if m["direction"] == "out"][0]
        self.assertEqual(failed["error_message"], "Message undeliverable")

    def test_voice_message_from_customer_flags_attention(self):
        self.set_mode("automatic")
        with fake_llm() as llm, fake_graph() as graph:
            self.post_webhook(self.webhook_payload(msg_type="audio"))
        self.assertEqual(llm.calls, [])
        conv = Conversation.objects.get()
        self.assertTrue(conv.needs_attention)
        # media download goes through the official media endpoint
        self.assertTrue(any("audio-media-1" in r["url"] for r in graph.requests))

    @override_settings(DEBUG=True)
    def test_dev_simulator_runs_pipeline_but_is_not_reported_as_a_real_webhook(self):
        from apps.whatsapp.models import WhatsAppIntegration

        self.set_mode("manual")
        with fake_llm() as llm, fake_graph():
            r = self.client.post("/api/dev/simulate-inbound/", {"text": "Hi there", "wa_id": "15557770000"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["simulated"])
        self.assertEqual(len(llm.reply_calls()), 1)
        integration = WhatsAppIntegration.objects.get(workspace=self.workspace)
        self.assertIsNone(integration.last_webhook_at)
        self.assertIsNone(integration.last_message_event_at)

    def test_dev_simulator_disabled_without_debug(self):
        r = self.client.post("/api/dev/simulate-inbound/", {"text": "Hi"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_invalid_json_rejected(self):
        r = self.post_webhook(raw=b"{not json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(json.loads(json.dumps({"ok": 1})), {"ok": 1})
