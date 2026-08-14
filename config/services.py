"""The Haresign service registry — the one place platform URLs are defined.

Subdomain layout will move during the migration, so no template hard-codes a
destination: they all read this. Each service also carries whether it is
actually *live*, because the four platforms are not arriving at once and a card
linking to a host that does not resolve is worse than one that says so.

`available` is what makes "Coming soon" a configuration change rather than a
template edit: an unavailable service renders as a badge instead of a link, so
nothing on the page can promise something that is not there yet.

Availability is env-driven (HARESIGN_LIVE_SERVICES) so a service can be switched
on the moment its DNS resolves, without a code change or a rebuild.
"""
import os


def _live_services():
    """Slugs of services currently reachable, from HARESIGN_LIVE_SERVICES.

    Defaults to the App alone — it is the only one of the four that exists
    today. Deliberately an allow-list rather than a deny-list: a service added
    to the registry later is "not live" until somebody says otherwise, which is
    the safe direction to be wrong in.
    """
    raw = os.environ.get('HARESIGN_LIVE_SERVICES', 'app')
    return {slug.strip().lower() for slug in raw.split(',') if slug.strip()}


def _url(env_name, default):
    return os.environ.get(env_name, default).strip()


def build_registry():
    """Return the service registry as an ordered dict of slug -> service.

    Built at import time from the environment. Order is display order: the four
    public platforms as they appear on the homepage, then identity, which is
    infrastructure rather than a destination people browse to.
    """
    live = _live_services()

    services = {
        'consulting': {
            'name': 'Consulting',
            'url': _url('HARESIGN_URL_CONSULTING', 'https://consulting.haresign.net'),
            'accent': 'coral',
        },
        'app': {
            'name': 'App',
            'url': _url('HARESIGN_URL_APP', 'https://app.haresign.net'),
            'accent': 'teal',
        },
        'community': {
            'name': 'Community',
            'url': _url('HARESIGN_URL_COMMUNITY', 'https://community.haresign.net'),
            'accent': 'aqua',
        },
        'clients': {
            'name': 'Clients',
            'url': _url('HARESIGN_URL_CLIENTS', 'https://clients.haresign.net'),
            'accent': 'navy',
        },
        # Identity. Not a platform card — it backs the Sign in action, and it is
        # deliberately not live: authentication is a later piece of work, and the
        # button must not imply it already exists.
        'auth': {
            'name': 'Sign in',
            'url': _url('HARESIGN_URL_AUTH', 'https://auth.haresign.net'),
            'accent': 'navy',
        },
    }

    for slug, service in services.items():
        service['slug'] = slug
        service['available'] = slug in live

    return services


HARESIGN_SERVICES = build_registry()
