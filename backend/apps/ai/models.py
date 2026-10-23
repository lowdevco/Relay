from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import Workspace


class Provider(models.TextChoices):
    GEMINI = "gemini", "Google Gemini"
    DEEPSEEK = "deepseek", "DeepSeek"
    GROQ = "groq", "Groq"


class AISettings(models.Model):
    """Per-workspace AI provider selection. This (not .env AI_PROVIDER) decides the active provider."""

    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="ai_settings")
    provider = models.CharField(max_length=16, choices=Provider.choices, default=Provider.GEMINI)
    # Explicit opt-in. When False, a failing provider is never silently replaced.
    fallback_enabled = models.BooleanField(default=False)
    # Which provider to retry with when fallback is enabled. Must differ from `provider`.
    fallback_provider = models.CharField(max_length=16, choices=Provider.choices, blank=True, default="")
    temperature = models.FloatField(default=0.4, validators=[MinValueValidator(0.0), MaxValueValidator(1.5)])
    max_reply_chars = models.PositiveIntegerField(
        default=700, validators=[MinValueValidator(80), MaxValueValidator(4000)]
    )
    history_messages = models.PositiveSmallIntegerField(
        default=12, validators=[MinValueValidator(2), MaxValueValidator(40)]
    )
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)


class PersonaProfile(models.Model):
    class Emoji(models.TextChoices):
        NONE = "none"
        RARE = "rare"
        MODERATE = "moderate"
        FREQUENT = "frequent"

    class Length(models.TextChoices):
        SHORT = "short"
        MEDIUM = "medium"
        LONG = "long"

    workspace = models.OneToOneField(Workspace, on_delete=models.CASCADE, related_name="persona")
    business_name = models.CharField(max_length=120, blank=True)
    assistant_role = models.CharField(
        max_length=255, blank=True, default="customer support assistant for the business"
    )
    formality = models.PositiveSmallIntegerField(default=3, validators=[MinValueValidator(1), MaxValueValidator(5)])
    friendliness = models.PositiveSmallIntegerField(default=4, validators=[MinValueValidator(1), MaxValueValidator(5)])
    conciseness = models.PositiveSmallIntegerField(default=4, validators=[MinValueValidator(1), MaxValueValidator(5)])
    sentence_length = models.CharField(max_length=8, choices=Length.choices, default=Length.SHORT)
    greetings = models.TextField(blank=True)
    closings = models.TextField(blank=True)
    vocabulary = models.TextField(blank=True)
    emoji_usage = models.CharField(max_length=10, choices=Emoji.choices, default=Emoji.RARE)
    preferred_language = models.CharField(max_length=32, blank=True, default="match customer")
    code_switching = models.TextField(blank=True)
    regional_expressions = models.TextField(blank=True)
    phrases_to_avoid = models.TextField(blank=True)
    situation_guidelines = models.TextField(blank=True)
    custom_persona = models.TextField(blank=True)
    # Editable, optionally AI-generated from few-shot examples.
    style_profile = models.JSONField(default=dict, blank=True)
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)


class FewShotExample(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="examples")
    customer_message = models.TextField()
    preferred_reply = models.TextField()
    situation = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=16, blank=True)
    # Owner confirms they are allowed to use this content to steer replies.
    authorized = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class KnowledgeEntry(models.Model):
    class Category(models.TextChoices):
        DESCRIPTION = "description", "Business description"
        PRODUCTS = "products", "Products & services"
        PRICES = "prices", "Prices"
        HOURS = "hours", "Opening hours"
        SERVICE_AREAS = "service_areas", "Service areas"
        FAQ = "faq", "FAQ"
        POLICY = "policy", "Policies"
        REFUNDS = "refunds", "Refunds & returns"
        SHIPPING = "shipping", "Shipping"
        BOOKING = "booking", "Booking procedure"
        CONTACT = "contact", "Contact information"
        CUSTOM = "custom", "Custom instructions"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="knowledge")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.FAQ)
    title = models.CharField(max_length=200)
    content = models.TextField()
    keywords = models.CharField(max_length=500, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "title"]
        indexes = [models.Index(fields=["workspace", "active"])]


class AIGeneration(models.Model):
    """Audit record for every AI call. Stores structured output only, never chain-of-thought."""

    class Operation(models.TextChoices):
        REPLY = "reply"
        CLASSIFY = "classify"
        SUMMARIZE = "summarize"
        EVALUATE = "evaluate"
        STYLE_PROFILE = "style_profile"
        PREVIEW = "preview"
        TEST = "test"

    class Status(models.TextChoices):
        SUCCESS = "success"
        INVALID_OUTPUT = "invalid_output"
        ERROR = "error"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="ai_generations")
    conversation = models.ForeignKey(
        "conversations.Conversation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    message = models.ForeignKey(
        "conversations.Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    operation = models.CharField(max_length=16, choices=Operation.choices)
    provider = models.CharField(max_length=16, choices=Provider.choices)
    requested_provider = models.CharField(max_length=16, choices=Provider.choices)
    model = models.CharField(max_length=128)
    fallback_used = models.BooleanField(default=False)
    prompt_version = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    output = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    attempts = models.PositiveSmallIntegerField(default=1)
    latency_ms = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
