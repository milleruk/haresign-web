"""The Haresign service registry — names *and* URLs, in one place.

Naming convention: **Haresign + a clear functional product name**. The master
brand stays visibly dominant and no service gets a standalone name of its own
(no Pulse, Nexus, Hub or Portal), so the ecosystem reads as one company rather
than several unrelated businesses.

`name` is the customer-facing product name and `nav_label` the short form for
places with no room for the full one. Both live here so a rename is one edit —
no template repeats either.

Note the slug/host split, which is deliberate and will persist through the
migration: the *slugs* are the product names (`intelligence`, `workspace`,
`account`) while the *hosts* remain the ones already deployed
(`app.`, `clients.`, `auth.`). Renaming a live subdomain is a separate, riskier
job than renaming a product, so the two are allowed to differ.

Each service also carries whether it is actually live, because the platforms are
not arriving at once and a card linking to a host that does not resolve is worse
than one that says so. `available` is what makes "Coming soon" a configuration
change rather than a template edit.
"""
import os


def _live_services():
    """Slugs of services currently reachable, from HARESIGN_LIVE_SERVICES.

    Defaults to Intelligence, Community and the documentation — the three that
    verifiably answer today. Deliberately an allow-list: a service added to the
    registry later is "not live" until somebody says otherwise, which is the safe
    way to be wrong.

    Community was added once community.haresign.net was confirmed serving. Note
    what did *not* have to change for it: no template, no card, no nav item, no
    FAQ answer and no CTA route. Every one of them asks this registry.
    """
    raw = os.environ.get('HARESIGN_LIVE_SERVICES', 'intelligence,community,docs')
    return {slug.strip().lower() for slug in raw.split(',') if slug.strip()}


def _url(env_name, default):
    return os.environ.get(env_name, default).strip()


def build_registry():
    """Return the service registry as an ordered dict of slug -> service.

    Order is display order: the four public platforms as they appear on the
    homepage, then Account and the API, which are infrastructure rather than
    destinations people browse to.
    """
    live = _live_services()

    services = {
        'consulting': {
            'name': 'Haresign Consulting',
            'nav_label': 'Consulting',
            'url': _url('HARESIGN_URL_CONSULTING', 'https://consulting.haresign.net'),
            'accent': 'coral',
        },
        'intelligence': {
            'name': 'Haresign Intelligence',
            'nav_label': 'Intelligence',
            # Host stays app.haresign.net — the product was renamed, not the
            # deployment. "Haresign App" is no longer a customer-facing name.
            'url': _url('HARESIGN_URL_INTELLIGENCE', 'https://app.haresign.net'),
            'accent': 'teal',
        },
        'community': {
            'name': 'Haresign Community',
            'nav_label': 'Community',
            'url': _url('HARESIGN_URL_COMMUNITY', 'https://community.haresign.net'),
            'accent': 'aqua',
        },
        'workspace': {
            'name': 'Haresign Workspace',
            'nav_label': 'Workspace',
            # Host stays clients.haresign.net. "Haresign Clients" and "Client
            # Portal" are both retired as customer-facing names.
            'url': _url('HARESIGN_URL_WORKSPACE', 'https://clients.haresign.net'),
            'accent': 'navy',
        },
        # Identity. Users see "Haresign Account"; "Haresign Core" is an internal
        # architectural term for this service and must never reach the page.
        # Not a platform card — it backs the account/sign-in action, and it is
        # deliberately not live: authentication is later work and the control
        # must not imply it already exists.
        'account': {
            'name': 'Haresign Account',
            'nav_label': 'Sign in',
            'url': _url('HARESIGN_URL_ACCOUNT', 'https://auth.haresign.net'),
            'accent': 'navy',
        },
        # Documentation. It is **not copied into this repository** — Web links to
        # the service that owns the content, which is the ownership boundary
        # applied to docs as much as to tools.
        #
        # Read its contents before deciding where it belongs: Platform, Tools,
        # Data Sources, Developer API. That is Haresign Intelligence
        # documentation, not ecosystem documentation, so it is labelled as such
        # and lives under Resources in the footer rather than in the main nav —
        # most visitors to the umbrella site are not looking for a tools manual.
        'docs': {
            'name': 'Documentation',
            'nav_label': 'Docs',
            'url': _url('HARESIGN_URL_DOCS', 'https://haresign.readthedocs.io/en/latest/'),
            'accent': 'teal',
            'owner': 'intelligence',
        },
        # Developer-facing, listed for completeness so nothing else invents a
        # name or a URL for it.
        'api': {
            'name': 'Haresign API',
            'nav_label': 'API',
            'url': _url('HARESIGN_URL_API', 'https://api.haresign.net'),
            'accent': 'navy',
        },
    }

    for slug, service in services.items():
        service['slug'] = slug
        service['available'] = slug in live

    return services


HARESIGN_SERVICES = build_registry()
