"""Page content, kept out of the templates.

Two reasons this is a module rather than markup:

1. The insights section is explicitly meant to be re-pointed at an API, CMS or
   content service later. Everything below goes through `get_insights()`, so
   that swap is one function body — no template touches an article's source.
2. Copy that lives in Python can be tested. `web/tests.py` asserts the platform
   copy and the four principles actually reach the page, which markup buried in
   a template makes awkward.

`get_insights()` is the seam between this page and editorial content. It used to
return placeholders; it now reads the `insights` app, and the homepage template
was not touched to make that happen.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Platform:
    """One of the four platform cards.

    `service` is the registry slug (config/services.py), which is where the
    product *name*, the URL and the live/coming-soon state come from. This object
    carries only the copy unique to the card, so a rename or a subdomain move
    never touches this file — the card heading is `service.name`, not a second
    copy of it.
    """
    service: str
    blurb: str
    cta: str
    icon: str
    areas: list = field(default_factory=list)


PLATFORMS = [
    Platform(
        service='consulting',
        blurb='Practical support for practices, PCNs and primary care organisations.',
        cta='Explore Consulting',
        icon='compass',
        areas=['Strategy & planning', 'Access & capacity', 'Operations',
               'Transformation', 'Management support'],
    ),
    Platform(
        service='intelligence',
        blurb='Primary care data, insight and practical tools that turn '
              'information into action.',
        cta='Open Intelligence',
        icon='chart',
        areas=['Benchmarking', 'GP appointments', 'Patient experience', 'Workforce',
               'List size', 'Funding', 'Forecasting', 'Contracts', 'Compliance',
               'Clinical safety', 'Primary care management tools'],
    ),
    Platform(
        service='community',
        blurb='A place for primary care people to learn, share and support each other.',
        cta='Join the Community',
        icon='community',
        areas=['Discussions', 'Questions & answers', 'Resources',
               'Knowledge sharing', 'Peer support'],
    ),
    Platform(
        service='workspace',
        blurb='Your private workspace for projects, reports, analysis and resources.',
        cta='Open Workspace',
        icon='folder',
        areas=['Reports', 'Dashboards', 'Projects', 'Analysis',
               'Resources', 'Deliverables'],
    ),
]


# Credibility — one section, not two.
#
# This was previously a "principles" band (Evidence-led / Built from experience /
# Practical / Connected) *and* a separate credibility strip carrying the facts
# behind them. The two said the same four things, one abstractly and one
# concretely, which is repetition dressed up as structure. Merged: each item now
# states the principle and the fact that substantiates it, so the section makes a
# claim and backs it in the same breath.
#
# Every `proof` is already published on haresign.net. No customer counts, no
# performance claims, and nothing that turns the umbrella page into a personal
# profile — the people behind Haresign belong to Haresign Consulting.
CREDIBILITY = [
    {
        'icon': 'experience',
        'heading': 'Built from experience',
        'body': 'Created around the realities of managing and improving primary '
                'care, by someone who has done the job.',
        'proof': '25+ years in practice and business management',
    },
    {
        'icon': 'evidence',
        'heading': 'Evidence-led',
        'body': 'Published NHS data and practical analysis, so you can see what '
                'is actually happening rather than what it feels like.',
        'proof': 'Official NHS datasets, not estimates',
    },
    {
        'icon': 'practical',
        'heading': 'Practical by design',
        'body': 'Tools, insight and support built to help people decide '
                'something and then act on it.',
        'proof': 'Working with practices and PCNs across England',
    },
    {
        'icon': 'connected',
        'heading': 'Independent thinking',
        'body': 'Analysis and commentary meant to inform decisions — not to '
                'rank practices against each other.',
        'proof': 'Accredited member of the IGPM',
    },
]


# The pre-footer ecosystem call to action: four ways in, one per platform.
#
# `service` is the registry slug, so the name, the destination and whether it is
# live all come from one place — a route to a platform that has not launched
# renders as a label rather than a broken link, exactly as the cards and the nav
# already do.
ECOSYSTEM_ROUTES = [
    {'service': 'consulting',   'action': 'Get practical support.'},
    {'service': 'intelligence', 'action': 'Explore data and tools.'},
    {'service': 'community',    'action': 'Join the conversation.'},
    {'service': 'workspace',    'action': 'Access your work with Haresign.'},
]


def get_insights(limit=4):
    """Articles for the homepage "Latest insight" section, newest first.

    This was the documented seam for "today a placeholder list, tomorrow a real
    source". That swap has now happened: it reads the `insights` app, which this
    repository owns. The homepage template did not change — it never learned
    where an article came from, which was the point.

    Imported here rather than at module scope so `content` stays importable
    without the app registry being ready.
    """
    from insights.selectors import featured_article, recent_articles

    featured = featured_article()
    if featured is None:
        return []
    return [featured] + recent_articles(limit=limit - 1, exclude=featured)
