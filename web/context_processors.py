"""Values every template needs, so no view has to remember to pass them."""
from django.conf import settings

from .content import ECOSYSTEM_ROUTES


def _ecosystem_routes():
    """Join the ecosystem CTA's copy to the service registry.

    Here rather than in a view because the band appears on more than one page and
    a Django template cannot index a dict by a variable key. It is a pure
    in-memory join over four items — no query, no I/O — so paying for it on every
    render costs nothing, and any page can include the band without its view
    knowing the band exists.
    """
    return [
        {'service': settings.HARESIGN_SERVICES[route['service']],
         'action': route['action']}
        for route in ECOSYSTEM_ROUTES
    ]


def site(request):
    return {
        'SITE_NAME': settings.SITE_NAME,
        'SITE_BASE_URL': settings.SITE_BASE_URL,
        'SITE_INDEXABLE': settings.SITE_INDEXABLE,
        'SITE_ENVIRONMENT_LABEL': settings.SITE_ENVIRONMENT_LABEL,
        # Header, footer, platform cards and the ecosystem band all resolve
        # destinations through this, so a subdomain move is an environment change.
        'services': settings.HARESIGN_SERVICES,
        'ecosystem_routes': _ecosystem_routes(),
        'legal': settings.LEGAL,
    }
