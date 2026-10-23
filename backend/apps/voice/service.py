import hashlib
import time

from django.conf import settings
from django.core.files.base import ContentFile

from apps.conversations.models import MediaAsset
from apps.core.models import UsageEvent
from apps.core.services import record_error, record_usage

from .elevenlabs import ElevenLabsClient, VoiceError, detect_audio_mime, is_configured
from .models import VoiceGeneration, VoiceSettings

MAX_VOICE_CHARS = 600
WHATSAPP_AUDIO_LIMIT = 16 * 1024 * 1024


def voice_readiness(voice_settings):
    """Return a list of blocking problems ([] = ready)."""
    problems = []
    if not is_configured():
        problems.append("ELEVENLABS_API_KEY is not configured on the server.")
    if not voice_settings.enabled:
        problems.append("Voice replies are disabled.")
    if not voice_settings.voice_id:
        problems.append("No voice selected.")
    if voice_settings.is_cloned_voice and not voice_settings.clone_consent_confirmed:
        problems.append("Cloned voice requires confirmed consent from the voice owner.")
    return problems


def synthesize_for_whatsapp(workspace, text, *, conversation=None, client=None):
    """Generate audio, store it, and return (MediaAsset, is_voice_note). Raises VoiceError."""
    vs = VoiceSettings.objects.get(workspace=workspace)
    problems = voice_readiness(vs)
    if problems:
        raise VoiceError(" ".join(problems), code="voice_not_ready")
    if len(text) > MAX_VOICE_CHARS:
        raise VoiceError(f"Text too long for a voice note ({len(text)} > {MAX_VOICE_CHARS} chars).", code="too_long")

    model_id = vs.model_id or settings.ELEVENLABS_DEFAULT_MODEL
    gen = VoiceGeneration.objects.create(
        workspace=workspace,
        conversation=conversation,
        text=text,
        voice_id=vs.voice_id,
        model_id=model_id,
        output_format=settings.ELEVENLABS_OUTPUT_FORMAT,
        characters=len(text),
    )
    started = time.monotonic()
    try:
        client = client or ElevenLabsClient()
        audio = client.synthesize(
            text,
            vs.voice_id,
            model_id=model_id,
            language_code=vs.language_code,
            stability=vs.stability,
            similarity_boost=vs.similarity_boost,
        )
        mime = detect_audio_mime(audio)
        if not mime:
            raise VoiceError("Generated audio is in an unrecognised format; cannot send to WhatsApp.", code="unsupported_format")
        if len(audio) > WHATSAPP_AUDIO_LIMIT:
            raise VoiceError("Generated audio exceeds WhatsApp's 16 MB limit.", code="too_large")
    except VoiceError as exc:
        gen.status = VoiceGeneration.Status.FAILED
        gen.error = exc.message[:500]
        gen.latency_ms = int((time.monotonic() - started) * 1000)
        gen.save(update_fields=["status", "error", "latency_ms"])
        record_usage(
            workspace, UsageEvent.Kind.VOICE_GENERATION, source="elevenlabs", model=model_id, success=False,
            characters=len(text), error_code=exc.code, message=exc.message,
        )
        record_error(workspace, "elevenlabs", exc.code, exc.message)
        raise

    # Native voice notes need Ogg/Opus; anything else (mp3) is sent as a basic audio message.
    is_voice_note = mime.startswith("audio/ogg") and "opus" in mime
    stored_mime = "audio/ogg" if mime.startswith("audio/ogg") else mime
    ext = "ogg" if stored_mime == "audio/ogg" else "mp3"
    media = MediaAsset(
        workspace=workspace,
        source=MediaAsset.Source.VOICE_GENERATED,
        mime_type=stored_mime,
        size=len(audio),
        sha256=hashlib.sha256(audio).hexdigest(),
    )
    media.file.save(f"voice_{gen.pk}.{ext}", ContentFile(audio), save=False)
    media.save()
    gen.status = VoiceGeneration.Status.SUCCESS
    gen.media = media
    gen.latency_ms = int((time.monotonic() - started) * 1000)
    gen.save(update_fields=["status", "media", "latency_ms"])
    record_usage(
        workspace, UsageEvent.Kind.VOICE_GENERATION, source="elevenlabs", model=model_id,
        characters=len(text), latency_ms=gen.latency_ms,
    )
    return media, is_voice_note, gen
