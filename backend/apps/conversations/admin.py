from django.contrib import admin

from .models import Contact, Conversation, Draft, MediaAsset, Message

admin.site.register(Contact, list_display=["wa_id", "profile_name", "workspace"])
admin.site.register(Conversation, list_display=["contact", "workspace", "status", "human_takeover", "needs_attention"])
admin.site.register(Message, list_display=["conversation", "direction", "sender_type", "status", "created_at"])
admin.site.register(Draft, list_display=["conversation", "status", "created_at"])
admin.site.register(MediaAsset, list_display=["workspace", "source", "mime_type", "size"])
