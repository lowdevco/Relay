from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.middleware.csrf import get_token
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from apps.ai.registry import SUPPORTED, provider_status
from apps.voice.elevenlabs import is_configured as voice_configured

from .models import AuditLog, Membership, UsageEvent, Workspace
from .permissions import IsWorkspaceMember
from .services import audit, ensure_workspace_defaults

User = get_user_model()


class AuthThrottle(SimpleRateThrottle):
    scope = "auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


def _me_payload(request):
    user = request.user
    memberships = Membership.objects.select_related("workspace").filter(user=user).order_by("created_at")
    return {
        "user": {"id": user.id, "username": user.username, "email": user.email},
        "workspaces": [
            {"id": m.workspace.id, "name": m.workspace.name, "role": m.role, "timezone": m.workspace.timezone}
            for m in memberships
        ],
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def csrf(request):
    return Response({"csrfToken": get_token(request)})


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def login_view(request):
    ser = LoginSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    user = authenticate(request, **ser.validated_data)
    if user is None:
        return Response({"detail": "Invalid username or password."}, status=status.HTTP_400_BAD_REQUEST)
    login(request, user)
    return Response(_me_payload(request))


class RegisterSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[\w.@+-]{3,150}$")
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(min_length=8, max_length=128, trim_whitespace=False)
    business_name = serializers.CharField(max_length=120)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is taken.")
        return value

    def validate(self, attrs):
        try:
            validate_password(attrs["password"], User(username=attrs["username"]))
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AuthThrottle])
def register_view(request):
    if not settings.ALLOW_REGISTRATION:
        return Response({"detail": "Registration is disabled."}, status=status.HTTP_403_FORBIDDEN)
    ser = RegisterSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    data = ser.validated_data
    with transaction.atomic():
        user = User.objects.create_user(data["username"], data.get("email", ""), data["password"])
        ws = Workspace.objects.create(name=data["business_name"], timezone=settings.TIME_ZONE)
        Membership.objects.create(user=user, workspace=ws, role=Membership.Role.OWNER)
        ensure_workspace_defaults(ws)
        from apps.ai.models import PersonaProfile

        PersonaProfile.objects.filter(workspace=ws).update(business_name=data["business_name"])
    login(request, user)
    audit(ws, user, "workspace.created", ws)
    return Response(_me_payload(request), status=status.HTTP_201_CREATED)


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response({"ok": True})


@api_view(["GET"])
def me(request):
    return Response(_me_payload(request))


class WorkspaceView(APIView):
    permission_classes = [IsWorkspaceMember]

    def patch(self, request):
        if not request.membership.can_manage:
            return Response({"detail": "Only owners or admins can change the workspace."}, status=403)
        ws = request.workspace
        name = request.data.get("name")
        tz = request.data.get("timezone")
        if name:
            ws.name = str(name)[:120]
        if tz:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(tz)
            except (ZoneInfoNotFoundError, ValueError):
                return Response({"timezone": ["Unknown timezone."]}, status=400)
            ws.timezone = tz
        ws.save()
        audit(ws, request.user, "workspace.updated", ws)
        return Response({"id": ws.id, "name": ws.name, "timezone": ws.timezone})


class DashboardView(APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        from apps.automation.models import AutomationSettings
        from apps.ai.models import AISettings
        from apps.conversations.models import Conversation, Draft, Message
        from apps.voice.models import VoiceGeneration

        ws = request.workspace
        since = timezone.now() - timedelta(days=30)
        msgs = Message.objects.filter(workspace=ws)
        convs = Conversation.objects.filter(workspace=ws)
        ai = AISettings.objects.filter(workspace=ws).first()
        auto = AutomationSettings.objects.filter(workspace=ws).first()
        usage = (
            UsageEvent.objects.filter(workspace=ws, kind=UsageEvent.Kind.AI_REQUEST, created_at__gte=since)
            .values("source")
            .annotate(
                requests=Count("id"),
                failures=Count("id", filter=Q(success=False)),
                input_tokens=Sum("input_tokens"),
                output_tokens=Sum("output_tokens"),
            )
        )
        voice = VoiceGeneration.objects.filter(workspace=ws, created_at__gte=since).aggregate(
            total=Count("id"),
            failed=Count("id", filter=Q(status="failed")),
            characters=Sum("characters", filter=Q(status="success")),
        )
        days = []
        for i in range(13, -1, -1):
            day = (timezone.now() - timedelta(days=i)).date()
            days.append(
                {
                    "date": day.isoformat(),
                    "received": msgs.filter(direction="in", created_at__date=day).count(),
                    "ai_sent": msgs.filter(sender_type__in=["ai_auto", "ai_approved"], created_at__date=day).count(),
                }
            )
        return Response(
            {
                "totals": {
                    "conversations": convs.count(),
                    "open_conversations": convs.filter(status="open").count(),
                    "messages_received": msgs.filter(direction="in").count(),
                    "ai_replies_sent": msgs.filter(sender_type__in=["ai_auto", "ai_approved"]).exclude(status="failed").count(),
                    "ai_auto_sent": msgs.filter(sender_type="ai_auto").exclude(status="failed").count(),
                    "human_replies": msgs.filter(sender_type="human").count(),
                    "drafts_pending": Draft.objects.filter(workspace=ws, status="pending").count(),
                    "needs_attention": convs.filter(needs_attention=True, status="open").count(),
                    "failed_messages": msgs.filter(status="failed").count(),
                    "human_takeover": convs.filter(human_takeover=True).count(),
                },
                "automation": {
                    "mode": auto.mode if auto else None,
                    "enabled": auto.automation_enabled if auto else False,
                },
                "provider": {
                    "selected": ai.provider if ai else None,
                    "fallback_enabled": ai.fallback_enabled if ai else False,
                    "status": provider_status(ai.provider) if ai else None,
                },
                "ai_usage_30d": list(usage),
                "voice_usage_30d": voice,
                "daily": days,
            }
        )


class ActivityView(APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        ws = request.workspace
        logs = AuditLog.objects.filter(workspace=ws).select_related("user")[:40]
        events = UsageEvent.objects.filter(workspace=ws).exclude(kind=UsageEvent.Kind.WHATSAPP_WEBHOOK)[:60]
        source = request.query_params.get("source")
        if source:
            events = UsageEvent.objects.filter(workspace=ws, source=source)[:60]
        return Response(
            {
                "audit": [
                    {
                        "id": a.id,
                        "action": a.action,
                        "user": a.user.username if a.user else "system (AI)",
                        "target_type": a.target_type,
                        "target_id": a.target_id,
                        "details": a.details,
                        "created_at": a.created_at,
                    }
                    for a in logs
                ],
                "events": [
                    {
                        "id": e.id,
                        "kind": e.kind,
                        "source": e.source,
                        "operation": e.operation,
                        "model": e.model,
                        "success": e.success,
                        "error_code": e.error_code,
                        "message": e.message,
                        "latency_ms": e.latency_ms,
                        "input_tokens": e.input_tokens,
                        "output_tokens": e.output_tokens,
                        "characters": e.characters,
                        "created_at": e.created_at,
                    }
                    for e in events
                ],
            }
        )


class IntegrationsStatusView(APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        from apps.whatsapp.views import integration_payload

        return Response(
            {
                "whatsapp": integration_payload(request.workspace),
                "providers": [provider_status(name) for name in SUPPORTED],
                "elevenlabs": {
                    "configured": voice_configured(),
                    "missing": [] if voice_configured() else ["ELEVENLABS_API_KEY"],
                    "model": settings.ELEVENLABS_DEFAULT_MODEL,
                    "output_format": settings.ELEVENLABS_OUTPUT_FORMAT,
                },
            }
        )
