"""ElevenLabs REST client (https://elevenlabs.io/docs/api-reference)."""

import requests
from django.conf import settings


class VoiceError(Exception):
    def __init__(self, message, code="voice_error", retryable=False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable


def is_configured():
    return bool(settings.ELEVENLABS_API_KEY)


class ElevenLabsClient:
    def __init__(self, api_key=None, *, session=None, timeout=None):
        self.api_key = api_key if api_key is not None else settings.ELEVENLABS_API_KEY
        if not self.api_key:
            raise VoiceError("ElevenLabs is not configured (missing ELEVENLABS_API_KEY).", code="not_configured")
        self.base = settings.ELEVENLABS_BASE_URL.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout or settings.ELEVENLABS_TIMEOUT

    def _request(self, method, path, **kwargs):
        try:
            resp = self.session.request(
                method, f"{self.base}{path}", headers={"xi-api-key": self.api_key}, timeout=self.timeout, **kwargs
            )
        except requests.Timeout as exc:
            raise VoiceError("ElevenLabs request timed out.", code="timeout", retryable=True) from exc
        except requests.RequestException as exc:
            raise VoiceError(f"ElevenLabs request failed: {exc.__class__.__name__}", code="network", retryable=True) from exc
        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json().get("detail")
                detail = body.get("message", "") if isinstance(body, dict) else str(body or "")
            except ValueError:
                detail = resp.text[:200]
            raise VoiceError(
                f"ElevenLabs API error ({resp.status_code}): {detail[:200]}",
                code=f"elevenlabs_{resp.status_code}",
                retryable=resp.status_code in (429, 500, 502, 503, 504),
            )
        return resp

    def list_voices(self):
        data = self._request("GET", "/v1/voices").json()
        return [
            {
                "voice_id": v.get("voice_id"),
                "name": v.get("name"),
                "category": v.get("category", ""),
                "labels": v.get("labels") or {},
                "preview_url": v.get("preview_url", ""),
            }
            for v in data.get("voices", [])
        ]

    def subscription(self):
        data = self._request("GET", "/v1/user/subscription").json()
        return {
            "tier": data.get("tier"),
            "character_count": data.get("character_count"),
            "character_limit": data.get("character_limit"),
            "can_use_instant_voice_cloning": data.get("can_use_instant_voice_cloning"),
        }

    def synthesize(self, text, voice_id, *, model_id, language_code="", output_format=None, stability=None, similarity_boost=None):
        body = {"text": text, "model_id": model_id}
        if language_code:
            body["language_code"] = language_code
        voice_settings = {}
        if stability is not None:
            voice_settings["stability"] = stability
        if similarity_boost is not None:
            voice_settings["similarity_boost"] = similarity_boost
        if voice_settings:
            body["voice_settings"] = voice_settings
        resp = self._request(
            "POST",
            f"/v1/text-to-speech/{voice_id}",
            params={"output_format": output_format or settings.ELEVENLABS_OUTPUT_FORMAT},
            json=body,
        )
        audio = resp.content
        if not audio:
            raise VoiceError("ElevenLabs returned empty audio.", code="empty_audio")
        return audio


def detect_audio_mime(data: bytes):
    """Identify the container from magic bytes. WhatsApp voice notes need Ogg/Opus."""
    if data[:4] == b"OggS":
        return "audio/ogg; codecs=opus" if b"OpusHead" in data[:200] else "audio/ogg"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    return ""
