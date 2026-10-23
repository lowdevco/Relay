"""Minimal client for Meta's official WhatsApp Cloud API (Graph API)."""

import logging

import requests
from django.conf import settings

from apps.core.logging import redact

logger = logging.getLogger(__name__)

# https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes
RETRYABLE_CODES = {4, 80007, 130429, 131000, 131016, 131056, 133004}
NON_RETRYABLE_HINTS = {
    190: "Invalid or expired access token.",
    10: "Permission denied for this phone number / app.",
    100: "Invalid parameter.",
    131026: "Message undeliverable (recipient may not be on WhatsApp).",
    131047: "More than 24 hours since the customer's last message; a template message is required.",
    131051: "Unsupported message type.",
    131053: "Media upload error (unsupported or invalid file).",
    132000: "Template parameter count mismatch.",
    132001: "Template does not exist.",
    368: "Account temporarily blocked for policy violations.",
}


class WhatsAppError(Exception):
    def __init__(self, message, code=None, http_status=None, retryable=False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.retryable = retryable


class WhatsAppNotConfigured(WhatsAppError):
    pass


class WhatsAppClient:
    def __init__(self, phone_number_id, access_token, *, session=None, timeout=None):
        if not phone_number_id or not access_token:
            missing = []
            if not phone_number_id:
                missing.append("phone number id")
            if not access_token:
                missing.append("access token (WHATSAPP_ACCESS_TOKEN)")
            raise WhatsAppNotConfigured("WhatsApp is not configured: missing " + ", ".join(missing), code="not_configured")
        self.phone_number_id = phone_number_id
        self.token = access_token
        self.session = session or requests.Session()
        self.timeout = timeout or settings.WHATSAPP_TIMEOUT
        self.base = f"{settings.WHATSAPP_GRAPH_BASE_URL.rstrip('/')}/{settings.WHATSAPP_GRAPH_VERSION}"

    @classmethod
    def for_integration(cls, integration):
        return cls(integration.phone_number_id, integration.effective_token)

    # ------------------------------------------------------------------
    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _request(self, method, url, **kwargs):
        try:
            resp = self.session.request(method, url, headers=self._headers(), timeout=self.timeout, **kwargs)
        except requests.Timeout as exc:
            raise WhatsAppError("WhatsApp API timed out.", code="timeout", retryable=True) from exc
        except requests.RequestException as exc:
            raise WhatsAppError(f"WhatsApp API request failed: {exc.__class__.__name__}", code="network", retryable=True) from exc
        if resp.status_code >= 400:
            raise self._error_from_response(resp)
        return resp

    @staticmethod
    def _error_from_response(resp):
        code = None
        message = f"HTTP {resp.status_code}"
        try:
            err = resp.json().get("error", {})
            code = err.get("code")
            details = (err.get("error_data") or {}).get("details")
            message = err.get("message") or message
            if details:
                message = f"{message} ({details})"
        except ValueError:
            pass
        hint = NON_RETRYABLE_HINTS.get(code)
        if hint:
            message = f"{hint} {message}"
        retryable = resp.status_code == 429 or resp.status_code >= 500 or code in RETRYABLE_CODES
        logger.warning("WhatsApp API error %s/%s: %s", resp.status_code, code, redact(message))
        return WhatsAppError(redact(message)[:500], code=code, http_status=resp.status_code, retryable=retryable)

    # ------------------------------------------------------------------
    def send_text(self, to, body, *, reply_to=None):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        if reply_to:
            payload["context"] = {"message_id": reply_to}
        return self._send(payload)

    def send_audio(self, to, media_id, *, voice=True):
        audio = {"id": media_id}
        if voice:
            audio["voice"] = True
        return self._send({"messaging_product": "whatsapp", "recipient_type": "individual", "to": to, "type": "audio", "audio": audio})

    def send_template(self, to, name, language_code, components=None):
        template = {"name": name, "language": {"code": language_code}}
        if components:
            template["components"] = components
        return self._send({"messaging_product": "whatsapp", "to": to, "type": "template", "template": template})

    def _send(self, payload):
        resp = self._request("POST", f"{self.base}/{self.phone_number_id}/messages", json=payload)
        data = resp.json()
        try:
            return data["messages"][0]["id"]
        except (KeyError, IndexError, TypeError) as exc:
            raise WhatsAppError("WhatsApp API returned no message id.", code="bad_response") from exc

    def mark_read(self, message_id):
        self._request(
            "POST",
            f"{self.base}/{self.phone_number_id}/messages",
            json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
        )

    def upload_media(self, content, mime_type, filename):
        resp = self._request(
            "POST",
            f"{self.base}/{self.phone_number_id}/media",
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (filename, content, mime_type)},
        )
        media_id = resp.json().get("id")
        if not media_id:
            raise WhatsAppError("Media upload returned no id.", code="bad_response")
        return media_id

    def download_media(self, media_id, max_bytes=16 * 1024 * 1024):
        meta = self._request("GET", f"{self.base}/{media_id}").json()
        url = meta.get("url")
        if not url:
            raise WhatsAppError("Media URL missing.", code="bad_response")
        if int(meta.get("file_size") or 0) > max_bytes:
            raise WhatsAppError("Media too large.", code="media_too_large")
        resp = self._request("GET", url, stream=True)
        chunks, total = [], 0
        for chunk in resp.iter_content(64 * 1024):
            total += len(chunk)
            if total > max_bytes:
                raise WhatsAppError("Media too large.", code="media_too_large")
            chunks.append(chunk)
        return b"".join(chunks), meta.get("mime_type", "application/octet-stream")

    def get_phone_number(self):
        return self._request(
            "GET",
            f"{self.base}/{self.phone_number_id}",
            params={"fields": "display_phone_number,verified_name,quality_rating,code_verification_status"},
        ).json()


def exchange_embedded_signup_code(code):
    """Exchange an Embedded Signup authorization code for a business token (server-side only)."""
    if not (settings.META_APP_ID and settings.META_APP_SECRET):
        raise WhatsAppNotConfigured("META_APP_ID and META_APP_SECRET are required for Embedded Signup.", code="not_configured")
    base = f"{settings.WHATSAPP_GRAPH_BASE_URL.rstrip('/')}/{settings.WHATSAPP_GRAPH_VERSION}"
    try:
        resp = requests.get(
            f"{base}/oauth/access_token",
            params={"client_id": settings.META_APP_ID, "client_secret": settings.META_APP_SECRET, "code": code},
            timeout=settings.WHATSAPP_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise WhatsAppError("Token exchange failed (network).", code="network", retryable=True) from exc
    if resp.status_code >= 400:
        raise WhatsAppClient._error_from_response(resp)
    token = resp.json().get("access_token")
    if not token:
        raise WhatsAppError("Token exchange returned no access token.", code="bad_response")
    return token
