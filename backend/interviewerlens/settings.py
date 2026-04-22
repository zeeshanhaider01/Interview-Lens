import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

def getenv_bool(name, default="False"):
    return os.getenv(name, default).lower() in ("1", "true", "yes")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-not-secure")
DEBUG = getenv_bool("DJANGO_DEBUG", "True")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "interviewerlens.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "interviewerlens.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

database_url = (os.getenv("DATABASE_URL") or "").strip()
if database_url:
    parsed = urlparse(database_url)
    if parsed.scheme in ("postgres", "postgresql"):
        DATABASES["default"] = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
        }
        ssl_mode = parse_qs(parsed.query).get("sslmode", [""])[0]
        if ssl_mode:
            DATABASES["default"]["OPTIONS"] = {"sslmode": ssl_mode}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["api.auth.Auth0JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": f"{os.getenv('DAILY_RATELIMIT', '200')}/day"}
}

from corsheaders.defaults import default_headers
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]

CORS_ALLOW_HEADERS = list(default_headers) + ["authorization"]

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "")
AUTH0_ISSUER = os.getenv("AUTH0_ISSUER", "")
AUTH0_API_AUDIENCE = os.getenv("AUTH0_API_AUDIENCE", "")
FRONTEND_DASHBOARD_URL = os.getenv("FRONTEND_DASHBOARD_URL", "http://localhost:5173")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
AI_PROVIDER = os.getenv("AI_PROVIDER", "")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
AI_DEFAULT_PROVIDER = os.getenv("AI_DEFAULT_PROVIDER", "anthropic")
AI_SELECTION_STRATEGY = os.getenv("AI_SELECTION_STRATEGY", "auto")
AI_PROVIDER_PRIORITY = os.getenv("AI_PROVIDER_PRIORITY", "anthropic,openai")
AI_COST_SCORE_ANTHROPIC = float(os.getenv("AI_COST_SCORE_ANTHROPIC", "1.0"))
AI_COST_SCORE_OPENAI = float(os.getenv("AI_COST_SCORE_OPENAI", "1.2"))

# ------- CACHING / REDIS CONFIGURATION -------

# Feature flag: ENABLE_CACHING
# Set this to False to immediately disable all caching and locking logic (safe rollback).
ENABLE_CACHING = os.getenv("ENABLE_CACHING", "True").lower() in ("1", "true", "yes")

# Redis-backed cache configuration (used for locks and fast-result caching)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

# Tuneable TTLs (seconds)
CACHE_TTL_RUNNING = int(os.getenv("CACHE_TTL_RUNNING", "300"))   # lock TTL (default 5m)
CACHE_TTL_RESULT = int(os.getenv("CACHE_TTL_RESULT", "86400"))  # result cache (default 24h)

# ------- CELERY CONFIGURATION -------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_ALWAYS_EAGER = getenv_bool("CELERY_TASK_ALWAYS_EAGER", "False")
CELERY_TASK_EAGER_PROPAGATES = getenv_bool("CELERY_TASK_EAGER_PROPAGATES", "True")
