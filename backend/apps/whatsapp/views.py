import json
import logging
import time
import uuid

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import jobs
from apps.core.models import UsageEvent
from apps.core.permissions import IsWorkspaceManager, IsWorkspaceMember
from apps.core.services import audit

from . import webhook
from .client import WhatsAppClient, WhatsAppError, exchange_embedded_signup_code
from .models import WhatsAppIntegration

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public webhook (Meta -> Django)
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge", "")
        if not settings.WHATSAPP_VERIFY_TOKEN:
            logger.error("Webhook verification attempted but WHATSAPP_VERIFY_TOKEN is not set.")
            return HttpResponseForbidden("verify token not configured")
        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponseForbidden("verification failed")

    raw = request.body
    signature = request.headers.get("X-Hub-Signature-256", "")
    signature_valid = webhook.verify_signature(raw, signature)
    if not signature_valid:
        dev_unsigned = settings.DEBUG and settings.WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS and not settings.META_APP_SECRET
        if not dev_unsigned:
            logger.warning("Rejected webhook with invalid/missing signature.")
            return HttpResponseForbidden("invalid signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest("invalid json")
    if not isinstance(payload, dict):
        return HttpResponseBadRequest("invalid payload")

    created = webhook.process_payload(payload, raw, signature_valid)
    jobs.dispatch(created)  # after the ingestion transactions committed; AI runs in the background
    return HttpResponse("ok")


# ---------------------------------------------------------------------------
# Dashboard API
# ---------------------------------------------------------------------------
def integration_payload(workspace):
    integration = WhatsAppIntegration.objects.filter(workspace=workspace).first()
    errors = list(
        UsageEvent.objects.filter(workspace=workspace, source="whatsapp", success=False).values(
            "error_code", "message", "created_at"
        )[:10]
    )
    env = {
        "access_token_configured": bool(settings.WHATSAPP_ACCESS_TOKEN),
        "verify_token_configured": bool(settings.WHATSAPP_VERIFY_TOKEN),
        "app_secret_configured": bool(settings.META_APP_SECRET),
        "env_phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID,
        "env_business_account_id": settings.WHATSAPP_BUSINESS_ACCOUNT_ID,
        "graph_version": settings.WHATSAPP_GRAPH_VERSION,
        "unsigned_webhooks_allowed": bool(settings.DEBUG and settings.WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS and not settings.META_APP_SECRET),
        "embedded_signup_available": bool(settings.META_APP_ID and settings.META_APP_SECRET and settings.META_EMBEDDED_SIGNUP_CONFIG_ID),
        "meta_app_id": settings.META_APP_ID,
        "embedded_signup_config_id": settings.META_EMBEDDED_SIGNUP_CONFIG_ID,
        "webhook_url": f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/api/webhooks/whatsapp/",
        "debug": settings.DEBUG,
    }
    data = {"env": env, "recent_errors": errors}
    if integration is None:
        data.update({"status": WhatsAppIntegration.Status.NOT_CONFIGURED, "integration": None})
        return data
    has_token = bool(integration.effective_token)
    data["status"] = integration.status if has_token else WhatsAppIntegration.Status.NOT_CONFIGURED
    data["integration"] = {
        "phone_number_id": integration.phone_number_id,
        "business_account_id": integration.business_account_id,
        "display_phone_number": integration.display_phone_number,
        "verified_name": integration.verified_name,
        "quality_rating": integration.quality_rating,
        "token_source": integration.token_source,  # never the token itself
        "status": integration.status,
        "last_validated_at": integration.last_validated_at,
        "last_validation_error": integration.last_validation_error,
        "last_webhook_at": integration.last_webhook_at,
        "last_message_event_at": integration.last_message_event_at,
    }
    return data


class IntegrationSerializer(serializers.Serializer):
    phone_number_id = serializers.RegexField(r"^\d{5,30}$")
    business_account_id = serializers.RegexField(r"^\d{5,30}$", required=False, allow_blank=True)


def validate_integration(integration):
    try:
        info = WhatsAppClient.for_integration(integration).get_phone_number()
    except WhatsAppError as exc:
        integration.status = WhatsAppIntegration.Status.ERROR
        integration.last_validation_error = exc.message[:500]
        integration.last_validated_at = timezone.now()
        integration.save()
        return False, exc.message
    integration.display_phone_number = info.get("display_phone_number", "")[:32]
    integration.verified_name = info.get("verified_name", "")[:255]
    integration.quality_rating = str(info.get("quality_rating", ""))[:32]
    integration.status = WhatsAppIntegration.Status.CONNECTED
    integration.last_validation_error = ""
    integration.last_validated_at = timezone.now()
    integration.save()
    return True, ""


class WhatsAppIntegrationView(APIView):
    permission_classes = [IsWorkspaceManager]

    def get(self, request):
        return Response(integration_payload(request.workspace))

    def put(self, request):
        ser = IntegrationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pid = ser.validated_data["phone_number_id"]
        if WhatsAppIntegration.objects.filter(phone_number_id=pid).exclude(workspace=request.workspace).exists():
            return Response({"phone_number_id": ["This phone number is connected to another workspace."]}, status=400)
        integration, _ = WhatsAppIntegration.objects.get_or_create(workspace=request.workspace)
        integration.phone_number_id = pid
        integration.business_account_id = ser.validated_data.get("business_account_id", "")
        integration.status = WhatsAppIntegration.Status.PENDING
        integration.save()
        audit(request.workspace, request.user, "whatsapp.configured", integration, phone_number_id=pid)
        if integration.effective_token:
            validate_integration(integration)
        return Response(integration_payload(request.workspace))


class WhatsAppValidateView(APIView):
    permission_classes = [IsWorkspaceManager]

    def post(self, request):
        integration = WhatsAppIntegration.objects.filter(workspace=request.workspace).first()
        if integration is None or not integration.phone_number_id:
            return Response({"detail": "Save a phone number id first."}, status=400)
        ok, error = validate_integration(integration)
        return Response({"ok": ok, "error": error, **integration_payload(request.workspace)}, status=200)


class EmbeddedSignupView(APIView):
    """Completes Meta Embedded Signup: the browser sends the short-lived code; the token stays server-side."""

    permission_classes = [IsWorkspaceManager]

    def post(self, request):
        code = str(request.data.get("code") or "")
        pid = str(request.data.get("phone_number_id") or "")
        waba = str(request.data.get("waba_id") or "")
        if not code or not pid.isdigit():
            return Response({"detail": "code and phone_number_id are required."}, status=400)
        try:
            token = exchange_embedded_signup_code(code)
        except WhatsAppError as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=400)
        if WhatsAppIntegration.objects.filter(phone_number_id=pid).exclude(workspace=request.workspace).exists():
            return Response({"detail": "This phone number is connected to another workspace."}, status=400)
        integration, _ = WhatsAppIntegration.objects.get_or_create(workspace=request.workspace)
        integration.phone_number_id = pid
        integration.business_account_id = waba if waba.isdigit() else ""
        integration.access_token = token
        integration.save()
        audit(request.workspace, request.user, "whatsapp.embedded_signup", integration, phone_number_id=pid)
        validate_integration(integration)
        return Response(integration_payload(request.workspace))


class DevSimulateInboundView(APIView):
    """DEVELOPMENT SUBSTITUTE (DEBUG only): injects a webhook-shaped inbound message
    through the real ingestion + AI pipeline. It does NOT come from Meta. Outgoing
    replies still use the real Cloud API and fail visibly if credentials are missing."""

    permission_classes = [IsWorkspaceMember]

    def post(self, request):
        if not settings.DEBUG:
            return Response({"detail": "Only available when DEBUG=True."}, status=404)
        integration = WhatsAppIntegration.objects.filter(workspace=request.workspace).first()
        if integration is None or not integration.phone_number_id:
            return Response({"detail": "Configure a WhatsApp phone number id first (Integrations page)."}, status=400)
        text = str(request.data.get("text") or "").strip()[:2000]
        wa_id = str(request.data.get("wa_id") or "15550001111")
        name = str(request.data.get("name") or "Test Customer")[:80]
        if not text or not wa_id.isdigit():
            return Response({"detail": "text and a numeric wa_id are required."}, status=400)
        # kind="owner_echo" pretends the owner replied from the WhatsApp Business app (coexistence test mode).
        owner_echo = request.data.get("kind") == "owner_echo"
        msg = {"id": f"wamid.DEV-{uuid.uuid4().hex}", "timestamp": str(int(time.time())), "type": "text", "text": {"body": text}}
        value = {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": integration.display_phone_number, "phone_number_id": integration.phone_number_id},
        }
        if owner_echo:
            value["message_echoes"] = [{**msg, "from": integration.display_phone_number or "0", "to": wa_id}]
        else:
            value["contacts"] = [{"profile": {"name": name}, "wa_id": wa_id}]
            value["messages"] = [{**msg, "from": wa_id}]
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": integration.business_account_id or "0",
                "changes": [{"field": "smb_message_echoes" if owner_echo else "messages", "value": value}],
            }],
        }
        raw = json.dumps(payload).encode()
        created = webhook.process_payload(payload, raw, signature_valid=False, simulated=True)
        jobs.dispatch(created)
        return Response({"ok": True, "simulated": True, "jobs": len([j for j in created if j])})
