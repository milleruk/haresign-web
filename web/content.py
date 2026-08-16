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


@dataclass(frozen=True)
class HeroSlide:
    """One frame of the homepage banner.

    The headline is stored in three parts rather than as one string because the
    typography carries meaning: `strong` is the heavy white subject, `light` is
    the connective phrase set at normal weight, and `accent` closes the line in
    slate. Putting the markup in the template and only the words here would mean
    the copy could not be tested without parsing HTML, and storing a single
    string with tags in it would put presentation in the content module.

    A slide points at exactly one destination. `url_name` is a Django URL name
    where the target is a page of this site; `anchor` is for in-page targets
    only. Nothing here names a host: a platform destination goes through the
    service registry, as everywhere else.
    """
    image: str      # stem under static/images/hero/, without width or extension
    strong: str
    light: str
    accent: str
    body: str
    cta: str
    url_name: str = ''
    anchor: str = ''


# The homepage banner: three slides over photography, rotating.
#
# This replaces the illustrated hero the migration shipped with. That version was
# technically fine and completely off-brand — a pale ground, a blurred colour
# field and a vector diagram, which is what every B2B SaaS homepage looks like.
# haresign.net has always led with a photograph of the actual work, white type
# over it, and one action. The visual language is the established one; only the
# copy is the umbrella brand's rather than the consultancy's.
#
# Three slides, one per audience question: what is Haresign now, what does it
# know, and who is behind it. The first keeps the line the whole page hangs on.
HERO_SLIDES = [
    HeroSlide(
        image='hero-ecosystem',
        strong='Haresign', light='has', accent='grown.',
        body='What started as helping primary care make better use of its data is '
             'now consultancy, intelligence, practical tools, client services and '
             'a growing professional community.',
        cta='Explore our platforms',
        anchor='#platforms',
    ),
    HeroSlide(
        image='hero-intelligence',
        strong='Insight', light='drawn from', accent='NHS data.',
        body='Published NHS datasets, benchmarked and explained — so decisions on '
             'funding, workforce and access are made with the evidence in front '
             'of you rather than the impression.',
        cta='Read the insights',
        url_name='insights:index',
    ),
    HeroSlide(
        image='hero-consultancy',
        strong='Support', light='from inside', accent='general practice.',
        body='Haresign was not built by a software company that found healthcare. '
             'It was built by people who have run practices and PCNs, and it shows '
             'in what it chooses to measure.',
        cta='Talk to us',
        url_name='contact',
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
