from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .contact import CONTACT_ROUTES
from .content import CREDIBILITY, HERO_SLIDES, PLATFORMS, get_insights
from .faq import FAQ_SECTIONS
from .legal import LAST_REVIEWED, LEGAL_PAGES


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


def build_hero_slides():
    """Pair each banner slide with the URL its button points at.

    Resolved here rather than in the template for the reason `{% url %}` cannot
    help with: a slide's destination is either a named route on this site or an
    in-page anchor, and a template that has to branch on which one it got ends up
    writing the choice twice — once in the tag and once in the fallback. One
    `href` per slide means the markup asks no questions.
    """
    return [
        {
            'slide': slide,
            'href': reverse(slide.url_name) if slide.url_name else slide.anchor,
        }
        for slide in HERO_SLIDES
    ]


def home(request):
    """The umbrella homepage.

    Platform copy comes from `content.PLATFORMS` and destinations from the
    service registry; `build_platform_cards()` joins them so neither knows about
    the other's storage.
    """
    insights = get_insights(limit=4)
    return render(request, 'web/home.html', {
        'hero_slides': build_hero_slides(),
        'platform_cards': build_platform_cards(),
        'credibility': CREDIBILITY,
        # One featured article plus three cards. Sliced here rather than in the
        # template so the shape of the section is a decision in Python.
        'featured_article': insights[0] if insights else None,
        'recent_articles': insights[1:4],
    })


def faq(request):
    """The umbrella FAQ.

    Each question's optional service link is resolved here, because a Django
    template cannot index a dict by a variable key — the same reason
    `build_platform_cards()` exists. Resolving it also means an unlaunched
    platform renders as a label rather than a link, without the template having
    to know the rule.
    """
    services = settings.HARESIGN_SERVICES
    sections = [
        {
            'anchor': section.anchor,
            'heading': section.heading,
            'items': [
                {
                    'question': question,
                    'link_service': services.get((question.link or {}).get('service')),
                }
                for question in section.questions
            ],
        }
        for section in FAQ_SECTIONS
    ]
    return render(request, 'web/faq.html', {'sections': sections})


def contact(request):
    """The contact routing page.

    A GET-only page: there is no form and nothing is posted. See web/contact.py
    for why routing rather than capture, and the README for what adding a form
    would cost.
    """
    services = settings.HARESIGN_SERVICES
    routes = [
        {'route': route, 'service': services.get(route.service)}
        for route in CONTACT_ROUTES
    ]
    return render(request, 'web/contact.html', {'routes': routes})


def legal_page(request, slug):
    """One view for all four legal pages.

    They differ only in their prose, so four views (and four near-identical
    templates) would be four places for the shell to drift. The metadata comes
    from `web/legal.py`; the document is `web/legal/<slug>.html`.

    Public and unauthenticated, deliberately and permanently: a privacy notice
    behind a login is not a privacy notice.
    """
    page = LEGAL_PAGES.get(slug)
    if page is None:
        raise Http404(f'No legal page: {slug}')
    return render(request, f'web/legal/{slug}.html', {
        # `slug` is added here rather than stored in LEGAL_PAGES so the two
        # cannot disagree; the template uses it to drop the current page from
        # the "other policies" list.
        'page': {**page, 'slug': slug},
        'legal_pages': LEGAL_PAGES,
        'last_reviewed': LAST_REVIEWED,
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
