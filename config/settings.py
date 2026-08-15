"""Settings for haresign-web — the public Haresign web layer.

Deliberately small. It renders public pages and owns one thing: Haresign's
public editorial content (the `insights` app).

The ownership boundary, which has not loosened now that there is a database:
this application has its **own** PostgreSQL database holding Web-owned content
only. It never connects to the monolith's database, never writes back to it, and
shares no models with it. Identity, primary-care application data and client
data belong to their own services.

Django Admin is the publishing backend, so auth/sessions/admin are installed.
Those accounts are **editorial staff logins for this admin**, not Haresign
identity — ecosystem identity is Haresign Account (auth.haresign.net) and is not
implemented here. No public view on this site reads `request.user`.

Anything that varies by environment is read from the environment. Nothing in
this file is a secret, and no secret has a default.
"""
import os
import sys
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
    # Admin is the publishing backend for Insights, which is why auth, sessions,
    # contenttypes and messages are here. Read the boundary carefully: these
    # accounts are *editorial staff logins for this site's admin*, not Haresign
    # identity. Ecosystem identity remains Haresign Account (auth.haresign.net)
    # and is not implemented here. Nothing public on this site has a user, and
    # no public view reads request.user.
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'tinymce',

    'insights',
    'newsletter',
    'web',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    # The newsletter form is the first public POST on this site. Note the
    # consequence, which is documented rather than hidden: `{% csrf_token %}`
    # sets a `csrftoken` cookie on every page carrying that form. It is a
    # strictly-necessary cookie and needs no consent, and the Cookie Policy names
    # it and says which pages set it.
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
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
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'web.context_processors.site',
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------
# A PostgreSQL database owned by *this* application and nothing else.
#
# The architectural rule has not loosened. haresign-web must never become the
# shared backend for the ecosystem, and this database is not a step toward that:
# it holds Web-owned editorial content only. It is a separate database on a
# separate container from the monolith's, this application never connects to the
# monolith's database, and nothing writes back to it. Identity, primary-care
# application data and client data stay with their own services.
#
# Discrete variables rather than a DATABASE_URL, so a password containing "@" or
# "/" needs no URL-encoding and cannot silently truncate a connection string.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'haresign_web'),
        'USER': os.environ.get('POSTGRES_USER', 'haresign_web'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        # Persistent connections; gunicorn workers are long-lived.
        'CONN_MAX_AGE': int(os.environ.get('DB_CONN_MAX_AGE', 60)),
    }
}

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

# --- Media (uploaded files) -------------------------------------------------
# Featured images and any images placed in article bodies. Binary data never
# goes in PostgreSQL: the database holds the *path*, the bytes live on a volume.
#
# Storage is declared through STORAGES['default'], so moving to object storage
# (Cloudflare R2 via django-storages' S3 backend) later is a settings change plus
# a file copy — the Article model, the templates and the admin are unaffected
# because they only ever touch `article.featured_image.url`. See README, "Media".
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', BASE_DIR / 'media'))

# --- TinyMCE ----------------------------------------------------------------
# The monolith's blog authors in TinyMCE and stores HTML. Insights does the same
# deliberately: it keeps the authoring model familiar and, more importantly, means
# legacy article HTML can be imported later without rewriting a single article.
#
# The toolbar is the set of things Haresign articles actually use — headings,
# emphasis, links, lists, quotes, tables, images, and a source view for fixing
# imported markup. Everything else was left out; a 40-button toolbar makes an
# editor harder to use, not more capable.
TINYMCE_DEFAULT_CONFIG = {
    'height': 620,
    'menubar': 'edit view insert format table',
    'plugins': (
        'advlist autolink lists link image charmap preview anchor '
        'searchreplace visualblocks code fullscreen '
        'insertdatetime media table wordcount'
    ),
    'toolbar': (
        'undo redo | blocks | bold italic | '
        'alignleft aligncenter alignright | '
        'bullist numlist outdent indent | '
        'link image blockquote table | removeformat | code fullscreen'
    ),
    # Only the block types the article stylesheet actually styles, so an author
    # cannot pick a heading level the design does not render.
    'block_formats': 'Paragraph=p; Heading 2=h2; Heading 3=h3; Heading 4=h4; Quote=blockquote; Code=pre',
    'branding': False,
    'promotion': False,
    'convert_urls': False,      # keep hrefs exactly as typed/imported
    'relative_urls': False,
    'browser_spellcheck': True,
    'contextmenu': False,
}
# Served from the installed package, never a CDN — the site keeps no external
# runtime dependency and the admin works on a locked-down network.
TINYMCE_JS_URL = None

# --- Security --------------------------------------------------------------

# Behind Traefik, which terminates TLS. Without this Django never sees a secure
# request and will not emit HSTS or mark cookies secure.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# The test runner must not depend on the deployment environment. With
# SECURE_SSL_REDIRECT on, every test-client request 301s and the response body is
# empty, so assertions fail for a reason that has nothing to do with the code.
TESTING = 'test' in sys.argv

if not DEBUG and not TESTING:
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
