"""Settings for haresign-web — the public Haresign web layer.

Deliberately small. This application renders public pages and nothing else, so
it runs with **no database**: `DATABASES = {}` is a supported Django
configuration, and it is the clearest possible statement that this repository
does not share the monolith's data. Sessions, auth, admin and messages are all
absent for the same reason — nothing here has a user, so nothing here needs a
session cookie.

Anything that varies by environment is read from the environment. Nothing in
this file is a secret, and no secret has a default.
"""
import os
from pathlib import Path

from .services import HARESIGN_SERVICES  # noqa: F401  (re-exported for settings access)

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


# --- Core ------------------------------------------------------------------

# No default. The app refuses to start in production without one rather than
# running on a placeholder somebody forgets to replace (see the check below).
SECRET_KEY = os.environ.get('SECRET_KEY', '')
DEBUG = _env_bool('DEBUG', False)

ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1')

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-development-only-not-for-production'
    else:
        raise RuntimeError(
            'SECRET_KEY must be set when DEBUG is off. '
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(64))"'
        )

CSRF_TRUSTED_ORIGINS = [
    f'https://{host}' for host in ALLOWED_HOSTS
    if host not in ('*', 'localhost', '127.0.0.1')
]

INSTALLED_APPS = [
    'django.contrib.staticfiles',
    'web',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.common.CommonMiddleware',
    # No form on the site posts anything today, and this sets no cookie until a
    # template asks for a token — so it is free now and already correct on the
    # day somebody adds the first form, rather than a thing to remember then.
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'web.context_processors.site',
            ],
        },
    },
]

# No database. Not "an empty default" — genuinely none, so an accidental ORM
# import fails loudly here rather than quietly reaching for a connection.
DATABASES = {}

# --- Internationalisation --------------------------------------------------

LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'Europe/London'
USE_I18N = True
USE_TZ = True

# --- Static files ----------------------------------------------------------

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Hashed + compressed at collectstatic time, served straight from Gunicorn.
# One fewer moving part than a separate static container, and correct
# far-future caching comes for free.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
WHITENOISE_MAX_AGE = 31536000  # a year; filenames are content-hashed

# --- Security --------------------------------------------------------------

# Behind Traefik, which terminates TLS. Without this Django never sees a secure
# request and will not emit HSTS or mark cookies secure.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool('SECURE_SSL_REDIRECT', True)
    # The container health check calls http://127.0.0.1:8000/health/ directly,
    # with no proxy and so no X-Forwarded-Proto. Without this exemption the
    # redirect turns every check into a 301 and the container reports unhealthy
    # while serving traffic perfectly well.
    SECURE_REDIRECT_EXEMPT = [r'^health/$']
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# --- Site / SEO ------------------------------------------------------------

# Canonical origin, used for canonical URLs and absolute OpenGraph image URLs.
# On beta this is the beta host; it becomes https://haresign.net at promotion.
SITE_BASE_URL = os.environ.get('SITE_BASE_URL', 'https://beta.haresign.net').rstrip('/')
SITE_NAME = os.environ.get('SITE_NAME', 'Haresign')

# Search indexing is OFF unless explicitly enabled, so beta cannot be indexed by
# forgetting a flag — the unsafe state requires an action, not an omission.
# Flip to true only when this becomes production haresign.net.
SITE_INDEXABLE = _env_bool('SITE_INDEXABLE', False)

# Shown in the header so nobody mistakes the preview for the live site. Set to
# an empty string to remove it at promotion.
SITE_ENVIRONMENT_LABEL = os.environ.get('SITE_ENVIRONMENT_LABEL', 'Beta')

# --- Legal / company details ----------------------------------------------

# Structured placeholders. The real registration details belong to the business,
# not to this repository, so they are supplied by configuration and simply
# omitted from the footer when unset — an absent line is better than an invented
# one. See README "Environment variables".
LEGAL = {
    'company_name': os.environ.get('LEGAL_COMPANY_NAME', 'Haresign Consulting Services'),
    'company_number': os.environ.get('LEGAL_COMPANY_NUMBER', ''),
    'registered_address': os.environ.get('LEGAL_REGISTERED_ADDRESS', ''),
    'ico_registration': os.environ.get('LEGAL_ICO_REGISTRATION', ''),
    'contact_email': os.environ.get('LEGAL_CONTACT_EMAIL', 'contact@haresign.net'),
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': os.environ.get('LOG_LEVEL', 'INFO')},
}
