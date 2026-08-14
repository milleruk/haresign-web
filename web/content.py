"""Page content, kept out of the templates.

Two reasons this is a module rather than markup:

1. The insights section is explicitly meant to be re-pointed at an API, CMS or
   content service later. Everything below goes through `get_insights()`, so
   that swap is one function body — no template touches an article's source.
2. Copy that lives in Python can be tested. `web/tests.py` asserts the platform
   copy and the four principles actually reach the page, which markup buried in
   a template makes awkward.

The article entries here are placeholders for layout only, and say so. They are
*not* invented Haresign research: no fabricated findings, statistics or claims,
and `is_placeholder` lets the template mark them rather than passing them off as
published work.
"""
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Article:
    title: str
    summary: str
    published: date
    url: str = ''
    category: str = 'Insight'
    is_placeholder: bool = False

    @property
    def has_link(self):
        """A card with no destination renders as static, not as a dead link."""
        return bool(self.url)


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


# Placeholder article set. Titles describe the *kind* of thing Haresign
# publishes; none of them asserts a finding, a figure or an outcome, because a
# placeholder that reads as real research is a claim nobody made.
_PLACEHOLDER_ARTICLES = [
    Article(
        title='Making sense of your practice data',
        summary='How primary care teams can move from reporting numbers to '
                'acting on what those numbers actually show.',
        published=date(2026, 7, 22),
        category='Featured',
        is_placeholder=True,
    ),
    Article(
        title='Understanding your appointment data',
        summary='What GP appointment data does and does not tell you about access.',
        published=date(2026, 7, 8),
        is_placeholder=True,
    ),
    Article(
        title='Workforce planning in general practice',
        summary='Approaching workforce decisions with the data already available to you.',
        published=date(2026, 6, 24),
        is_placeholder=True,
    ),
    Article(
        title='Benchmarking without the noise',
        summary='Choosing comparisons that support a decision rather than start an argument.',
        published=date(2026, 6, 10),
        is_placeholder=True,
    ),
]


def get_insights(limit=4):
    """Return articles for the "Latest insight" section, newest first.

    The seam. Today it returns the placeholder set above; tomorrow it queries a
    CMS or an internal content API. Callers get `Article` objects either way, so
    replacing the body is the entire migration — the template never learns where
    an article came from.
    """
    articles = sorted(_PLACEHOLDER_ARTICLES, key=lambda a: a.published, reverse=True)
    return articles[:limit]
