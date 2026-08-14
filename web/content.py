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


PRINCIPLES = [
    {
        'icon': 'evidence',
        'heading': 'Evidence-led',
        'body': 'Insight people can actually use.',
    },
    {
        'icon': 'experience',
        'heading': 'Built from experience',
        'body': 'Created around the realities of running primary care.',
    },
    {
        'icon': 'practical',
        'heading': 'Practical',
        'body': 'Tools and support intended to help people make decisions and take action.',
    },
    {
        'icon': 'connected',
        'heading': 'Connected',
        'body': 'Consulting, intelligence, workspace and community working as '
                'one Haresign ecosystem.',
    },
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
