"""ElevenLabs voice replies (ElevenLabs + Graph API MOCKED)."""

from unittest import mock

from django.test import override_settings

from apps.automation.models import AutomationSettings
from apps.conversations.models import Conversation, Draft, Message
from apps.voice.elevenlabs import VoiceError, detect_audio_mime
from apps.voice.models import VoiceGeneration, VoiceSettings

from .helpers import BaseTestCase, fake_graph, fake_llm

OGG_OPUS = b"OggS\x00\x02" + b"\x00" * 22 + b"OpusHead" + b"\x00" * 200


def enable_voice(ws, **extra):
    VoiceSettings.objects.filter(workspace=ws).update(enabled=True, voice_id="voice123", voice_category="premade", **extra)


@override_settings(ELEVENLABS_API_KEY="test-eleven-key-123456")
class VoiceTests(BaseTestCase):
    def test_settings_validation(self):
        r = self.client.put("/api/voice/", {"enabled": True}, format="json")
        self.assertEqual(r.status_code, 400)  # no voice selected
        r = self.client.put("/api/voice/", {"enabled": True, "voice_id": "abc", "voice_category": "cloned"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("consent", r.content.decode())
        r = self.client.put("/api/voice/", {"enabled": True, "voice_id": "abc", "voice_category": "cloned",
                                            "clone_consent_confirmed": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(VoiceSettings.objects.get(workspace=self.workspace).clone_consent_at)

    @override_settings(ELEVENLABS_API_KEY="")
    def test_cannot_enable_without_key(self):
        r = self.client.put("/api/voice/", {"enabled": True, "voice_id": "abc"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("ELEVENLABS_API_KEY", r.content.decode())

    def test_audio_format_detection(self):
        self.assertEqual(detect_audio_mime(OGG_OPUS), "audio/ogg; codecs=opus")
        self.assertEqual(detect_audio_mime(b"ID3\x03rest"), "audio/mpeg")
        self.assertEqual(detect_audio_mime(b"RIFF...."), "")

    def test_voice_reply_on_approval_uploads_and_sends_voice_note(self):
        enable_voice(self.workspace)
        AutomationSettings.objects.filter(workspace=self.workspace).update(mode="approval", default_reply_format="voice")
        with fake_llm(), fake_graph() as graph, mock.patch("apps.voice.elevenlabs.ElevenLabsClient.synthesize", return_value=OGG_OPUS) as synth:
            self.post_webhook(self.webhook_payload())
            draft = Draft.objects.get()
            self.assertEqual(draft.reply_format, "voice")
            r = self.client.post(f"/api/drafts/{draft.pk}/approve/", {}, format="json")
            self.assertEqual(r.status_code, 200, r.content)
        synth.assert_called_once()
        upload = [x for x in graph.requests if x["url"].endswith("/media")][0]
        self.assertEqual(upload["data"]["type"], "audio/ogg")
        send = graph.sends[0]
        self.assertEqual(send["json"]["type"], "audio")
        self.assertTrue(send["json"]["audio"]["voice"])
        msg = Message.objects.get(direction="out")
        self.assertEqual((msg.message_type, msg.media.mime_type), ("audio", "audio/ogg"))
        self.assertEqual(VoiceGeneration.objects.get().status, "success")
        r = self.client.get(f"/api/media/{msg.media_id}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content)[:4], b"OggS")

    def test_voice_failure_falls_back_to_text_in_automatic_mode(self):
        enable_voice(self.workspace)
        AutomationSettings.objects.filter(workspace=self.workspace).update(
            mode="automatic", default_reply_format="voice", voice_requires_approval=False
        )
        with fake_llm(), fake_graph() as graph, mock.patch(
            "apps.voice.elevenlabs.ElevenLabsClient.synthesize", side_effect=VoiceError("quota exceeded", code="elevenlabs_429")
        ):
            self.post_webhook(self.webhook_payload())
        self.assertEqual(len(graph.sends), 1)
        self.assertEqual(graph.sends[0]["json"]["type"], "text")
        self.assertEqual(VoiceGeneration.objects.get().status, "failed")

    def test_voice_requires_approval_by_default(self):
        enable_voice(self.workspace)
        AutomationSettings.objects.filter(workspace=self.workspace).update(mode="automatic", default_reply_format="voice")
        with fake_llm(), fake_graph() as graph:
            self.post_webhook(self.webhook_payload())
        self.assertEqual(graph.sends, [])
        self.assertIn("voice_requires_approval", Draft.objects.get().review_reasons)

    def test_text_works_when_voice_not_configured(self):
        AutomationSettings.objects.filter(workspace=self.workspace).update(mode="automatic", default_reply_format="voice")
        with fake_llm(), fake_graph() as graph:
            self.post_webhook(self.webhook_payload())  # voice disabled -> text reply
        self.assertEqual(graph.sends[0]["json"]["type"], "text")
        self.assertTrue(Conversation.objects.exists())
