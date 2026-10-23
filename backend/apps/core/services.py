from .models import AuditLog, UsageEvent
from .logging import redact


def audit(workspace, user, action, target=None, **details):
    return AuditLog.objects.create(
        workspace=workspace,
        user=user if (user is not None and user.is_authenticated) else None,
        action=action,
        target_type=target.__class__.__name__ if target is not None else "",
        target_id=str(getattr(target, "pk", "") or ""),
        details=details,
    )


def record_usage(workspace, kind, *, source="", operation="", model="", success=True, message="", **fields):
    return UsageEvent.objects.create(
        workspace=workspace,
        kind=kind,
        source=source,
        operation=operation,
        model=model or "",
        success=success,
        message=redact(message or "")[:500],
        **fields,
    )


def record_error(workspace, source, error_code, message, **details):
    return record_usage(
        workspace,
        UsageEvent.Kind.ERROR,
        source=source,
        success=False,
        error_code=str(error_code or "")[:64],
        message=message,
        details=details,
    )


def ensure_workspace_defaults(workspace):
    """Create the per-workspace settings rows with first-run defaults."""
    from django.conf import settings

    from apps.ai.models import AISettings, PersonaProfile
    from apps.automation.models import AutomationSettings
    from apps.voice.models import VoiceSettings

    AISettings.objects.get_or_create(workspace=workspace, defaults={"provider": settings.AI_PROVIDER})
    PersonaProfile.objects.get_or_create(workspace=workspace)
    AutomationSettings.objects.get_or_create(workspace=workspace)
    VoiceSettings.objects.get_or_create(
        workspace=workspace, defaults={"model_id": settings.ELEVENLABS_DEFAULT_MODEL}
    )
