from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsWorkspaceManager
from apps.core.services import audit
from apps.core.throttles import AIThrottle

from .elevenlabs import ElevenLabsClient, VoiceError, is_configured
from .models import VoiceGeneration, VoiceSettings
from .service import synthesize_for_whatsapp, voice_readiness


class VoiceSettingsSerializer(serializers.ModelSerializer):
    is_cloned_voice = serializers.BooleanField(read_only=True)

    class Meta:
        model = VoiceSettings
        fields = [
            "enabled", "voice_id", "voice_name", "voice_category", "model_id", "language_code", "pronunciation_notes",
            "stability", "similarity_boost", "clone_consent_confirmed", "clone_consent_at", "is_cloned_voice", "updated_at",
        ]
        read_only_fields = ["clone_consent_at", "updated_at"]

    def validate_stability(self, v):
        if not 0 <= v <= 1:
            raise serializers.ValidationError("Must be between 0 and 1.")
        return v

    validate_similarity_boost = validate_stability

    def validate(self, attrs):
        merged = {**{f: getattr(self.instance, f) for f in ("enabled", "voice_id", "voice_category", "clone_consent_confirmed")}, **attrs}
        if merged["enabled"]:
            if not is_configured():
                raise serializers.ValidationError({"enabled": "ELEVENLABS_API_KEY is not configured on the server."})
            if not merged["voice_id"]:
                raise serializers.ValidationError({"voice_id": "Select a voice before enabling voice replies."})
            if merged["voice_category"] in ("cloned", "professional") and not merged["clone_consent_confirmed"]:
                raise serializers.ValidationError(
                    {"clone_consent_confirmed": "Confirm you have the voice owner's consent to use this cloned voice."}
                )
        return attrs


def _payload(workspace):
    vs, _ = VoiceSettings.objects.get_or_create(workspace=workspace, defaults={"model_id": settings.ELEVENLABS_DEFAULT_MODEL})
    since = timezone.now() - timezone.timedelta(days=30)
    usage = VoiceGeneration.objects.filter(workspace=workspace, created_at__gte=since).aggregate(
        total=Count("id"), failed=Count("id", filter=Q(status="failed")), characters=Sum("characters", filter=Q(status="success"))
    )
    recent = list(
        VoiceGeneration.objects.filter(workspace=workspace).values("id", "status", "characters", "error", "media_id", "created_at")[:10]
    )
    return {
        "settings": VoiceSettingsSerializer(vs).data,
        "configured": is_configured(),
        "ready_problems": voice_readiness(vs),
        "output_format": settings.ELEVENLABS_OUTPUT_FORMAT,
        "usage_30d": usage,
        "recent": recent,
    }


class VoiceSettingsView(APIView):
    permission_classes = [IsWorkspaceManager]

    def get(self, request):
        return Response(_payload(request.workspace))

    def put(self, request):
        vs, _ = VoiceSettings.objects.get_or_create(workspace=request.workspace)
        ser = VoiceSettingsSerializer(vs, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        consent_now = ser.validated_data.get("clone_consent_confirmed")
        obj = ser.save()
        if consent_now and not vs.clone_consent_at:
            obj.clone_consent_by = request.user
            obj.clone_consent_at = timezone.now()
            obj.save(update_fields=["clone_consent_by", "clone_consent_at"])
        audit(request.workspace, request.user, "voice.updated", obj, enabled=obj.enabled, voice_id=obj.voice_id)
        return Response(_payload(request.workspace))

    patch = put


class VoiceListView(APIView):
    permission_classes = [IsWorkspaceManager]

    def get(self, request):
        try:
            client = ElevenLabsClient()
            return Response({"voices": client.list_voices(), "subscription": client.subscription()})
        except VoiceError as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=400 if exc.code == "not_configured" else 502)


class VoiceTestView(APIView):
    permission_classes = [IsWorkspaceManager]
    throttle_classes = [AIThrottle]

    def post(self, request):
        text = str(request.data.get("text") or "Hi! This is a test of our voice replies.")[:300]
        try:
            media, is_voice, gen = synthesize_for_whatsapp(request.workspace, text)
        except VoiceError as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=400)
        return Response(
            {"media_url": f"/api/media/{media.pk}/", "mime_type": media.mime_type, "voice_note_compatible": is_voice,
             "size": media.size, "generation_id": gen.pk}
        )
