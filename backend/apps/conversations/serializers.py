from rest_framework import serializers

from .models import Contact, Conversation, Draft, Message


class ContactSerializer(serializers.ModelSerializer):
    name = serializers.CharField(read_only=True)

    class Meta:
        model = Contact
        fields = ["id", "wa_id", "profile_name", "display_name", "name", "notes", "created_at"]
        read_only_fields = ["id", "wa_id", "profile_name", "created_at"]


class MessageSerializer(serializers.ModelSerializer):
    media_url = serializers.SerializerMethodField()
    media_mime = serializers.SerializerMethodField()
    media_status = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    provider = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id", "direction", "sender_type", "message_type", "text", "status", "error_code", "error_message",
            "media_url", "media_mime", "media_status", "created_by_name", "provider", "created_at", "sent_at",
        ]

    def get_media_url(self, obj):
        if obj.media_id and obj.media and obj.media.file:
            return f"/api/media/{obj.media_id}/"
        return None

    def get_media_mime(self, obj):
        return obj.media.mime_type if obj.media_id and obj.media else None

    def get_media_status(self, obj):
        return obj.media.download_status if obj.media_id and obj.media else None

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by_id and obj.created_by else None

    def get_provider(self, obj):
        if obj.ai_generation_id and obj.ai_generation:
            return {"provider": obj.ai_generation.provider, "model": obj.ai_generation.model,
                    "fallback_used": obj.ai_generation.fallback_used}
        return None


class DraftSerializer(serializers.ModelSerializer):
    provider = serializers.SerializerMethodField()
    in_reply_to_text = serializers.SerializerMethodField()
    contact_name = serializers.SerializerMethodField()
    rationale = serializers.SerializerMethodField()

    class Meta:
        model = Draft
        fields = [
            "id", "conversation", "contact_name", "in_reply_to", "in_reply_to_text", "text", "status", "reply_format",
            "intent", "confidence", "review_reasons", "provider", "rationale", "error_message", "created_at", "decided_at",
        ]

    def get_provider(self, obj):
        if obj.generation_id and obj.generation:
            return {"provider": obj.generation.provider, "model": obj.generation.model,
                    "fallback_used": obj.generation.fallback_used}
        return None

    def get_in_reply_to_text(self, obj):
        return obj.in_reply_to.text if obj.in_reply_to_id and obj.in_reply_to else ""

    def get_contact_name(self, obj):
        return obj.conversation.contact.name

    def get_rationale(self, obj):
        if obj.generation_id and obj.generation:
            return (obj.generation.output or {}).get("rationale", "")
        return ""


class ConversationListSerializer(serializers.ModelSerializer):
    contact = ContactSerializer(read_only=True)
    pending_drafts = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Conversation
        fields = [
            "id", "contact", "status", "automation_override", "automation_paused", "human_takeover", "reply_format",
            "needs_attention", "attention_reason", "unread_count", "last_message_at", "last_message_preview",
            "last_customer_message_at", "pending_drafts",
        ]


class ConversationDetailSerializer(ConversationListSerializer):
    within_service_window = serializers.SerializerMethodField()
    effective_mode = serializers.SerializerMethodField()
    takeover_by_name = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta(ConversationListSerializer.Meta):
        fields = ConversationListSerializer.Meta.fields + [
            "within_service_window", "effective_mode", "takeover_by_name", "takeover_at", "summary", "state_version",
        ]

    def get_within_service_window(self, obj):
        return obj.within_service_window()

    def get_effective_mode(self, obj):
        from apps.automation.models import AutomationSettings
        from apps.automation.rules import effective_mode

        auto, _ = AutomationSettings.objects.get_or_create(workspace=obj.workspace)
        return effective_mode(obj, auto)

    def get_takeover_by_name(self, obj):
        return obj.takeover_by.username if obj.takeover_by_id else None

    def get_summary(self, obj):
        s = getattr(obj, "summary", None)
        try:
            return s.summary if s else ""
        except Exception:
            return ""


class ConversationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["automation_override", "automation_paused", "reply_format", "status", "needs_attention"]


class SendMessageSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4096)


class ApproveDraftSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=4096, required=False)
    reply_format = serializers.ChoiceField(choices=["text", "voice"], required=False)


class TemplateSerializer(serializers.Serializer):
    name = serializers.RegexField(r"^[a-z0-9_]{1,512}$")
    language = serializers.RegexField(r"^[a-zA-Z_]{2,10}$", default="en_US")
