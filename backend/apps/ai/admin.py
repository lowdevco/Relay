from django.contrib import admin

from .models import AIGeneration, AISettings, FewShotExample, KnowledgeEntry, PersonaProfile

admin.site.register(AISettings, list_display=["workspace", "provider", "fallback_enabled"])
admin.site.register(PersonaProfile)
admin.site.register(FewShotExample, list_display=["workspace", "situation", "active"])
admin.site.register(KnowledgeEntry, list_display=["workspace", "category", "title", "active"])
admin.site.register(AIGeneration, list_display=["workspace", "operation", "provider", "model", "status", "created_at"])
