"""
Inbound message pipeline: context -> AI (selected provider) -> validation -> rules ->
auto-send / approval queue / escalation. Every decision is enforced here, server-side.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.ai.models import AIGeneration
from apps.ai.service import AIService, AIServiceError
from apps.conversations.models import Conversation, Draft, Message
from apps.core import jobs
from apps.core.services import audit, record_error
from apps.voice.elevenlabs import VoiceError
from apps.voice.models import VoiceSettings
from apps.voice.service import synthesize_for_whatsapp, voice_readiness
from apps.whatsapp import sender

from . import rules
from .models import AutomationSettings

logger = logging.getLogger(__name__)

STALE_AFTER = timedelta(hours=1)
SUMMARY_EVERY = 10


def flag_attention(conversation, reason):
    Conversation.objects.filter(pk=conversation.pk).update(needs_attention=True, attention_reason=reason[:255])


def resolve_reply_format(conversation, automation, voice_settings):
    wanted = conversation.reply_format if conversation.reply_format != "inherit" else automation.default_reply_format
    if wanted == "voice" and not voice_readiness(voice_settings):
        return "voice"
    return "text"


def _consecutive_failures(conversation):
    count = 0
    for status in (
        AIGeneration.objects.filter(conversation=conversation, operation=AIGeneration.Operation.REPLY)
        .order_by("-created_at")
        .values_list("status", flat=True)[:10]
    ):
        if status == AIGeneration.Status.SUCCESS:
            break
        count += 1
    return count


def _create_draft(conversation, message, data, generation, mode, reasons, reply_format, error=""):
    with transaction.atomic():
        Draft.objects.filter(
            conversation=conversation, status__in=[Draft.Status.PENDING, Draft.Status.SUGGESTION]
        ).update(status=Draft.Status.SUPERSEDED)
        return Draft.objects.create(
            workspace=conversation.workspace,
            conversation=conversation,
            in_reply_to=message,
            text=data.get("reply_text", ""),
            status=Draft.Status.SUGGESTION if mode == "manual" else Draft.Status.PENDING,
            reply_format=reply_format,
            generation=generation,
            intent=data.get("intent", ""),
            confidence=data.get("confidence"),
            review_reasons=reasons,
            error_message=error[:500],
        )


def _claim_send(conversation, start_version, message):
    """Atomically confirm nobody took over / paused / acted since we started."""
    if Message.objects.filter(
        conversation=conversation, direction=Message.Direction.INBOUND, created_at__gt=message.created_at
    ).exists():
        return False, "newer_customer_message"
    with transaction.atomic():
        claimed = (
            Conversation.objects.select_for_update()
            .filter(pk=conversation.pk, state_version=start_version, human_takeover=False, automation_paused=False)
            .update(last_message_at=timezone.now())
        )
    return claimed == 1, "state_changed"


def _auto_rate_exceeded(conversation, automation):
    since = timezone.now() - timedelta(hours=1)
    sent = Message.objects.filter(
        conversation=conversation, sender_type=Message.Sender.AI_AUTO, created_at__gte=since
    ).count()
    return sent >= automation.max_auto_replies_per_hour


def _expire_owner_takeover(conversation, automation):
    """Owner takeovers from the phone app (takeover_by is None) end after owner_takeover_minutes.
    Takeovers clicked in Relay (takeover_by set) stay until someone resumes the AI."""
    if not conversation.human_takeover or conversation.takeover_by_id or not conversation.takeover_at:
        return
    if timezone.now() - conversation.takeover_at < timedelta(minutes=automation.owner_takeover_minutes):
        return
    Conversation.objects.filter(pk=conversation.pk, takeover_by__isnull=True).update(
        human_takeover=False, takeover_at=None
    )
    conversation.bump_version()
    conversation.refresh_from_db(fields=["human_takeover", "takeover_at"])


def process_inbound(message_id):
    message = Message.objects.select_related("conversation__contact", "workspace").get(pk=message_id)
    if message.direction != Message.Direction.INBOUND:
        return "skipped:not_inbound"
    conversation = message.conversation
    workspace = message.workspace
    automation, _ = AutomationSettings.objects.get_or_create(workspace=workspace)
    voice_settings, _ = VoiceSettings.objects.get_or_create(workspace=workspace)
    _expire_owner_takeover(conversation, automation)
    start_version = conversation.state_version
    mode = rules.effective_mode(conversation, automation)

    if message.message_type != Message.Type.TEXT or not message.text.strip():
        flag_attention(conversation, f"Customer sent a {message.message_type} message; please review it.")
        return "skipped:non_text"

    if Message.objects.filter(
        conversation=conversation, direction=Message.Direction.INBOUND, created_at__gt=message.created_at
    ).exists():
        return "skipped:newer_message"

    flags = rules.keyword_flags(message.text, automation)
    if flags["escalate"]:
        flag_attention(conversation, "Customer asked to speak to a person.")

    if mode == "off":
        return "skipped:automation_off"
    # Outside AI hours the owner handles chats from the phone; the AI stays completely silent.
    if not rules.within_operating_hours(automation, workspace.timezone):
        return "skipped:outside_ai_hours"

    reply_format = resolve_reply_format(conversation, automation, voice_settings)
    service = AIService(workspace)
    try:
        result = service.generate_reply(conversation, message, reply_format)
    except AIServiceError as exc:
        failures = _consecutive_failures(conversation)
        reason = f"AI could not generate a reply ({exc.code})."
        if failures >= automation.max_consecutive_failures:
            reason = f"AI failed {failures} times in a row; manual reply needed."
        flag_attention(conversation, reason)
        record_error(workspace, "pipeline", exc.code, exc.message, conversation_id=conversation.pk)
        return f"error:{exc.code}"

    data = result.data
    generation = result.generation
    prompt = result.prompt
    knowledge_ids = prompt.context["knowledge_ids"]
    from apps.ai.models import KnowledgeEntry

    knowledge = list(KnowledgeEntry.objects.filter(workspace=workspace, pk__in=knowledge_ids))
    history_texts = list(
        Message.objects.filter(conversation=conversation, direction=Message.Direction.INBOUND)
        .order_by("-created_at")
        .values_list("text", flat=True)[:10]
    )

    if data["suggested_action"] == "no_reply":
        return "no_reply"

    reasons = rules.review_reasons(
        data,
        customer_text=message.text,
        knowledge_texts=[k.content for k in knowledge] + [k.title for k in knowledge],
        automation=automation,
        history_texts=history_texts,
    )
    escalate = rules.should_escalate(data, flags)
    if escalate:
        flag_attention(conversation, conversation.attention_reason or f"Escalated by AI ({data['reason_code']}).")
        reasons.append("escalated")

    if mode == "automatic" and not reasons:
        if not conversation.within_service_window():
            reasons.append("window_closed")
        if _auto_rate_exceeded(conversation, automation):
            reasons.append("auto_reply_rate_limit")
        if message.provider_timestamp and timezone.now() - message.provider_timestamp > STALE_AFTER:
            reasons.append("stale_message")
        if reply_format == "voice" and automation.voice_requires_approval:
            reasons.append("voice_requires_approval")

    if mode == "automatic" and not reasons:
        try:
            evaluation = service.evaluate_reply(
                message.text, data["reply_text"], knowledge, conversation=conversation, message=message
            ).data
            if evaluation["verdict"] != "pass":
                reasons.append("evaluation_failed")
        except AIServiceError:
            reasons.append("evaluation_unavailable")

    if mode != "automatic" or reasons:
        draft = _create_draft(conversation, message, data, generation, mode, reasons, reply_format)
        _maybe_summarize(conversation)
        return f"draft:{draft.status}"

    outcome = _auto_send(conversation, message, data, generation, reply_format, start_version)
    _maybe_summarize(conversation)
    return outcome


def _auto_send(conversation, message, data, generation, reply_format, start_version):
    ok, why = _claim_send(conversation, start_version, message)
    if not ok:
        _create_draft(conversation, message, data, generation, "approval", [why], reply_format)
        return f"draft:{why}"
    conversation.refresh_from_db()
    text = data["reply_text"]
    try:
        if reply_format == "voice":
            try:
                media, is_voice, _ = synthesize_for_whatsapp(conversation.workspace, text, conversation=conversation)
                sent = sender.send_voice(
                    conversation, text, media, sender_type=Message.Sender.AI_AUTO,
                    idempotency_key=f"auto:{message.pk}", ai_generation=generation, as_voice=is_voice,
                )
                return f"sent:{sent.pk}"
            except VoiceError as exc:
                logger.warning("Voice generation failed, falling back to text: %s", exc.message)
        sent = sender.send_text(
            conversation, text, sender_type=Message.Sender.AI_AUTO,
            idempotency_key=f"auto:{message.pk}", ai_generation=generation,
        )
    except sender.SendError as exc:
        _create_draft(conversation, message, data, generation, "approval", ["send_failed"], reply_format, error=exc.message)
        flag_attention(conversation, f"Automatic reply failed to send: {exc.message}")
        return f"send_failed:{exc.code}"
    audit(conversation.workspace, None, "ai.auto_reply_sent", sent, provider=generation.provider, model=generation.model)
    return f"sent:{sent.pk}"


def _maybe_summarize(conversation):
    from apps.ai.models import AISettings

    window = AISettings.objects.filter(workspace=conversation.workspace).values_list("history_messages", flat=True).first() or 12
    total = Message.objects.filter(conversation=conversation).count()
    if total > window and total % SUMMARY_EVERY == 0:
        job = jobs.enqueue(
            "automation.summarize",
            {"conversation_id": conversation.pk},
            workspace=conversation.workspace,
            dedupe_key=f"summary:{conversation.pk}:{total}",
            max_attempts=2,
        )
        transaction.on_commit(lambda: jobs.dispatch([job]))


def summarize(conversation_id):
    from apps.ai.models import AISettings
    from apps.conversations.models import ConversationSummary

    conversation = Conversation.objects.select_related("workspace").get(pk=conversation_id)
    window = AISettings.objects.get(workspace=conversation.workspace).history_messages
    msgs = list(Message.objects.filter(conversation=conversation).order_by("-created_at")[window:window + 60])[::-1]
    if not msgs:
        return
    existing = ConversationSummary.objects.filter(conversation=conversation).first()
    result = AIService(conversation.workspace).summarize_conversation(
        conversation, msgs, existing.summary if existing else ""
    )
    ConversationSummary.objects.update_or_create(
        conversation=conversation,
        defaults={"summary": result.data["summary"], "covers_until": msgs[-1], "provider": result.provider},
    )
