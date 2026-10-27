from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import Workspace


class AutomationMode(models.TextChoices):
    MANUAL = "manual", "Manual (drafts only, never sends)"
    APPROVAL = "approval", "Approval required"
    AUTOMATIC = "automatic", "Automatic"


DEFAULT_REVIEW_TOPICS = ["refund", "chargeback", "lawyer", "legal", "complaint", "cancel my order", "discount"]
DEFAULT_ESCALATION_KEYWORDS = [
    "talk to a human",
    "speak to a human",
    "real person",
    "speak to someone",
    "talk to someone",
    "manager",
    "agent please",
]


class AutomationSettings(models.Model):
    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="automation")
    # Approval is the safe default; automatic must be explicitly chosen by the owner.
    mode = models.CharField(max_length=16, choices=AutomationMode.choices, default=AutomationMode.APPROVAL)
    automation_enabled = models.BooleanField(default=True)
    confidence_threshold = models.FloatField(
        default=0.75, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )
    # "AI hours": outside them the AI stays silent and the owner replies from the WhatsApp Business app.
    operating_hours_enabled = models.BooleanField(default=False)
    # {"mon": [["09:00","18:00"]], ...} in workspace timezone; start > end means the range runs past midnight.
    operating_hours = models.JSONField(default=dict, blank=True)
    # Intents allowed for automatic sending. Empty list = all intents not otherwise blocked.
    allowed_auto_intents = models.JSONField(default=list, blank=True)
    # Keywords in the customer's message that always force approval.
    review_topics = models.JSONField(default=list, blank=True)
    # Keywords meaning "the customer wants a person" -> escalate.
    escalation_keywords = models.JSONField(default=list, blank=True)
    max_auto_replies_per_hour = models.PositiveSmallIntegerField(default=10)
    default_reply_format = models.CharField(max_length=8, default="text")  # text / voice
    voice_requires_approval = models.BooleanField(default=True)
    max_consecutive_failures = models.PositiveSmallIntegerField(default=2)
    # Coexistence: after the owner replies from the phone app, the AI stays out of that chat this long.
    owner_takeover_minutes = models.PositiveSmallIntegerField(default=120, validators=[MaxValueValidator(10080)])
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self._state.adding:
            if not self.review_topics:
                self.review_topics = list(DEFAULT_REVIEW_TOPICS)
            if not self.escalation_keywords:
                self.escalation_keywords = list(DEFAULT_ESCALATION_KEYWORDS)
        super().save(*args, **kwargs)
