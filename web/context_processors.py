"""Values every template needs, so no view has to remember to pass them."""
from django.conf import settings


def site(request):
    return {
        'SITE_NAME': settings.SITE_NAME,
        'SITE_BASE_URL': settings.SITE_BASE_URL,
        'SITE_INDEXABLE': settings.SITE_INDEXABLE,
        'SITE_ENVIRONMENT_LABEL': settings.SITE_ENVIRONMENT_LABEL,
        # Header, footer and platform cards all resolve destinations through
        # this, so a subdomain move is an environment change.
        'services': settings.HARESIGN_SERVICES,
        'legal': settings.LEGAL,
    }
