from django.contrib import admin

from .models import AuditLog, Job, Membership, UsageEvent, Workspace

admin.site.register(Workspace)
admin.site.register(Membership, list_display=["user", "workspace", "role"])
admin.site.register(AuditLog, list_display=["workspace", "action", "user", "created_at"])
admin.site.register(UsageEvent, list_display=["workspace", "kind", "source", "success", "created_at"])
admin.site.register(Job, list_display=["kind", "status", "attempts", "created_at"])
