"""Webhook verification + idempotent ingestion of WhatsApp Cloud API events."""

import hashlib
import hmac
import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.conversations.models import STATUS_ORDER, Contact, Conversation, Draft, MediaAsset, Message, MessageStatusEvent
from apps.core import jobs
from apps.core.models import UsageEvent
from apps.core.services import record_error, record_usage

from .models import WebhookEvent, WhatsAppIntegration

logger = logging.getLogger(__name__)

STATUS_MAP = {
    "sent": Message.Status.SENT,
    "delivered": Message.Status.DELIVERED,
    "read": Message.Status.READ,
    "played": Message.Status.PLAYED,
    "failed": Message.Status.FAILED,
}


def verify_signature(raw_body: bytes, header_value: str) -> bool:
    """Validate X-Hub-Signature-256 (HMAC-SHA256 of the raw body with the app secret)."""
    secret = settings.META_APP_SECRET
    if not secret or not header_value or not header_value.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_value.split("=", 1)[1].strip())


def _ts(value):
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _extract_content(m):
    """Return (message_type, text, media_id, mime) for an inbound message object."""
    mtype = m.get("type", "unknown")
    if mtype == "text":
        return Message.Type.TEXT, (m.get("text") or {}).get("body", ""), None, ""
    if mtype == "button":
        return Message.Type.TEXT, (m.get("button") or {}).get("text", ""), None, ""
    if mtype == "interactive":
        inter = m.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        return Message.Type.TEXT, reply.get("title", ""), None, ""
    if mtype == "audio":
        a = m.get("audio") or {}
        return Message.Type.AUDIO, "", a.get("id"), a.get("mime_type", "")
    if mtype == "image":
        i = m.get("image") or {}
        return Message.Type.IMAGE, i.get("caption", ""), i.get("id"), i.get("mime_type", "")
    if mtype == "document":
        d = m.get("document") or {}
        return Message.Type.DOCUMENT, d.get("caption", "") or d.get("filename", ""), d.get("id"), d.get("mime_type", "")
    return Message.Type.OTHER, f"[unsupported message type: {mtype}]", None, ""


def process_payload(payload, raw_body, signature_valid, simulated=False):
    """Persist everything in the payload. Returns jobs to dispatch after commit.

    Idempotent: the same body is processed once (WebhookEvent.event_hash) and each
    message is unique per (workspace, provider_message_id).
    `simulated` events (DEBUG dev tool) never update the integration's webhook health timestamps.
    """
    event_hash = hashlib.sha256(raw_body).hexdigest()
    try:
        with transaction.atomic():
            event = WebhookEvent.objects.create(event_hash=event_hash, payload=payload, signature_valid=signature_valid)
    except IntegrityError:
        logger.info("Duplicate webhook delivery ignored (%s)", event_hash[:12])
        return []

    created_jobs = []
    if payload.get("object") != "whatsapp_business_account":
        event.error = "unexpected object type"
        event.processed_at = timezone.now()
        event.save(update_fields=["error", "processed_at"])
        return []

    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            field = change.get("field")
            if field not in ("messages", "smb_message_echoes"):
                continue
            value = change.get("value") or {}
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            integration = WhatsAppIntegration.objects.select_related("workspace").filter(phone_number_id=phone_number_id).first()
            if integration is None:
                logger.warning("Webhook for unknown phone_number_id %s", phone_number_id)
                record_error(None, "whatsapp", "unknown_phone_number", f"Webhook for unknown phone number id {phone_number_id}")
                continue
            event.integration = integration
            now = timezone.now()
            if not simulated:
                WhatsAppIntegration.objects.filter(pk=integration.pk).update(last_webhook_at=now)
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts") or []}
            for m in value.get("message_echoes") or []:
                _ingest_owner_echo(integration, m)
            for m in value.get("messages") or []:
                created_jobs.extend(_ingest_message(integration, m, names, simulated))
            for s in value.get("statuses") or []:
                _ingest_status(integration, s)
            for err in value.get("errors") or []:
                record_error(integration.workspace, "whatsapp", err.get("code"), err.get("title") or err.get("message", ""))

    event.processed_at = timezone.now()
    event.save(update_fields=["integration", "processed_at"])
    return created_jobs


def _ingest_message(integration, m, names, simulated=False):
    workspace = integration.workspace
    wa_id = m.get("from")
    wamid = m.get("id")
    if not wa_id or not wamid:
        return []
    mtype, text, media_id, mime = _extract_content(m)
    sent_at = _ts(m.get("timestamp")) or timezone.now()
    with transaction.atomic():
        if Message.objects.filter(workspace=workspace, provider_message_id=wamid).exists():
            return []  # duplicate delivery of the same message
        contact, _ = Contact.objects.get_or_create(workspace=workspace, wa_id=wa_id)
        profile_name = names.get(wa_id) or ""
        if profile_name and contact.profile_name != profile_name:
            contact.profile_name = profile_name[:255]
            contact.save(update_fields=["profile_name"])
        conversation, _ = Conversation.objects.get_or_create(workspace=workspace, contact=contact)
        media = None
        if media_id:
            media = MediaAsset.objects.create(
                workspace=workspace,
                source=MediaAsset.Source.INBOUND,
                provider_media_id=media_id,
                mime_type=mime[:100],
                download_status="pending",
            )
        try:
            with transaction.atomic():
                message = Message.objects.create(
                    workspace=workspace,
                    conversation=conversation,
                    direction=Message.Direction.INBOUND,
                    sender_type=Message.Sender.CUSTOMER,
                    message_type=mtype,
                    text=text[:4096],
                    media=media,
                    provider_message_id=wamid,
                    status=Message.Status.RECEIVED,
                    provider_timestamp=sent_at,
                )
        except IntegrityError:
            return []
        preview = text[:120] if text else f"[{mtype}]"
        Conversation.objects.filter(pk=conversation.pk).update(
            last_message_at=timezone.now(),
            last_customer_message_at=sent_at,
            last_message_preview=preview,
            unread_count=F("unread_count") + 1,
            status=Conversation.Status.OPEN,
        )
        if not simulated:
            WhatsAppIntegration.objects.filter(pk=integration.pk).update(last_message_event_at=timezone.now())
        record_usage(
            workspace, UsageEvent.Kind.WHATSAPP_WEBHOOK, source="whatsapp",
            operation="simulated_inbound" if simulated else "inbound_message",
        )

        new_jobs = []
        if media is not None:
            new_jobs.append(
                jobs.enqueue("whatsapp.fetch_media", {"media_id": media.pk}, workspace=workspace, dedupe_key=f"media:{media.pk}")
            )
        new_jobs.append(
            jobs.enqueue(
                "automation.process_inbound",
                {"message_id": message.pk},
                workspace=workspace,
                dedupe_key=f"inbound:{message.pk}",
                max_attempts=3,
            )
        )
    return new_jobs


def _ingest_owner_echo(integration, m):
    """Coexistence: the owner replied from the WhatsApp Business app. Record it and pause the AI for that chat."""
    workspace = integration.workspace
    wa_id = m.get("to")
    wamid = m.get("id")
    if not wa_id or not wamid:
        return
    mtype, text, _media_id, _mime = _extract_content(m)
    sent_at = _ts(m.get("timestamp")) or timezone.now()
    with transaction.atomic():
        if Message.objects.filter(workspace=workspace, provider_message_id=wamid).exists():
            return
        contact, _ = Contact.objects.get_or_create(workspace=workspace, wa_id=wa_id)
        conversation, _ = Conversation.objects.get_or_create(workspace=workspace, contact=contact)
        try:
            with transaction.atomic():
                Message.objects.create(
                    workspace=workspace,
                    conversation=conversation,
                    direction=Message.Direction.OUTBOUND,
                    sender_type=Message.Sender.HUMAN,
                    message_type=mtype,
                    text=text[:4096],
                    provider_message_id=wamid,
                    status=Message.Status.SENT,
                    provider_timestamp=sent_at,
                )
        except IntegrityError:
            return
        # takeover_by stays empty: that marks it as a phone-app takeover, which expires on its own.
        Conversation.objects.filter(pk=conversation.pk).update(
            human_takeover=True,
            takeover_by=None,
            takeover_at=timezone.now(),
            last_message_at=timezone.now(),
            last_message_preview=(text[:120] if text else f"[{mtype}]"),
            needs_attention=False,
            unread_count=0,
        )
        conversation.bump_version()
        # A pending AI draft for this chat is out of date once the owner has answered.
        Draft.objects.filter(
            conversation=conversation, status__in=[Draft.Status.PENDING, Draft.Status.SUGGESTION]
        ).update(status=Draft.Status.SUPERSEDED)


def _ingest_status(integration, s):
    workspace = integration.workspace
    wamid = s.get("id")
    status = STATUS_MAP.get(s.get("status"))
    if not wamid or not status:
        return
    message = Message.objects.filter(workspace=workspace, provider_message_id=wamid).first()
    if message is None:
        return
    errors = s.get("errors") or []
    err_code = str(errors[0].get("code", "")) if errors else ""
    err_msg = (errors[0].get("title") or errors[0].get("message") or "") if errors else ""
    ts = _ts(s.get("timestamp"))
    try:
        with transaction.atomic():
            MessageStatusEvent.objects.create(
                message=message, status=status, error_code=err_code[:64], error_message=err_msg[:500], provider_timestamp=ts
            )
    except IntegrityError:
        return  # duplicate status
    if status == Message.Status.FAILED:
        Message.objects.filter(pk=message.pk).update(status=status, error_code=err_code[:64], error_message=err_msg[:500])
        record_error(workspace, "whatsapp", err_code or "delivery_failed", f"Delivery failed: {err_msg}", message_id=message.pk)
        Conversation.objects.filter(pk=message.conversation_id).update(
            needs_attention=True, attention_reason=f"Message delivery failed: {err_msg}"[:255]
        )
    elif STATUS_ORDER.get(status, -1) > STATUS_ORDER.get(message.status, -1) and message.status != Message.Status.FAILED:
        Message.objects.filter(pk=message.pk).update(status=status)
