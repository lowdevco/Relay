from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.ai import views as ai_views
from apps.automation import views as automation_views
from apps.conversations import views as conv_views
from apps.core import views as core_views
from apps.voice import views as voice_views
from apps.whatsapp import views as wa_views

router = DefaultRouter(trailing_slash=True)
router.register("conversations", conv_views.ConversationViewSet, basename="conversation")
router.register("drafts", conv_views.DraftViewSet, basename="draft")
router.register("contacts", conv_views.ContactViewSet, basename="contact")
router.register("examples", ai_views.FewShotExampleViewSet, basename="example")
router.register("knowledge", ai_views.KnowledgeEntryViewSet, basename="knowledge")

api = [
    path("auth/csrf/", core_views.csrf),
    path("auth/login/", core_views.login_view),
    path("auth/register/", core_views.register_view),
    path("auth/logout/", core_views.logout_view),
    path("auth/me/", core_views.me),
    path("workspace/", core_views.WorkspaceView.as_view()),
    path("dashboard/", core_views.DashboardView.as_view()),
    path("activity/", core_views.ActivityView.as_view()),
    path("integrations/", core_views.IntegrationsStatusView.as_view()),
    path("ai/settings/", ai_views.AISettingsView.as_view()),
    path("ai/test/", ai_views.ProviderTestView.as_view()),
    path("ai/generations/", ai_views.GenerationsView.as_view()),
    path("persona/", ai_views.PersonaView.as_view()),
    path("persona/preview/", ai_views.PersonaPreviewView.as_view()),
    path("persona/style-profile/", ai_views.StyleProfileView.as_view()),
    path("knowledge-categories/", ai_views.KnowledgeCategoriesView.as_view()),
    path("automation/", automation_views.AutomationSettingsView.as_view()),
    path("voice/", voice_views.VoiceSettingsView.as_view()),
    path("voice/voices/", voice_views.VoiceListView.as_view()),
    path("voice/test/", voice_views.VoiceTestView.as_view()),
    path("whatsapp/", wa_views.WhatsAppIntegrationView.as_view()),
    path("whatsapp/validate/", wa_views.WhatsAppValidateView.as_view()),
    path("whatsapp/embedded-signup/", wa_views.EmbeddedSignupView.as_view()),
    path("dev/simulate-inbound/", wa_views.DevSimulateInboundView.as_view()),
    path("messages/<int:pk>/retry/", conv_views.MessageRetryView.as_view()),
    path("media/<int:pk>/", conv_views.MediaView.as_view()),
    path("webhooks/whatsapp/", wa_views.whatsapp_webhook),
    path("", include(router.urls)),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(api)),
]
