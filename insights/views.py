from django.shortcuts import get_object_or_404, render

from .models import Article
from .selectors import featured_article, recent_articles


def index(request):
    """The Insights index: a featured article, then the rest, newest first.

    The featured article is pulled out of the list rather than repeated in it —
    seeing the same piece twice at the top of a page reads as a bug.
    """
    featured = featured_article()
    articles = recent_articles(limit=None, exclude=featured)
    return render(request, 'insights/index.html', {
        'featured': featured,
        'articles': articles,
    })


def detail(request, slug):
    """A single article.

    Looked up through `live()`, so a draft, an archived piece or one scheduled
    for next week 404s exactly as an unknown slug does — no separate "not yet
    published" page that would confirm the article exists.
    """
    article = get_object_or_404(
        Article.objects.live().prefetch_related('categories', 'tags'),
        slug=slug,
    )
    return render(request, 'insights/detail.html', {'article': article})
