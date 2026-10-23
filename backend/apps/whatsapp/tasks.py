import hashlib

from django.core.files.base import ContentFile

from apps.conversations.models import MediaAsset
from apps.core.jobs import RetryableJobError, register
from apps.core.services import record_error

from .client import WhatsAppClient, WhatsAppError
from .models import WhatsAppIntegration

EXT = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/aac": "aac", "audio/amr": "amr",
       "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}


@register("whatsapp.fetch_media")
def fetch_media(media_id):
    media = MediaAsset.objects.select_related("workspace").get(pk=media_id)
    if media.download_status == "ready":
        return
    integration = WhatsAppIntegration.objects.filter(workspace=media.workspace).first()
    try:
        client = WhatsAppClient.for_integration(integration)
        content, mime = client.download_media(media.provider_media_id)
    except WhatsAppError as exc:
        media.download_status = "failed"
        media.error = exc.message[:500]
        media.save(update_fields=["download_status", "error"])
        record_error(media.workspace, "whatsapp", exc.code or "media_download", exc.message)
        if exc.retryable:
            media.download_status = "pending"
            media.save(update_fields=["download_status"])
            raise RetryableJobError(exc.message)
        return
    base_mime = (mime or media.mime_type).split(";")[0].strip()
    media.mime_type = base_mime[:100]
    media.size = len(content)
    media.sha256 = hashlib.sha256(content).hexdigest()
    media.file.save(f"in_{media.pk}.{EXT.get(base_mime, 'bin')}", ContentFile(content), save=False)
    media.download_status = "ready"
    media.error = ""
    media.save()
