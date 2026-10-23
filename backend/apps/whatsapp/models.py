from django.conf import settings
from django.db import models

from apps.core.models import Workspace


class WhatsAppIntegration(models.Model):
    """Maps a WhatsApp Business phone number to a workspace.

    For the local MVP the access token comes from WHATSAPP_ACCESS_TOKEN in .env.
    A token obtained through Embedded Signup is stored server-side in `access_token`
    and is never returned by any API.
    """

    class Status(models.TextChoices):
        NOT_CONFIGURED = "not_configured"
        PENDING = "pending"
        CONNECTED = "connected"
        ERROR = "error"

    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="whatsapp")
    phone_number_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    business_account_id = models.CharField(max_length=64, blank=True)
    display_phone_number = models.CharField(max_length=32, blank=True)
    verified_name = models.CharField(max_length=255, blank=True)
    quality_rating = models.CharField(max_length=32, blank=True)
    access_token = models.TextField(blank=True)  # optional per-workspace token (embedded signup)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NOT_CONFIGURED)
    last_validated_at = models.DateTimeField(null=True, blank=True)
    last_validation_error = models.CharField(max_length=500, blank=True)
    last_webhook_at = models.DateTimeField(null=True, blank=True)
    last_message_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def effective_token(self):
        return self.access_token or settings.WHATSAPP_ACCESS_TOKEN

    @property
    def token_source(self):
        if self.access_token:
            return "embedded_signup"
        if settings.WHATSAPP_ACCESS_TOKEN:
            return "env"
        return ""


class WebhookEvent(models.Model):
    """Raw webhook deliveries, deduplicated by body hash (replay / redelivery protection)."""

    event_hash = models.CharField(max_length=64, unique=True)
    integration = models.ForeignKey(WhatsAppIntegration, null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField()
    signature_valid = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
