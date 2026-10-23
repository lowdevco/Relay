from django.contrib import admin

from .models import VoiceGeneration, VoiceSettings

admin.site.register(VoiceSettings)
admin.site.register(VoiceGeneration, list_display=["workspace", "status", "characters", "created_at"])
