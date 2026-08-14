"""Read queries for Insights, in one place.

Both the Insights index and the homepage need "the featured article" and "recent
articles", and two implementations of that would eventually disagree. Keeping
them here also honours the rule that query logic lives in Python, not templates.
"""
from .models import Article


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
    returns everything, which is what the index wants.
    """
    qs = Article.objects.live().prefetch_related('categories')
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return list(qs[:limit] if limit is not None else qs)
