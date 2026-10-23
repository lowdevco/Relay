"""Human actions on conversations. Each one bumps state_version so in-flight AI work aborts."""

from django.db import transaction
from django.utils import timezone

from apps.ai.service import AIService
from apps.core.exceptions import ServiceError
from apps.core.services import audit
from apps.voice.elevenlabs import VoiceError
from apps.voice.service import synthesize_for_whatsapp
from apps.whatsapp import sender

from .models import Conversation, Draft, Message


def human_send(conversation, text, user):
    conversation.bump_version()
    message = sender.send_text(conversation, text, sender_type=Message.Sender.HUMAN, user=user)
    Draft.objects.filter(
        conversation=conversation, status__in=[Draft.Status.PENDING, Draft.Status.SUGGESTION]
    ).update(status=Draft.Status.SUPERSEDED)
    Conversation.objects.filter(pk=conversation.pk).update(needs_attention=False, attention_reason="", unread_count=0)
    audit(conversation.workspace, user, "message.sent_by_human", message)
    return message


def approve_draft(draft, user, *, text=None, reply_format=None):
    final_text = (text if text is not None else draft.text).strip()
    if not final_text:
        raise ServiceError("Reply text is empty.", code="empty")
    fmt = reply_format or draft.reply_format
    # Claim the draft atomically so a double click / two agents cannot send it twice.
    with transaction.atomic():
        claimed = Draft.objects.filter(
            pk=draft.pk, status__in=[Draft.Status.PENDING, Draft.Status.SUGGESTION, Draft.Status.FAILED]
        ).update(status=Draft.Status.APPROVED, decided_by=user, decided_at=timezone.now())
    if not claimed:
        raise ServiceError("This draft was already handled.", code="draft_handled", status_code=409)
    draft.refresh_from_db()
    conversation = draft.conversation
    conversation.bump_version()
    edited = final_text != draft.text
    try:
        if fmt == "voice":
            media, is_voice, _ = synthesize_for_whatsapp(conversation.workspace, final_text, conversation=conversation)
            message = sender.send_voice(
                conversation, final_text, media, sender_type=Message.Sender.AI_APPROVED, user=user,
                idempotency_key=f"draft:{draft.pk}:voice", ai_generation=draft.generation, as_voice=is_voice,
            )
        else:
            message = sender.send_text(
                conversation, final_text, sender_type=Message.Sender.AI_APPROVED, user=user,
                idempotency_key=f"draft:{draft.pk}", ai_generation=draft.generation,
            )
    except (sender.SendError, VoiceError) as exc:
        Draft.objects.filter(pk=draft.pk).update(status=Draft.Status.FAILED, error_message=exc.message[:500])
        raise ServiceError(exc.message, code=getattr(exc, "code", "send_failed"), status_code=502) from exc
    Draft.objects.filter(pk=draft.pk).update(
        status=Draft.Status.SENT, sent_message=message, text=final_text, error_message=""
    )
    Conversation.objects.filter(pk=conversation.pk).update(needs_attention=False, attention_reason="", unread_count=0)
    audit(conversation.workspace, user, "draft.approved", draft, edited=edited, reply_format=fmt)
    return message


def reject_draft(draft, user):
    updated = Draft.objects.filter(
        pk=draft.pk, status__in=[Draft.Status.PENDING, Draft.Status.SUGGESTION, Draft.Status.FAILED]
    ).update(status=Draft.Status.REJECTED, decided_by=user, decided_at=timezone.now())
    if not updated:
        raise ServiceError("This draft was already handled.", code="draft_handled", status_code=409)
    audit(draft.workspace, user, "draft.rejected", draft)


def regenerate_draft(conversation, user, reply_format="text"):
    """Generate a fresh draft for the latest customer message (always queued, never auto-sent)."""
    last_in = (
        Message.objects.filter(conversation=conversation, direction=Message.Direction.INBOUND, message_type=Message.Type.TEXT)
        .order_by("-created_at")
        .first()
    )
    if last_in is None:
        raise ServiceError("There is no customer text message to reply to.", code="nothing_to_reply")
    result = AIService(conversation.workspace).generate_reply(conversation, last_in, reply_format)
    data = result.data
    with transaction.atomic():
        Draft.objects.filter(
            conversation=conversation, status__in=[Draft.Status.PENDING, Draft.Status.SUGGESTION]
        ).update(status=Draft.Status.SUPERSEDED)
        draft = Draft.objects.create(
            workspace=conversation.workspace,
            conversation=conversation,
            in_reply_to=last_in,
            text=data["reply_text"],
            status=Draft.Status.PENDING,
            reply_format=reply_format,
            generation=result.generation,
            intent=data["intent"],
            confidence=data["confidence"],
            review_reasons=["regenerated_by_user"] + (["model_requested_review"] if data["needs_human_review"] else []),
        )
    audit(conversation.workspace, user, "draft.regenerated", draft, provider=result.provider)
    return draft


def take_over(conversation, user):
    Conversation.objects.filter(pk=conversation.pk).update(
        human_takeover=True, takeover_by=user, takeover_at=timezone.now()
    )
    conversation.bump_version()
    audit(conversation.workspace, user, "conversation.takeover", conversation)


def resume_ai(conversation, user):
    Conversation.objects.filter(pk=conversation.pk).update(
        human_takeover=False, takeover_by=None, takeover_at=None, automation_paused=False
    )
    conversation.bump_version()
    audit(conversation.workspace, user, "conversation.resume_ai", conversation)
