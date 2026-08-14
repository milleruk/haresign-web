"""WSGI entry point.

Static files are served by the WhiteNoise *middleware*. Uploaded media is served
by a WhiteNoise wrapper here instead, because the middleware only knows about
STATIC_ROOT.

`autorefresh=True` is deliberate and is the whole reason this is a wrapper rather
than a startup scan: WhiteNoise otherwise indexes files once at boot, and an
image uploaded through the admin would 404 until the container was restarted —
unacceptable for a publishing system.

This is the beta arrangement. In production media should move to object storage
(Cloudflare R2) or sit behind the proxy; see README, "Media".
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

from django.conf import settings  # noqa: E402  (must follow django setup)
from whitenoise import WhiteNoise  # noqa: E402

application = WhiteNoise(application, autorefresh=True)
application.add_files(str(settings.MEDIA_ROOT), prefix=settings.MEDIA_URL)

# Legacy media, for the parallel-running comparison only.
#
# Monolith article bodies reference images as "../../../../uploads/library/…" —
# a TinyMCE convert_urls artifact that resolves to /uploads/… by accident of the
# URL depth it was authored at. Serving that prefix here means an imported
# article renders with its images *without rewriting a single byte of its HTML*,
# which is the point of comparing the two side by side.
#
# This is a comparison affordance, not the migration plan: the real import should
# rewrite these paths to MEDIA_URL. See README, "Legacy image paths".
_legacy = settings.MEDIA_ROOT / 'legacy'
if _legacy.exists():
    application.add_files(str(_legacy), prefix='/uploads/')
