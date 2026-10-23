import re

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsWorkspaceManager
from apps.core.services import audit

from .models import AutomationMode, AutomationSettings
from .rules import DAYS

TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _keyword_list(value, field):
    if not isinstance(value, list) or len(value) > 50:
        raise serializers.ValidationError({field: "Must be a list of up to 50 strings."})
    out = []
    for v in value:
        if not isinstance(v, str) or not v.strip() or len(v) > 80:
            raise serializers.ValidationError({field: "Each entry must be a non-empty string (max 80 chars)."})
        out.append(v.strip())
    return out


class AutomationSettingsSerializer(serializers.ModelSerializer):
    mode = serializers.ChoiceField(choices=AutomationMode.choices)
    default_reply_format = serializers.ChoiceField(choices=["text", "voice"])
    # Automatic mode must be explicitly confirmed by the owner.
    confirm_automatic = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = AutomationSettings
        exclude = ["id", "workspace"]
        read_only_fields = ["updated_at"]

    def validate_operating_hours(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object keyed by day (mon..sun).")
        for day, ranges in value.items():
            if day not in DAYS or not isinstance(ranges, list):
                raise serializers.ValidationError(f"Invalid day '{day}'.")
            for r in ranges:
                if not (isinstance(r, list) and len(r) == 2 and all(isinstance(t, str) and TIME.match(t) for t in r) and r[0] < r[1]):
                    raise serializers.ValidationError(f"Invalid range for {day}: use [\"09:00\", \"18:00\"].")
        return value

    def validate_review_topics(self, value):
        return _keyword_list(value, "review_topics")

    def validate_escalation_keywords(self, value):
        return _keyword_list(value, "escalation_keywords")

    def validate_allowed_auto_intents(self, value):
        return [re.sub(r"[^a-z0-9_]", "_", v.lower()) for v in _keyword_list(value, "allowed_auto_intents")]

    def validate(self, attrs):
        confirm = attrs.pop("confirm_automatic", False)
        if attrs.get("mode") == AutomationMode.AUTOMATIC and getattr(self.instance, "mode", None) != AutomationMode.AUTOMATIC:
            if not confirm:
                raise serializers.ValidationError(
                    {"mode": "Automatic mode sends replies without review. Confirm explicitly (confirm_automatic=true)."}
                )
        return attrs


class AutomationSettingsView(APIView):
    permission_classes = [IsWorkspaceManager]

    def get(self, request):
        obj, _ = AutomationSettings.objects.get_or_create(workspace=request.workspace)
        return Response(AutomationSettingsSerializer(obj).data)

    def put(self, request):
        obj, _ = AutomationSettings.objects.get_or_create(workspace=request.workspace)
        before = obj.mode
        ser = AutomationSettingsSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        audit(request.workspace, request.user, "automation.updated", obj, mode_before=before, mode_after=obj.mode)
        return Response(AutomationSettingsSerializer(obj).data)

    patch = put
