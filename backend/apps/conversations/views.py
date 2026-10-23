from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsWorkspaceMember
from apps.core.services import audit
from apps.core.throttles import AIThrottle, SendThrottle
from apps.whatsapp import sender

from . import services
from .models import Contact, Conversation, Draft, MediaAsset, Message
from .serializers import (
    ApproveDraftSerializer,
    ContactSerializer,
    ConversationDetailSerializer,
    ConversationListSerializer,
    ConversationUpdateSerializer,
    DraftSerializer,
    MessageSerializer,
    SendMessageSerializer,
    TemplateSerializer,
)


class ConversationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsWorkspaceMember]

    def get_queryset(self):
        qs = (
            Conversation.objects.filter(workspace=self.request.workspace)
            .select_related("contact", "takeover_by")
            .annotate(pending_drafts=Count("drafts", filter=Q(drafts__status="pending")))
            .order_by("-last_message_at", "-id")
        )
        p = self.request.query_params
        if p.get("search"):
            s = p["search"].strip()[:100]
            qs = qs.filter(
                Q(contact__profile_name__icontains=s)
                | Q(contact__display_name__icontains=s)
                | Q(contact__wa_id__icontains=s)
                | Q(messages__text__icontains=s)
            ).distinct()
        f = p.get("filter")
        if f == "attention":
            qs = qs.filter(needs_attention=True)
        elif f == "unread":
            qs = qs.filter(unread_count__gt=0)
        elif f == "drafts":
            qs = qs.filter(drafts__status="pending").distinct()
        elif f == "takeover":
            qs = qs.filter(human_takeover=True)
        elif f == "resolved":
            qs = qs.filter(status="resolved")
        elif f == "open":
            qs = qs.filter(status="open")
        return qs

    def get_serializer_class(self):
        return ConversationDetailSerializer if self.action == "retrieve" else ConversationListSerializer

    def partial_update(self, request, pk=None):
        conv = self.get_object()
        ser = ConversationUpdateSerializer(conv, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        if ser.validated_data.get("needs_attention") is False:
            Conversation.objects.filter(pk=conv.pk).update(attention_reason="")
        conv.bump_version()
        audit(request.workspace, request.user, "conversation.updated", conv, **{k: str(v) for k, v in ser.validated_data.items()})
        return Response(ConversationDetailSerializer(self.get_object()).data)

    @action(detail=True, methods=["get", "post"], throttle_classes=[SendThrottle], url_path="messages")
    def messages(self, request, pk=None):
        conv = self.get_object()
        if request.method == "GET":
            qs = (
                Message.objects.filter(conversation=conv, workspace=request.workspace)
                .select_related("media", "created_by", "ai_generation")
                .order_by("-created_at", "-id")[:200]
            )
            return Response(MessageSerializer(list(qs)[::-1], many=True).data)
        ser = SendMessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        msg = services.human_send(conv, ser.validated_data["text"], request.user)
        return Response(MessageSerializer(msg).data, status=201)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        conv = self.get_object()
        Conversation.objects.filter(pk=conv.pk).update(unread_count=0)
        return Response({"ok": True})

    @action(detail=True, methods=["post"])
    def takeover(self, request, pk=None):
        conv = self.get_object()
        services.take_over(conv, request.user)
        return Response(ConversationDetailSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        conv = self.get_object()
        services.resume_ai(conv, request.user)
        return Response(ConversationDetailSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        conv = self.get_object()
        Conversation.objects.filter(pk=conv.pk).update(status="resolved", needs_attention=False, attention_reason="")
        conv.bump_version()
        audit(request.workspace, request.user, "conversation.resolved", conv)
        return Response(ConversationDetailSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        conv = self.get_object()
        Conversation.objects.filter(pk=conv.pk).update(status="open")
        audit(request.workspace, request.user, "conversation.reopened", conv)
        return Response(ConversationDetailSerializer(self.get_object()).data)

    @action(detail=True, methods=["post"], throttle_classes=[AIThrottle])
    def regenerate(self, request, pk=None):
        conv = self.get_object()
        fmt = request.data.get("reply_format", "text")
        if fmt not in ("text", "voice"):
            fmt = "text"
        draft = services.regenerate_draft(conv, request.user, fmt)
        return Response(DraftSerializer(draft).data, status=201)

    @action(detail=True, methods=["get"])
    def drafts(self, request, pk=None):
        conv = self.get_object()
        qs = Draft.objects.filter(conversation=conv, workspace=request.workspace).select_related(
            "generation", "in_reply_to", "conversation__contact"
        )[:20]
        return Response(DraftSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="send-template", throttle_classes=[SendThrottle])
    def send_template(self, request, pk=None):
        conv = self.get_object()
        ser = TemplateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        conv.bump_version()
        msg = sender.send_template(conv, ser.validated_data["name"], ser.validated_data["language"], user=request.user)
        audit(request.workspace, request.user, "message.template_sent", msg, template=ser.validated_data["name"])
        return Response(MessageSerializer(msg).data, status=201)

    @action(detail=True, methods=["patch"], url_path="contact")
    def contact(self, request, pk=None):
        conv = self.get_object()
        ser = ContactSerializer(conv.contact, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)


class DraftViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsWorkspaceMember]
    serializer_class = DraftSerializer

    def get_queryset(self):
        qs = Draft.objects.filter(workspace=self.request.workspace).select_related(
            "generation", "in_reply_to", "conversation__contact"
        )
        if self.action != "list":
            return qs
        status = self.request.query_params.get("status", "pending")
        if status != "all":
            qs = qs.filter(status=status)
        return qs[:100]

    @action(detail=True, methods=["post"], throttle_classes=[SendThrottle])
    def approve(self, request, pk=None):
        draft = self.get_object()
        ser = ApproveDraftSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        msg = services.approve_draft(
            draft, request.user, text=ser.validated_data.get("text"), reply_format=ser.validated_data.get("reply_format")
        )
        return Response({"draft": DraftSerializer(Draft.objects.get(pk=draft.pk)).data, "message": MessageSerializer(msg).data})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        draft = self.get_object()
        services.reject_draft(draft, request.user)
        return Response(DraftSerializer(Draft.objects.get(pk=draft.pk)).data)


class MessageRetryView(APIView):
    permission_classes = [IsWorkspaceMember]

    def post(self, request, pk):
        message = get_object_or_404(Message, pk=pk, workspace=request.workspace)
        msg = sender.retry_message(message)
        audit(request.workspace, request.user, "message.retried", msg)
        return Response(MessageSerializer(msg).data)


class MediaView(APIView):
    """Authenticated, workspace-scoped media download (no public media URLs)."""

    permission_classes = [IsWorkspaceMember]

    def get(self, request, pk):
        media = get_object_or_404(MediaAsset, pk=pk, workspace=request.workspace)
        if not media.file:
            raise Http404("Media not available.")
        resp = FileResponse(media.file.open("rb"), content_type=media.mime_type or "application/octet-stream")
        resp["Cache-Control"] = "private, max-age=3600"
        resp["X-Content-Type-Options"] = "nosniff"
        return resp


class ContactViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsWorkspaceMember]
    serializer_class = ContactSerializer

    def get_queryset(self):
        return Contact.objects.filter(workspace=self.request.workspace).order_by("-created_at")
