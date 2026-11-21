
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------
# Environment variables (.env for local development)
# ---------------------------------------------------------

def load_env_variables():
    """
    Load local .env variables only when they are not already
    provided by the environment (for example, Render).
    """
    env_path = BASE_DIR / ".env"

    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


load_env_variables()


# ---------------------------------------------------------
# Django security and host settings
# ---------------------------------------------------------

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-local-development-only",
)

DEBUG = os.getenv("DEBUG", "True").lower() == "true"

render_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "ALLOWED_HOSTS",
        "localhost,127.0.0.1",
    ).split(",")
    if host.strip()
]

if render_hostname:
    ALLOWED_HOSTS.append(render_hostname)


# ---------------------------------------------------------
# Applications
# ---------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party apps
    "rest_framework",

    # Custom apps
    "authentication.apps.AuthenticationConfig",
    "core.apps.CoreConfig",
    "consultations.apps.ConsultationsConfig",
    "api.apps.ApiConfig",
]


# ---------------------------------------------------------
# Middleware
# ---------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ---------------------------------------------------------
# URLs and templates
# ---------------------------------------------------------

ROOT_URLCONF = "mediscribe.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
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

WSGI_APPLICATION = "mediscribe.wsgi.application"


# ---------------------------------------------------------
# MySQL compatibility for local development
# ---------------------------------------------------------

try:
    import pymysql

    pymysql.install_as_MySQLdb()
except ImportError:
    pass


# ---------------------------------------------------------
# Database configuration
#
# Local: MySQL
# Render: Neon PostgreSQL using DATABASE_URL
# ---------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }

else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME") or "mediscribe_db",
            "USER": os.getenv("DB_USER") or "root",
            "PASSWORD": os.getenv("DB_PASSWORD") or "root",
            "HOST": os.getenv("DB_HOST") or "127.0.0.1",
            "PORT": os.getenv("DB_PORT") or "3306",
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
        }
    }


# ---------------------------------------------------------
# Password validation
# ---------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# ---------------------------------------------------------
# Internationalization
# ---------------------------------------------------------

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# ---------------------------------------------------------
# Static and media files
# ---------------------------------------------------------

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]

STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

MEDIA_URL = "/media/"

MEDIA_ROOT = os.path.join(BASE_DIR, "media")


# ---------------------------------------------------------
# Default primary key
# ---------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------
# Custom user model
# ---------------------------------------------------------

AUTH_USER_MODEL = "authentication.CustomUser"


# ---------------------------------------------------------
# Login and logout redirects
# ---------------------------------------------------------

LOGIN_URL = "login"

LOGIN_REDIRECT_URL = "dashboard"

LOGOUT_REDIRECT_URL = "home"


# ---------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "api.authentication.CsrfExemptSessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
}


# ---------------------------------------------------------
# CSRF trusted origins
# ---------------------------------------------------------

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

if render_hostname:
    CSRF_TRUSTED_ORIGINS.append(
        f"https://{render_hostname}"
    )

extra_csrf_origins = os.getenv(
    "CSRF_TRUSTED_ORIGINS",
    "",
)

if extra_csrf_origins:
    CSRF_TRUSTED_ORIGINS.extend(
        origin.strip()
        for origin in extra_csrf_origins.split(",")
        if origin.strip()
    )


# ---------------------------------------------------------
# Session and cookie settings
# ---------------------------------------------------------

CSRF_COOKIE_HTTPONLY = False

CSRF_USE_SESSIONS = False

SESSION_COOKIE_HTTPONLY = True

SESSION_COOKIE_SAMESITE = "Lax"

CSRF_COOKIE_SAMESITE = "Lax"


# ---------------------------------------------------------
# Render HTTPS / production security
# ---------------------------------------------------------

SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
