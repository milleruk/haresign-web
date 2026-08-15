"""Read queries for Insights, in one place.

The index and the homepage ask overlapping questions, and two implementations of
"which articles may the public see" would eventually disagree. Keeping them here
also honours the rule that query logic lives in Python, not templates.
"""
from django.db.models import Count

from .models import Article, Tag

# Articles per page. Twelve is a clean grid at every width and divides the
# 67-article archive into six pages.
#
# The reason for paginating at all is not HTML weight — the whole archive was
# 70KB of markup — but images: the hero images behind one unpaginated index came
# to 64.8MB, and that grows with every article published.
PAGE_SIZE = 12

# How many tags the filter offers. All 24 exist and all are used, but a wall of
# chips where most return a third of the archive is worse than no filter at all.
FILTER_TAG_LIMIT = 10


def featured_article():
    """The article that leads the index and the homepage.

    The most recently published *featured* article; failing that, simply the most
    recent one, so the slot is never empty on a site that has articles.
    """
    base = Article.objects.live().prefetch_related('categories')
    return base.filter(is_featured=True).first() or base.first()


def recent_articles(limit=3, exclude=None):
    """Recent live articles, newest first.

    `exclude` drops the featured article so it is not shown twice. `limit=None`
    returns everything.
    """
    qs = Article.objects.live().prefetch_related('categories')
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return list(qs[:limit] if limit is not None else qs)


def filter_tags(limit=FILTER_TAG_LIMIT):
    """Tags worth offering as filters, with their article counts.

    **The counts are shown to the reader deliberately.** These tags are topical
    labels rather than a taxonomy: the median article carries five of them, and
    the largest covers more than half the archive. A chip that silently returns
    36 of 67 articles feels broken; one that says "Governance (36)" tells the
    reader what it will do before they spend a click finding out.

    Counted over *live* articles only, so a count can never promise more than the
    filter delivers.
    """
    return list(
        Tag.objects
        .filter(articles__status=Article.STATUS_PUBLISHED,
                articles__published_at__isnull=False)
        .annotate(article_count=Count('articles', distinct=True))
        .filter(article_count__gt=0)
        .order_by('-article_count', 'name')[:limit]
    )


def article_list(tag=None):
    """The archive, newest first, optionally narrowed to one tag.

    Returns a queryset, not a list: the caller paginates it, and evaluating 67
    articles in order to show 12 would defeat the point of paginating.
    """
    qs = Article.objects.live().prefetch_related('categories', 'tags')
    if tag is not None:
        qs = qs.filter(tags=tag)
    return qs
