"""Outbound messaging: the only place that calls the WhatsApp send API."""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.conversations.models import Conversation, Message
from apps.core.exceptions import ServiceError
from apps.core.models import UsageEvent
from apps.core.services import record_error, record_usage

from .client import WhatsAppClient, WhatsAppError
from .models import WhatsAppIntegration

logger = logging.getLogger(__name__)


class SendError(ServiceError):
    def __init__(self, message, code="send_failed", retryable=False, message_obj=None):
        super().__init__(message, code=code, status_code=502 if code not in ("window_closed", "not_configured") else 409)
        self.retryable = retryable
        self.message_obj = message_obj


def get_client(workspace):
    integration = WhatsAppIntegration.objects.filter(workspace=workspace).first()
    if integration is None or not integration.phone_number_id:
        raise SendError(
            "WhatsApp is not connected for this workspace. Configure the phone number on the Integrations page.",
            code="not_configured",
        )
    try:
        return WhatsAppClient.for_integration(integration)
    except WhatsAppError as exc:
        raise SendError(exc.message, code="not_configured") from exc


def _create_outbound(conversation, *, text, sender_type, message_type, user, idempotency_key, ai_generation, media=None):
    try:
        with transaction.atomic():
            return (
                Message.objects.create(
                    workspace=conversation.workspace,
                    conversation=conversation,
                    direction=Message.Direction.OUTBOUND,
                    sender_type=sender_type,
                    message_type=message_type,
                    text=text,
                    media=media,
                    status=Message.Status.SENDING,
                    created_by=user if (user is not None and user.is_authenticated) else None,
                    idempotency_key=idempotency_key,
                    ai_generation=ai_generation,
                ),
                True,
            )
    except IntegrityError:
        existing = Message.objects.get(workspace=conversation.workspace, idempotency_key=idempotency_key)
        return existing, False


def _deliver(conversation, message, send_fn):
    try:
        wamid = send_fn()
    except WhatsAppError as exc:
        Message.objects.filter(pk=message.pk).update(
            status=Message.Status.FAILED, error_code=str(exc.code or "")[:64], error_message=exc.message[:500]
        )
        message.refresh_from_db()
        record_error(conversation.workspace, "whatsapp", exc.code or "send_failed", exc.message, message_id=message.pk)
        record_usage(
            conversation.workspace,
            UsageEvent.Kind.WHATSAPP_SEND,
            source="whatsapp",
            operation=message.message_type,
            success=False,
            error_code=str(exc.code or "")[:64],
            message=exc.message,
        )
        raise SendError(exc.message, code=f"whatsapp_{exc.code or 'error'}", retryable=exc.retryable, message_obj=message) from exc
    now = timezone.now()
    Message.objects.filter(pk=message.pk).update(
        provider_message_id=wamid, status=Message.Status.SENT, sent_at=now, error_code="", error_message=""
    )
    message.refresh_from_db()
    preview = message.text[:120] if message.message_type == Message.Type.TEXT else "[voice note]"
    Conversation.objects.filter(pk=conversation.pk).update(last_message_at=now, last_message_preview=preview)
    record_usage(conversation.workspace, UsageEvent.Kind.WHATSAPP_SEND, source="whatsapp", operation=message.message_type)
    return message


def ensure_window_open(conversation):
    if not conversation.within_service_window():
        raise SendError(
            "The 24-hour customer service window is closed. Only an approved template message can be sent "
            "until the customer writes again.",
            code="window_closed",
        )


def send_text(conversation, text, *, sender_type, user=None, idempotency_key=None, ai_generation=None):
    text = (text or "").strip()
    if not text:
        raise SendError("Message text is empty.", code="empty")
    if len(text) > 4096:
        raise SendError("Message exceeds WhatsApp's 4096 character limit.", code="too_long")
    ensure_window_open(conversation)
    client = get_client(conversation.workspace)
    message, created = _create_outbound(
        conversation,
        text=text,
        sender_type=sender_type,
        message_type=Message.Type.TEXT,
        user=user,
        idempotency_key=idempotency_key,
        ai_generation=ai_generation,
    )
    if not created and message.status != Message.Status.FAILED:
        return message  # already sent (duplicate request) - never send twice
    return _deliver(conversation, message, lambda: client.send_text(conversation.contact.wa_id, text))


def retry_message(message):
    """Resend a failed outbound text message (same row, so no duplicates)."""
    if message.direction != Message.Direction.OUTBOUND or message.status != Message.Status.FAILED:
        raise SendError("Only failed outbound messages can be retried.", code="not_retryable")
    if message.message_type != Message.Type.TEXT:
        raise SendError("Only text messages can be retried; regenerate voice notes instead.", code="not_retryable")
    conversation = message.conversation
    ensure_window_open(conversation)
    client = get_client(conversation.workspace)
    Message.objects.filter(pk=message.pk).update(status=Message.Status.SENDING)
    return _deliver(conversation, message, lambda: client.send_text(conversation.contact.wa_id, message.text))


def send_voice(conversation, text, media, *, sender_type, user=None, idempotency_key=None, ai_generation=None, as_voice=True):
    ensure_window_open(conversation)
    client = get_client(conversation.workspace)
    message, created = _create_outbound(
        conversation,
        text=text,
        sender_type=sender_type,
        message_type=Message.Type.AUDIO,
        user=user,
        idempotency_key=idempotency_key,
        ai_generation=ai_generation,
        media=media,
    )
    if not created and message.status != Message.Status.FAILED:
        return message

    def _send():
        with media.file.open("rb") as fh:
            content = fh.read()
        ext = "ogg" if media.mime_type.startswith("audio/ogg") else "mp3"
        media_id = client.upload_media(content, media.mime_type, f"reply.{ext}")
        media.provider_media_id = media_id
        media.save(update_fields=["provider_media_id"])
        return client.send_audio(conversation.contact.wa_id, media_id, voice=as_voice)

    return _deliver(conversation, message, _send)


def send_template(conversation, name, language_code, *, user=None):
    client = get_client(conversation.workspace)
    message, _ = _create_outbound(
        conversation,
        text=f"[template: {name} ({language_code})]",
        sender_type=Message.Sender.HUMAN,
        message_type=Message.Type.TEMPLATE,
        user=user,
        idempotency_key=None,
        ai_generation=None,
    )
    return _deliver(conversation, message, lambda: client.send_template(conversation.contact.wa_id, name, language_code))
