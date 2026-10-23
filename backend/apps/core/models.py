from django.conf import settings
from django.db import models


class Workspace(models.Model):
    name = models.CharField(max_length=120)
    timezone = models.CharField(max_length=64, default="UTC")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        AGENT = "agent", "Agent"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.OWNER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "workspace"], name="uniq_membership")]

    @property
    def can_manage(self):
        return self.role in (self.Role.OWNER, self.Role.ADMIN)


class AuditLog(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="audit_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["workspace", "-created_at"])]


class UsageEvent(models.Model):
    """Usage + error records for AI providers, voice generation and WhatsApp."""

    class Kind(models.TextChoices):
        AI_REQUEST = "ai_request"
        AI_FALLBACK = "ai_fallback"
        VOICE_GENERATION = "voice_generation"
        WHATSAPP_SEND = "whatsapp_send"
        WHATSAPP_WEBHOOK = "whatsapp_webhook"
        ERROR = "error"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, null=True, blank=True, related_name="usage_events")
    kind = models.CharField(max_length=32, choices=Kind.choices)
    source = models.CharField(max_length=32, blank=True)  # gemini / deepseek / elevenlabs / whatsapp / pipeline
    operation = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=128, blank=True)
    success = models.BooleanField(default=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    characters = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True)
    message = models.CharField(max_length=500, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "kind", "-created_at"]),
            models.Index(fields=["workspace", "source", "-created_at"]),
        ]


class Job(models.Model):
    """Minimal DB-backed background job queue (see apps.core.jobs)."""

    class Status(models.TextChoices):
        PENDING = "pending"
        RUNNING = "running"
        DONE = "done"
        FAILED = "failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, null=True, blank=True)
    kind = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    dedupe_key = models.CharField(max_length=191, unique=True, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    run_after = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["status", "run_after"])]
