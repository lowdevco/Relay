from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsWorkspaceManager, IsWorkspaceMember
from apps.core.services import audit
from apps.core.throttles import AIThrottle

from .models import AIGeneration, AISettings, FewShotExample, KnowledgeEntry, PersonaProfile
from .registry import SUPPORTED, provider_status
from .serializers import (
    AISettingsSerializer,
    FewShotExampleSerializer,
    KnowledgeEntrySerializer,
    PersonaPreviewSerializer,
    PersonaSerializer,
)
from .service import AIService, test_provider_connection


def _ai_payload(workspace):
    obj, _ = AISettings.objects.get_or_create(workspace=workspace)
    data = AISettingsSerializer(obj).data
    data["providers"] = [provider_status(name) for name in SUPPORTED]
    data["active"] = provider_status(obj.provider)
    last = (
        AIGeneration.objects.filter(workspace=workspace)
        .exclude(operation=AIGeneration.Operation.TEST)
        .values("provider", "model", "status", "fallback_used", "created_at")
        .first()
    )
    data["last_generation"] = last
    return data


class AISettingsView(APIView):
    permission_classes = [IsWorkspaceManager]

    def get(self, request):
        return Response(_ai_payload(request.workspace))

    def put(self, request):
        obj, _ = AISettings.objects.get_or_create(workspace=request.workspace)
        before = {"provider": obj.provider, "fallback_enabled": obj.fallback_enabled, "fallback_provider": obj.fallback_provider}
        ser = AISettingsSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        if request.data.get("test_connection"):
            result = test_provider_connection(request.workspace, ser.validated_data.get("provider", obj.provider))
            if not result["ok"]:
                return Response(
                    {"provider": [f"Connection test failed, selection not saved: {result['error']}"], "test": result},
                    status=400,
                )
        ser.save(updated_by=request.user)
        audit(request.workspace, request.user, "ai.settings_updated", obj, before=before,
              after={"provider": obj.provider, "fallback_enabled": obj.fallback_enabled,
                     "fallback_provider": obj.fallback_provider})
        return Response(_ai_payload(request.workspace))

    patch = put


class ProviderTestView(APIView):
    permission_classes = [IsWorkspaceManager]
    throttle_classes = [AIThrottle]

    def post(self, request):
        name = request.data.get("provider")
        if name not in SUPPORTED:
            return Response({"provider": [f"Must be one of: {', '.join(SUPPORTED)}."]}, status=400)
        return Response(test_provider_connection(request.workspace, name))


class PersonaView(APIView):
    permission_classes = [IsWorkspaceManager]

    def get(self, request):
        obj, _ = PersonaProfile.objects.get_or_create(workspace=request.workspace)
        return Response(PersonaSerializer(obj).data)

    def put(self, request):
        obj, _ = PersonaProfile.objects.get_or_create(workspace=request.workspace)
        ser = PersonaSerializer(obj, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        audit(request.workspace, request.user, "persona.updated", obj, version=obj.version)
        return Response(ser.data)

    patch = put


class PersonaPreviewView(APIView):
    """Generate a sample reply with the (possibly unsaved) persona. Nothing is sent."""

    permission_classes = [IsWorkspaceMember]
    throttle_classes = [AIThrottle]

    def post(self, request):
        ser = PersonaPreviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        persona, _ = PersonaProfile.objects.get_or_create(workspace=request.workspace)
        overrides = ser.validated_data.get("persona") or {}
        if overrides:
            pser = PersonaSerializer(persona, data=overrides, partial=True)
            pser.is_valid(raise_exception=True)
            for k, v in pser.validated_data.items():
                setattr(persona, k, v)  # in-memory only, not saved
        result = AIService(request.workspace).preview_reply(ser.validated_data["customer_message"], persona=persona)
        return Response(
            {
                "reply": result.data,
                "provider": result.provider,
                "model": result.generation.model,
                "fallback_used": result.fallback_used,
                "knowledge_ids": result.prompt.context["knowledge_ids"],
                "example_ids": result.prompt.context["example_ids"],
                "prompt_version": result.prompt.version,
            }
        )


class StyleProfileView(APIView):
    """Analyse the owner's few-shot examples into an editable style profile (not saved until PUT /persona)."""

    permission_classes = [IsWorkspaceManager]
    throttle_classes = [AIThrottle]

    def post(self, request):
        examples = list(FewShotExample.objects.filter(workspace=request.workspace, active=True, authorized=True)[:25])
        if len(examples) < 2:
            return Response({"detail": "Add at least 2 authorized examples first."}, status=400)
        result = AIService(request.workspace).generate_style_profile(examples)
        return Response({"style_profile": result.data, "provider": result.provider, "examples_used": len(examples)})


class FewShotExampleViewSet(viewsets.ModelViewSet):
    serializer_class = FewShotExampleSerializer
    permission_classes = [IsWorkspaceManager]

    def get_queryset(self):
        return FewShotExample.objects.filter(workspace=self.request.workspace)

    def perform_create(self, serializer):
        obj = serializer.save(workspace=self.request.workspace)
        audit(self.request.workspace, self.request.user, "example.created", obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request.workspace, self.request.user, "example.updated", obj)

    def perform_destroy(self, instance):
        audit(self.request.workspace, self.request.user, "example.deleted", instance)
        instance.delete()


class KnowledgeEntryViewSet(viewsets.ModelViewSet):
    serializer_class = KnowledgeEntrySerializer
    permission_classes = [IsWorkspaceManager]

    def get_queryset(self):
        qs = KnowledgeEntry.objects.filter(workspace=self.request.workspace)
        cat = self.request.query_params.get("category")
        if cat:
            qs = qs.filter(category=cat)
        return qs

    def perform_create(self, serializer):
        obj = serializer.save(workspace=self.request.workspace)
        audit(self.request.workspace, self.request.user, "knowledge.created", obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request.workspace, self.request.user, "knowledge.updated", obj)

    def perform_destroy(self, instance):
        audit(self.request.workspace, self.request.user, "knowledge.deleted", instance)
        instance.delete()


class KnowledgeCategoriesView(APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        return Response([{"value": v, "label": l} for v, l in KnowledgeEntry.Category.choices])


class GenerationsView(APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        qs = AIGeneration.objects.filter(workspace=request.workspace)
        conv = request.query_params.get("conversation")
        if conv:
            qs = qs.filter(conversation_id=conv)
        return Response(
            list(
                qs.values(
                    "id", "operation", "provider", "requested_provider", "model", "fallback_used", "status",
                    "error_code", "error_message", "latency_ms", "input_tokens", "output_tokens", "prompt_version",
                    "output", "validation_errors", "conversation_id", "created_at",
                )[:50]
            )
        )
