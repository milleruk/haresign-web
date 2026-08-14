from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from .content import PLATFORMS, PRINCIPLES, get_insights


# How many areas a card lists. The cards stretch to the tallest in the row, so
# Intelligence's eleven were setting the height of all four and leaving the other
# three with a block of dead space beneath their list. Six keeps the row compact
# and the cards balanced; the copy says "areas include", so the list was never
# meant to be exhaustive. The full sets stay in content.py for later use.
CARD_AREA_LIMIT = 6


def build_platform_cards():
    """Join platform copy to the service registry into ready-to-render cards.

    Done here rather than in the template because Django templates cannot look a
    dict up by a variable key, and because the join is worth testing: whether a
    card links or says "Coming soon" is a product decision, not markup.

    `domain` is derived from the configured URL rather than written down a second
    time, so the label under a card can never disagree with where it points.
    """
    cards = []
    for platform in PLATFORMS:
        service = settings.HARESIGN_SERVICES[platform.service]
        cards.append({
            'platform': platform,
            # The card heading. Read from the registry rather than stored a
            # second time in content.py, so a product rename is one edit.
            'name': service['name'],
            'url': service['url'],
            'available': service['available'],
            'accent': service['accent'],
            'icon': platform.icon,
            'areas': platform.areas[:CARD_AREA_LIMIT],
            'domain': service['url'].split('://', 1)[-1].rstrip('/'),
        })
    return cards


def home(request):
    """The umbrella homepage.

    Platform copy comes from `content.PLATFORMS` and destinations from the
    service registry; `build_platform_cards()` joins them so neither knows about
    the other's storage.
    """
    insights = get_insights(limit=4)
    return render(request, 'web/home.html', {
        'platform_cards': build_platform_cards(),
        'principles': PRINCIPLES,
        # One featured article plus three cards. Sliced here rather than in the
        # template so the shape of the section is a decision in Python.
        'featured_article': insights[0] if insights else None,
        'recent_articles': insights[1:4],
    })


@never_cache
def health(request):
    """Liveness probe for the proxy and for deployment monitoring.

    Deliberately trivial: it answers "is this process serving requests", which
    is the only question this application can answer about itself. It touches no
    dependency, because there is none to touch — a health check that fails for a
    reason outside the service turns a working deploy into a red light.
    """
    return JsonResponse({'status': 'ok', 'service': 'haresign-web'})


def robots(request):
    """robots.txt, driven by SITE_INDEXABLE.

    Beta must not be indexed, so the default disallows everything. This is a
    second line of defence alongside the meta robots tag — crawlers honour one
    or the other, and getting indexed is easy to do and slow to undo.
    """
    if settings.SITE_INDEXABLE:
        body = (
            'User-agent: *\n'
            'Allow: /\n'
            f'Sitemap: {settings.SITE_BASE_URL}/sitemap.xml\n'
        )
    else:
        body = 'User-agent: *\nDisallow: /\n'
    return HttpResponse(body, content_type='text/plain')
