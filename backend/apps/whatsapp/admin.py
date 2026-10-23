from django.contrib import admin

from .models import WebhookEvent, WhatsAppIntegration


@admin.register(WhatsAppIntegration)
class WhatsAppIntegrationAdmin(admin.ModelAdmin):
    list_display = ["workspace", "phone_number_id", "status"]
    exclude = ["access_token"]  # never display tokens


admin.site.register(WebhookEvent, list_display=["event_hash", "integration", "signature_valid", "received_at"])
