"""Export the monolith's public editorial data as JSON. **Read-only.**

Run this *against* the monolith, from this repository — it is deliberately not
committed to `milleruk/haresign.net`, because the migration is one-way and the
legacy application should need no change to be migrated away from.

    cd /path/to/haresign.net
    docker compose exec -T haresign_net python manage.py shell \
        < /path/to/haresign-web/tools/export_from_monolith.py

It writes three files into the monolith container's working directory:

    legacy_articles.json      BlogPost + BlogTag
    legacy_newsletters.json   Newsletter (+ the article slugs each links to)
    legacy_subscribers.json   NewsletterSubscriber        ** PERSONAL DATA **

Copy them out with `docker compose cp`, import them, then delete them. The
subscriber file is a list of real email addresses: it is covered by .gitignore in
haresign-web, and it should not sit around on disk once the import is verified.

This script only ever reads. It opens no transaction, writes no row, and touches
no file inside the monolith's own tree.
"""
import json
import sys

from django.db.models import Q

from modules.core.website.models import BlogPost, BlogTag, NewsletterSubscriber
from modules.core.newsletter.models import Newsletter


def isoformat(value):
    return value.isoformat() if value else None


# --- Articles ---------------------------------------------------------------
# `legacy_id` is the source pk, carried so a slug corrected on either side does
# not silently create a second article. Tags are exported by name rather than by
# pk, so the file is readable and does not depend on the monolith's id space.
articles = []
for post in BlogPost.objects.prefetch_related('tags').order_by('pk'):
    articles.append({
        'legacy_id': post.pk,
        'legacy_path': f'/blog/{post.slug}/',
        'title': post.title,
        'slug': post.slug,
        'excerpt': post.excerpt,
        'content': post.content,
        'hero_image': post.hero_image.name or '',
        'author_name': post.author_name,
        'published_date': isoformat(post.published_date),
        'is_published': post.is_published,
        'created_at': isoformat(post.created_at),
        'updated_at': isoformat(post.updated_at),
        'tags': [{'name': t.name, 'slug': t.slug} for t in post.tags.all()],
    })

tags = [{'name': t.name, 'slug': t.slug} for t in BlogTag.objects.order_by('name')]

# --- Newsletter issues ------------------------------------------------------
# `intro` is the issue body (TinyMCE HTML). The M2M to BlogPost is exported as
# *slugs*, not pks: the importer resolves them against articles it has already
# imported, so an issue keeps its reading list without either side sharing an
# id space.
#
# `documents` is deliberately NOT exported. Those are SharedDocument rows behind
# the monolith's permission-checked download view — client material, not public
# editorial content, and not this repository's to hold.
newsletters = []
for issue in Newsletter.objects.prefetch_related('blog_posts').order_by('pk'):
    newsletters.append({
        'legacy_id': issue.pk,
        'legacy_path': f'/newsletter/archive/{issue.slug}/',
        'title': issue.title,
        'slug': issue.slug,
        'subject': issue.subject,
        'intro': issue.intro,
        'created_at': isoformat(issue.created_at),
        'updated_at': isoformat(issue.updated_at),
        'sent_at': isoformat(issue.sent_at),
        'send_count': issue.send_count,
        'article_slugs': [p.slug for p in issue.blog_posts.all()],
        'document_count': issue.documents.count(),
    })

# --- Subscribers ------------------------------------------------------------
# PERSONAL DATA. Every row is exported, including anyone who has unsubscribed:
# an unsubscribe is a fact that must survive the migration, and exporting only
# the active list is how somebody who opted out gets mailed again.
#
# The monolith has no unsubscribed_at, no double opt-in and no consent record —
# `active` is the whole of it. The importer must not invent the others.
subscribers = []
for sub in NewsletterSubscriber.objects.order_by('pk'):
    subscribers.append({
        'legacy_id': sub.pk,
        'email': sub.email,
        'name': sub.name,
        'active': sub.active,
        'subscribed_at': isoformat(sub.subscribed_at),
        'unsubscribe_token': str(sub.unsubscribe_token),
    })


for filename, payload in (
    ('legacy_articles.json', {'articles': articles, 'tags': tags}),
    ('legacy_newsletters.json', {'newsletters': newsletters}),
    ('legacy_subscribers.json', {'subscribers': subscribers}),
):
    with open(filename, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

sys.stderr.write(
    f'Exported {len(articles)} article(s), {len(tags)} tag(s), '
    f'{len(newsletters)} newsletter(s), {len(subscribers)} subscriber(s).\n'
    f'Counts for reconciliation:\n'
    f'  articles published : {sum(1 for a in articles if a["is_published"])}\n'
    f'  articles draft     : {sum(1 for a in articles if not a["is_published"])}\n'
    f'  articles with image: {sum(1 for a in articles if a["hero_image"])}\n'
    f'  newsletters sent   : {sum(1 for n in newsletters if n["sent_at"])}\n'
    f'  newsletters draft  : {sum(1 for n in newsletters if not n["sent_at"])}\n'
    f'  subscribers active : {sum(1 for s in subscribers if s["active"])}\n'
    f'  subscribers opted out: {sum(1 for s in subscribers if not s["active"])}\n'
)
