from rest_framework import serializers

from .models import AISettings, FewShotExample, KnowledgeEntry, PersonaProfile, Provider
from .registry import provider_status


class AISettingsSerializer(serializers.ModelSerializer):
    provider = serializers.ChoiceField(choices=Provider.choices)
    fallback_provider = serializers.ChoiceField(choices=Provider.choices, required=False, allow_blank=True)

    class Meta:
        model = AISettings
        fields = ["provider", "fallback_enabled", "fallback_provider", "temperature", "max_reply_chars", "history_messages", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate(self, attrs):
        provider = attrs.get("provider", getattr(self.instance, "provider", None))
        status = provider_status(provider)
        if not status["configured"]:
            raise serializers.ValidationError(
                {"provider": f"{status['label']} is not configured on the server (missing: {', '.join(status['missing'])}). "
                             "Add it to backend/.env and restart the backend."}
            )
        fallback_enabled = attrs.get("fallback_enabled", getattr(self.instance, "fallback_enabled", False))
        fallback = attrs.get("fallback_provider", getattr(self.instance, "fallback_provider", ""))
        if fallback_enabled:
            if not fallback:
                raise serializers.ValidationError({"fallback_provider": "Choose which provider to fall back to."})
            if fallback == provider:
                raise serializers.ValidationError(
                    {"fallback_provider": "The fallback provider must be different from the selected provider."}
                )
            fb_status = provider_status(fallback)
            if not fb_status["configured"]:
                raise serializers.ValidationError(
                    {"fallback_provider": f"Fallback needs {fb_status['label']} to be configured too "
                                          f"(missing: {', '.join(fb_status['missing'])})."}
                )
        return attrs


class PersonaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonaProfile
        exclude = ["id", "workspace"]
        read_only_fields = ["version", "updated_at"]

    def validate_style_profile(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        if len(str(value)) > 5000:
            raise serializers.ValidationError("Style profile is too large.")
        return value

    def update(self, instance, validated_data):
        instance.version += 1
        return super().update(instance, validated_data)


class PersonaPreviewSerializer(serializers.Serializer):
    customer_message = serializers.CharField(max_length=1000)
    persona = serializers.DictField(required=False)


class FewShotExampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FewShotExample
        fields = ["id", "customer_message", "preferred_reply", "situation", "language", "authorized", "active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "customer_message": {"max_length": 1000},
            "preferred_reply": {"max_length": 1500},
        }


class KnowledgeEntrySerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = KnowledgeEntry
        fields = ["id", "category", "category_label", "title", "content", "keywords", "active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {"content": {"max_length": 5000}}
