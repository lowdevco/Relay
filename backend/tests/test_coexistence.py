"""Coexistence: AI hours, owner replies from the phone app (smb_message_echoes), takeover expiry. External APIs MOCKED."""

import time
from datetime import datetime, timedelta, timezone as dt_timezone

from django.test import override_settings
from django.utils import timezone

from apps.automation import rules
from apps.automation.models import AutomationSettings
from apps.conversations.models import Conversation, Draft, Message

from .helpers import BaseTestCase, fake_graph, fake_llm


def echo_payload(phone_number_id, text="I'll check and get back to you", to="15551234567", wamid="wamid.ECHO1"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": "smb_message_echoes", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "15550100", "phone_number_id": phone_number_id},
            "message_echoes": [{"from": "15550100", "to": to, "id": wamid, "timestamp": str(int(time.time())),
                                "type": "text", "text": {"body": text}}],
        }}]}],
    }


class AIHoursRuleTests(BaseTestCase):
    def hours(self, ranges):
        a = AutomationSettings(operating_hours_enabled=True, operating_hours=ranges)
        return lambda y, m, d, hh, mm: rules.within_operating_hours(a, "UTC", datetime(y, m, d, hh, mm, tzinfo=dt_timezone.utc))

    def test_overnight_range_covers_evening_and_next_morning(self):
        at = self.hours({"mon": [["22:00", "06:00"]]})  # 2026-10-26 is a Monday
        self.assertTrue(at(2026, 10, 26, 23, 0))
        self.assertTrue(at(2026, 10, 27, 5, 59))  # Tuesday morning, from Monday's range
        self.assertFalse(at(2026, 10, 27, 6, 0))
        self.assertFalse(at(2026, 10, 26, 5, 0))  # Monday morning belongs to Sunday, which is off
        self.assertFalse(at(2026, 10, 26, 12, 0))

    def test_overnight_range_accepted_by_api(self):
        r = self.client.put("/api/automation/", {"operating_hours": {"mon": [["22:00", "06:00"]]}}, format="json")
        self.assertEqual(r.status_code, 200)
        r = self.client.put("/api/automation/", {"operating_hours": {"mon": [["09:00", "09:00"]]}}, format="json")
        self.assertEqual(r.status_code, 400)


class CoexistencePipelineTests(BaseTestCase):
    def test_outside_ai_hours_the_ai_is_silent(self):
        self.set_mode("automatic")
        AutomationSettings.objects.filter(workspace=self.workspace).update(operating_hours_enabled=True, operating_hours={})
        with fake_llm() as llm, fake_graph() as graph:
            self.post_webhook(self.webhook_payload())
        self.assertEqual(llm.reply_calls(), [])
        self.assertEqual(graph.sends, [])
        self.assertFalse(Draft.objects.exists())
        self.assertTrue(Message.objects.filter(direction="in").exists())

    def test_owner_echo_records_message_pauses_ai_and_supersedes_draft(self):
        self.set_mode("approval")
        with fake_llm(), fake_graph():
            self.post_webhook(self.webhook_payload())
            self.assertEqual(Draft.objects.get().status, "pending")
            self.post_webhook(echo_payload(self.phone_number_id))
            self.post_webhook(echo_payload(self.phone_number_id))  # duplicate delivery
            with fake_llm() as llm:
                self.post_webhook(self.webhook_payload(text="Thanks!"))
        out = Message.objects.get(direction="out")
        self.assertEqual((out.sender_type, out.text), ("human", "I'll check and get back to you"))
        conv = Conversation.objects.get()
        self.assertTrue(conv.human_takeover)
        self.assertIsNone(conv.takeover_by)
        self.assertEqual(Draft.objects.get().status, "superseded")
        self.assertEqual(llm.reply_calls(), [])

    def test_phone_takeover_expires_but_relay_takeover_does_not(self):
        self.set_mode("manual")
        with fake_llm(), fake_graph():
            self.post_webhook(echo_payload(self.phone_number_id))
        conv = Conversation.objects.get()
        Conversation.objects.filter(pk=conv.pk).update(takeover_at=timezone.now() - timedelta(minutes=121))
        with fake_llm() as llm, fake_graph():
            self.post_webhook(self.webhook_payload())
        self.assertEqual(len(llm.reply_calls()), 1)
        self.assertFalse(Conversation.objects.get().human_takeover)

        # A takeover clicked in Relay stays put however old it is.
        Conversation.objects.filter(pk=conv.pk).update(
            human_takeover=True, takeover_by=self.user, takeover_at=timezone.now() - timedelta(days=3)
        )
        with fake_llm() as llm, fake_graph():
            self.post_webhook(self.webhook_payload(text="Hello?"))
        self.assertEqual(llm.reply_calls(), [])

    @override_settings(DEBUG=True)
    def test_simulator_owner_echo(self):
        with fake_llm(), fake_graph():
            r = self.client.post("/api/dev/simulate-inbound/", {"kind": "owner_echo", "text": "On my way", "wa_id": "15557770000"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Conversation.objects.get(contact__wa_id="15557770000").human_takeover)
