from django.core.paginator import InvalidPage, Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import Article, Tag
from .selectors import (PAGE_SIZE, article_list, featured_article, filter_tags,
                        recent_articles)


def index(request):
    """The Insights index: paginated, and filterable by tag.

    Three decisions worth knowing about.

    **The featured article leads page one only, and only unfiltered.** It is
    pulled out of the list rather than repeated in it, because seeing the same
    piece twice at the top of a page reads as a bug. On page two it would be
    stale furniture, and under a tag filter it would be an article ignoring the
    filter the reader just set — so in both cases the grid simply starts at the
    top.

    **An unknown tag or an out-of-range page is a 404, not an empty list.**
    `/insights/?tag=nonsense` names something that does not exist; answering it
    with "no articles found" invites the reader to conclude the archive is empty.

    **`page` is validated, `tag` is looked up.** Neither reaches a query
    unchecked.
    """
    tag = None
    tag_slug = request.GET.get('tag', '').strip()
    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)

    featured = featured_article() if tag is None else None

    articles = article_list(tag=tag)
    if featured is not None:
        articles = articles.exclude(pk=featured.pk)

    paginator = Paginator(articles, PAGE_SIZE)
    try:
        page = paginator.page(request.GET.get('page') or 1)
    except InvalidPage:
        # `InvalidPage`, not `EmptyPage`: Django raises `PageNotAnInteger` for
        # ?page=abc, which is a sibling of EmptyPage rather than a subclass, and
        # catching only EmptyPage turned a junk query string into a 500. Both
        # name a page that does not exist, so both are a 404.
        raise Http404('No such page of Insights.')

    # The featured article belongs to page one; on later pages it is not shown,
    # so the grid there is the whole content of the page.
    return render(request, 'insights/index.html', {
        'featured': featured if page.number == 1 else None,
        'page': page,
        'articles': page.object_list,
        'tags': filter_tags(),
        'active_tag': tag,
        'total': paginator.count + (1 if featured is not None else 0),
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
