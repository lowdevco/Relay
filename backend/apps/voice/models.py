from django.conf import settings
from django.db import models

from apps.core.models import Workspace


class VoiceSettings(models.Model):
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="voice")
    enabled = models.BooleanField(default=False)
    voice_id = models.CharField(max_length=64, blank=True)
    voice_name = models.CharField(max_length=128, blank=True)
    voice_category = models.CharField(max_length=32, blank=True)  # premade / cloned / professional / generated
    model_id = models.CharField(max_length=64, blank=True)
    language_code = models.CharField(max_length=8, blank=True)
    pronunciation_notes = models.TextField(blank=True)
    stability = models.FloatField(default=0.5)
    similarity_boost = models.FloatField(default=0.75)
    # Required before a cloned voice can be used.
    clone_consent_confirmed = models.BooleanField(default=False)
    clone_consent_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    clone_consent_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_cloned_voice(self):
        return self.voice_category in ("cloned", "professional")


class VoiceGeneration(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        SUCCESS = "success"
        FAILED = "failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="voice_generations")
    conversation = models.ForeignKey(
        "conversations.Conversation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    message = models.ForeignKey(
        "conversations.Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    text = models.TextField()
    voice_id = models.CharField(max_length=64)
    model_id = models.CharField(max_length=64)
    output_format = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    media = models.ForeignKey("conversations.MediaAsset", null=True, blank=True, on_delete=models.SET_NULL)
    characters = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
