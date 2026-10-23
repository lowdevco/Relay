from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import Workspace

CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)


class Contact(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="contacts")
    wa_id = models.CharField(max_length=32)  # WhatsApp user id (phone number in E.164 without +)
    profile_name = models.CharField(max_length=255, blank=True)
    display_name = models.CharField(max_length=255, blank=True)  # owner-editable
    notes = models.TextField(blank=True)  # context the business is permitted to retain
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "wa_id"], name="uniq_contact_wa_id")]

    @property
    def name(self):
        return self.display_name or self.profile_name or f"+{self.wa_id}"

    def __str__(self):
        return self.name


class Conversation(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        RESOLVED = "resolved"

    class AutomationOverride(models.TextChoices):
        INHERIT = "inherit", "Use workspace setting"
        OFF = "off", "Automation off"
        MANUAL = "manual", "Manual (drafts only)"
        APPROVAL = "approval", "Approval required"
        AUTOMATIC = "automatic", "Automatic"

    class ReplyFormat(models.TextChoices):
        INHERIT = "inherit"
        TEXT = "text"
        VOICE = "voice"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="conversations")
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name="conversations")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    automation_override = models.CharField(
        max_length=16, choices=AutomationOverride.choices, default=AutomationOverride.INHERIT
    )
    automation_paused = models.BooleanField(default=False)
    human_takeover = models.BooleanField(default=False)
    takeover_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    takeover_at = models.DateTimeField(null=True, blank=True)
    reply_format = models.CharField(max_length=16, choices=ReplyFormat.choices, default=ReplyFormat.INHERIT)
    needs_attention = models.BooleanField(default=False, db_index=True)
    attention_reason = models.CharField(max_length=255, blank=True)
    unread_count = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_preview = models.CharField(max_length=255, blank=True)
    last_customer_message_at = models.DateTimeField(null=True, blank=True)
    # Incremented on every human action so in-flight AI work can detect it lost the race.
    state_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "contact"], name="uniq_conversation_contact")]
        indexes = [models.Index(fields=["workspace", "-last_message_at"])]

    def within_service_window(self, now=None):
        if not self.last_customer_message_at:
            return False
        return (now or timezone.now()) - self.last_customer_message_at < CUSTOMER_SERVICE_WINDOW

    def bump_version(self):
        Conversation.objects.filter(pk=self.pk).update(state_version=F("state_version") + 1)
        self.refresh_from_db(fields=["state_version"])


class MediaAsset(models.Model):
    class Source(models.TextChoices):
        INBOUND = "inbound"
        VOICE_GENERATED = "voice_generated"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="media_assets")
    file = models.FileField(upload_to="media/%Y/%m/", blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True)
    source = models.CharField(max_length=32, choices=Source.choices)
    provider_media_id = models.CharField(max_length=128, blank=True)  # WhatsApp media id
    download_status = models.CharField(max_length=16, default="ready")  # pending / ready / failed
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Message(models.Model):
    class Direction(models.TextChoices):
        INBOUND = "in"
        OUTBOUND = "out"

    class Sender(models.TextChoices):
        CUSTOMER = "customer"
        HUMAN = "human"  # typed by a team member
        AI_AUTO = "ai_auto"  # sent automatically by the AI
        AI_APPROVED = "ai_approved"  # AI draft approved (maybe edited) by a human
        SYSTEM = "system"

    class Type(models.TextChoices):
        TEXT = "text"
        AUDIO = "audio"
        IMAGE = "image"
        DOCUMENT = "document"
        TEMPLATE = "template"
        OTHER = "other"

    class Status(models.TextChoices):
        RECEIVED = "received"
        QUEUED = "queued"
        SENDING = "sending"
        SENT = "sent"
        DELIVERED = "delivered"
        READ = "read"
        PLAYED = "played"
        FAILED = "failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="messages")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    direction = models.CharField(max_length=4, choices=Direction.choices)
    sender_type = models.CharField(max_length=16, choices=Sender.choices)
    message_type = models.CharField(max_length=16, choices=Type.choices, default=Type.TEXT)
    text = models.TextField(blank=True)  # for audio we keep the transcript/source text
    media = models.ForeignKey(MediaAsset, null=True, blank=True, on_delete=models.SET_NULL)
    provider_message_id = models.CharField(max_length=191, null=True, blank=True)  # wamid
    idempotency_key = models.CharField(max_length=191, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    ai_generation = models.ForeignKey(
        "ai.AIGeneration", null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_messages"
    )
    provider_timestamp = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "provider_message_id"],
                condition=Q(provider_message_id__isnull=False),
                name="uniq_provider_message_id",
            ),
            models.UniqueConstraint(
                fields=["workspace", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uniq_message_idempotency_key",
            ),
        ]
        indexes = [models.Index(fields=["conversation", "created_at"])]

    @property
    def is_ai(self):
        return self.sender_type in (self.Sender.AI_AUTO, self.Sender.AI_APPROVED)


STATUS_ORDER = {
    Message.Status.QUEUED: 0,
    Message.Status.SENDING: 1,
    Message.Status.SENT: 2,
    Message.Status.DELIVERED: 3,
    Message.Status.READ: 4,
    Message.Status.PLAYED: 5,
}


class MessageStatusEvent(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="status_events")
    status = models.CharField(max_length=16)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    provider_timestamp = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["message", "status", "provider_timestamp"], name="uniq_status_event")
        ]


class ConversationSummary(models.Model):
    conversation = models.OneToOneField(Conversation, on_delete=models.CASCADE, related_name="summary")
    summary = models.TextField(blank=True)
    covers_until = models.ForeignKey(Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    provider = models.CharField(max_length=16, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class Draft(models.Model):
    """AI-prepared reply awaiting a human decision (approval queue / manual suggestions)."""

    class Status(models.TextChoices):
        PENDING = "pending"  # awaiting approval
        SUGGESTION = "suggestion"  # manual mode: a suggestion only
        APPROVED = "approved"  # approved, sending in progress
        SENT = "sent"
        REJECTED = "rejected"
        SUPERSEDED = "superseded"
        FAILED = "failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="drafts")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="drafts")
    in_reply_to = models.ForeignKey(Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="drafts")
    text = models.TextField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    reply_format = models.CharField(max_length=8, default="text")  # text / voice
    generation = models.ForeignKey(
        "ai.AIGeneration", null=True, blank=True, on_delete=models.SET_NULL, related_name="drafts"
    )
    intent = models.CharField(max_length=64, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    review_reasons = models.JSONField(default=list, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    decided_at = models.DateTimeField(null=True, blank=True)
    sent_message = models.ForeignKey(Message, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    error_message = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "status"])]
