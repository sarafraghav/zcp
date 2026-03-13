from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="django-insecure-change-me-in-production")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*", cast=lambda v: [s.strip() for s in v.split(",")])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_htmx",
    "apps.organizations",
    "apps.accounts",
    "apps.database",
    "apps.workflows",
    "apps.dashboard",
    "apps.redis",
    "apps.projects",
    "apps.deployments",
    "apps.apikeys",
    "apps.api",
    "apps.docs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "zcp.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "zcp.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

TEMPORAL_HOST = config("TEMPORAL_HOST", default="zcp-raghav.dkqth.tmprl.cloud:7233")
TEMPORAL_NAMESPACE = config("TEMPORAL_NAMESPACE", default="zcp-raghav.dkqth")
TEMPORAL_API_KEY = config("TEMPORAL_API_KEY", default="")

NEON_API_KEY = config("NEON_API_KEY", default="")
NEON_ORG_ID = config("NEON_ORG_ID", default="")

UPSTASH_EMAIL = config("UPSTASH_EMAIL", default="")
UPSTASH_API_KEY = config("UPSTASH_API_KEY", default="")

DEPLOY_SAMPLE_DIR = BASE_DIR / "Sample Deployment"

# Pinned sample app repo for signup deploys — git clone → read zcp.json → orchestrate_deploy
SAMPLE_REPO_URL = config("SAMPLE_REPO_URL", default="https://github.com/sarafraghav/test_tictac.git")
SAMPLE_REPO_BRANCH = config("SAMPLE_REPO_BRANCH", default="main")
SAMPLE_REPO_COMMIT = config("SAMPLE_REPO_COMMIT", default="")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.APIKeyAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}
