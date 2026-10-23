"""
Django settings for the WhatsApp AI assistant.

All environment-dependent configuration is read through python-decouple
(`.env` file or real environment variables). See `.env.example`.
"""

from pathlib import Path

from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------
# Required: no default. decouple raises UndefinedValueError when it is missing.
SECRET_KEY = config("DJANGO_SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)

if not DEBUG and SECRET_KEY in {"replace-me", "change-me", ""}:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a strong value when DEBUG is False.")

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")
BACKEND_PUBLIC_URL = config("BACKEND_PUBLIC_URL", default="http://localhost:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.core",
    "apps.whatsapp",
    "apps.conversations",
    "apps.ai",
    "apps.automation",
    "apps.voice",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------
# Database: SQLite for simple local development, MySQL preferred otherwise.
# --------------------------------------------------------------------------
DATABASE_ENGINE = config("DATABASE_ENGINE", default="sqlite").lower()

if DATABASE_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / config("SQLITE_NAME", default="db.sqlite3"),
            "OPTIONS": {"timeout": 20},
        }
    }
elif DATABASE_ENGINE == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": config("MYSQL_DATABASE"),
            "USER": config("MYSQL_USER"),
            "PASSWORD": config("MYSQL_PASSWORD"),
            "HOST": config("MYSQL_HOST", default="127.0.0.1"),
            "PORT": config("MYSQL_PORT", default="3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    raise ImproperlyConfigured("DATABASE_ENGINE must be 'sqlite' or 'mysql'.")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = config("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media (voice notes, inbound media). Served only through the authenticated
# /api/media/<id>/ endpoint, never through a public URL.
MEDIA_ROOT = BASE_DIR / config("MEDIA_DIR", default="media_store")
MEDIA_URL = "/media-not-public/"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Security / sessions / CORS
# --------------------------------------------------------------------------
# The Vite dev server proxies /api to Django, so the SPA is same-origin and uses
# session cookies + CSRF tokens. Nothing secret is stored in browser storage.
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default=FRONTEND_URL, cast=Csv())
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default=FRONTEND_URL, cast=Csv())
CORS_ALLOW_CREDENTIALS = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

ALLOW_REGISTRATION = config("ALLOW_REGISTRATION", default=DEBUG, cast=bool)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth": config("THROTTLE_AUTH", default="10/min"),
        "ai": config("THROTTLE_AI", default="30/min"),
        "send": config("THROTTLE_SEND", default="60/min"),
        "webhook": config("THROTTLE_WEBHOOK", default="600/min"),
    },
    "DEFAULT_PAGINATION_CLASS": None,
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
}

# --------------------------------------------------------------------------
# AI providers
# --------------------------------------------------------------------------
SUPPORTED_AI_PROVIDERS = ("gemini", "deepseek", "groq")

AI_PROVIDER = config("AI_PROVIDER", default="gemini").lower()
if AI_PROVIDER not in SUPPORTED_AI_PROVIDERS:
    raise ImproperlyConfigured(
        f"AI_PROVIDER must be one of {', '.join(SUPPORTED_AI_PROVIDERS)} (got '{AI_PROVIDER}')."
    )

AI_REQUEST_TIMEOUT = config("AI_REQUEST_TIMEOUT", default=60, cast=int)  # seconds
AI_MAX_RETRIES = config("AI_MAX_RETRIES", default=1, cast=int)  # retries on invalid output / transient errors

GEMINI_API_KEY = config("GEMINI_API_KEY", default="")
# Defaults verified against https://ai.google.dev/gemini-api/docs/models (Oct 2026).
# gemini-3.5-flash-lite: recommended for new projects and much less congested than 3.8 Flash
# (live test Oct 2026: ~1-2 s per reply; gemini-3.8-flash returned 503 "high demand" / 504).
GEMINI_MODEL = config("GEMINI_MODEL", default="gemini-3.5-flash-lite")
# Blank = model default. Supported levels differ per model (3.8 Flash: low/medium/high;
# 3.5 Flash-Lite: minimal/low/medium/high). See https://ai.google.dev/gemini-api/docs/thinking
GEMINI_THINKING_LEVEL = config("GEMINI_THINKING_LEVEL", default="").lower()
if GEMINI_THINKING_LEVEL not in {"", "minimal", "low", "medium", "high"}:
    raise ImproperlyConfigured("GEMINI_THINKING_LEVEL must be blank, minimal, low, medium or high.")

DEEPSEEK_API_KEY = config("DEEPSEEK_API_KEY", default="")
# Defaults verified against https://api-docs.deepseek.com/ (Oct 2026).
DEEPSEEK_MODEL = config("DEEPSEEK_MODEL", default="deepseek-flash")
DEEPSEEK_BASE_URL = config("DEEPSEEK_BASE_URL", default="https://api.deepseek.com")

# Groq (GroqCloud, https://console.groq.com) - official API with a FREE plan (rate limited:
# about 30 requests/min, 1K requests/day, 8K tokens/min per model as of Oct 2026).
# openai/gpt-oss-120b is a Groq production model that supports JSON mode.
GROQ_API_KEY = config("GROQ_API_KEY", default="")
GROQ_MODEL = config("GROQ_MODEL", default="openai/gpt-oss-120b")
GROQ_BASE_URL = config("GROQ_BASE_URL", default="https://api.groq.com/openai/v1")
GROQ_REASONING_EFFORT = config("GROQ_REASONING_EFFORT", default="low").lower()
if GROQ_REASONING_EFFORT not in {"", "low", "medium", "high"}:
    raise ImproperlyConfigured("GROQ_REASONING_EFFORT must be blank, low, medium or high.")

# --------------------------------------------------------------------------
# ElevenLabs
# --------------------------------------------------------------------------
ELEVENLABS_API_KEY = config("ELEVENLABS_API_KEY", default="")
ELEVENLABS_BASE_URL = config("ELEVENLABS_BASE_URL", default="https://api.elevenlabs.io")
ELEVENLABS_DEFAULT_MODEL = config("ELEVENLABS_DEFAULT_MODEL", default="eleven_multilingual_v2")
# Ogg/Opus is required for native WhatsApp voice notes.
ELEVENLABS_OUTPUT_FORMAT = config("ELEVENLABS_OUTPUT_FORMAT", default="opus_48000_64")
ELEVENLABS_TIMEOUT = config("ELEVENLABS_TIMEOUT", default=45, cast=int)

# --------------------------------------------------------------------------
# WhatsApp Cloud API (Meta)
# --------------------------------------------------------------------------
WHATSAPP_GRAPH_VERSION = config("WHATSAPP_GRAPH_VERSION", default="v26.0")
WHATSAPP_GRAPH_BASE_URL = config("WHATSAPP_GRAPH_BASE_URL", default="https://graph.facebook.com")
WHATSAPP_ACCESS_TOKEN = config("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = config("WHATSAPP_PHONE_NUMBER_ID", default="")
WHATSAPP_BUSINESS_ACCOUNT_ID = config("WHATSAPP_BUSINESS_ACCOUNT_ID", default="")
WHATSAPP_VERIFY_TOKEN = config("WHATSAPP_VERIFY_TOKEN", default="")
WHATSAPP_TIMEOUT = config("WHATSAPP_TIMEOUT", default=20, cast=int)
META_APP_ID = config("META_APP_ID", default="")
META_APP_SECRET = config("META_APP_SECRET", default="")
META_EMBEDDED_SIGNUP_CONFIG_ID = config("META_EMBEDDED_SIGNUP_CONFIG_ID", default="")
# Development only: accept webhooks without X-Hub-Signature-256 when META_APP_SECRET
# is not configured. Refused unless DEBUG is True.
WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS = config("WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS", default=False, cast=bool)
if WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS and not DEBUG:
    raise ImproperlyConfigured("WHATSAPP_ALLOW_UNSIGNED_WEBHOOKS may only be enabled when DEBUG is True.")

# --------------------------------------------------------------------------
# Background jobs
#   thread: run each job in a background thread right after the request (local dev)
#   worker: only enqueue; run `python manage.py run_jobs` separately
#   sync:   run inline (tests)
# --------------------------------------------------------------------------
JOBS_MODE = config("JOBS_MODE", default="thread")
if JOBS_MODE not in {"thread", "worker", "sync"}:
    raise ImproperlyConfigured("JOBS_MODE must be 'thread', 'worker' or 'sync'.")

# --------------------------------------------------------------------------
# Logging (secrets are redacted by apps.core.logging.RedactSecretsFilter)
# --------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact": {"()": "apps.core.logging.RedactSecretsFilter"}},
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple", "filters": ["redact"]},
    },
    "root": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "urllib3": {"level": "WARNING"},
        "httpx": {"level": "WARNING"},
        "google_genai": {"level": "WARNING"},
    },
}
