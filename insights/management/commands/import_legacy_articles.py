"""One-way import of the monolith's blog into Insights.

**It reads a JSON export file, never a database.** haresign-web does not connect
to the monolith's PostgreSQL, and it must not: a direct connection would be
exactly the shared-database coupling this repository exists to avoid, and it
would make beta depend on production being up.

Produce the export *in the monolith*:

    docker compose exec haresign_net python manage.py dumpdata \\
        website.BlogPost website.BlogTag \\
        --natural-foreign --indent 2 > legacy_articles.json

Copy the file here and run:

    python manage.py import_legacy_articles legacy_articles.json --dry-run
    python manage.py import_legacy_articles legacy_articles.json

The mapping is exact, not guessed — the legacy models are:

    BlogPost: title, slug, excerpt, content, hero_image, tags (M2M BlogTag),
              author_name, published_date (a DateField), is_published,
              created_at, updated_at
    BlogTag:  name, slug

    legacy                  ->  insights.Article
    title                   ->  title
    slug                    ->  slug            (unchanged: /blog/x/ -> /insights/x/)
    excerpt                 ->  summary
    content                 ->  body            (HTML copied verbatim)
    author_name             ->  author_name
    published_date          ->  published_at    (date -> aware datetime, 09:00 local)
    is_published            ->  status          (True -> published, False -> draft)
    hero_image              ->  featured_image  (path only; see --media-root)
    tags                    ->  tags

Legacy has **no categories, kicker, summary/meta split or featured flag**, so
those are left empty rather than invented. Article HTML is copied byte-for-byte:
rewriting it here would defeat the reason Insights uses TinyMCE at all.

Idempotent, matched on slug: re-running updates in place rather than duplicating,
so a delta import at cutover is the same command again. It is one-way and never
writes anything back to the monolith.
"""
import json
from datetime import datetime, time
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from insights.models import Article, Tag


class Command(BaseCommand):
    help = 'Import monolith blog articles from a dumpdata JSON export (one-way).'

    def add_arguments(self, parser):
        parser.add_argument('export', help='Path to the dumpdata JSON file.')
        parser.add_argument(
            '--media-root',
            help='Path to the monolith\'s media directory. When given, hero '
                 'images are copied in; without it the image path is skipped '
                 'and the article imports without one.',
        )
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change and roll back.')
        parser.add_argument('--only', nargs='*', metavar='SLUG',
                            help='Import just these slugs — how a representative '
                                 'article or two gets loaded for comparison.')

    def handle(self, *args, **options):
        path = Path(options['export'])
        if not path.exists():
            raise CommandError(f'Export file not found: {path}')

        try:
            records = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise CommandError(f'Could not parse {path}: {exc}')

        posts = [r for r in records if r.get('model', '').endswith('blogpost')]
        legacy_tags = {
            r['pk']: r['fields']
            for r in records if r.get('model', '').endswith('blogtag')
        }
        if not posts:
            raise CommandError(
                'No website.BlogPost records in the export. Check the dumpdata '
                'command included the right models.'
            )

        only = set(options['only'] or [])
        if only:
            posts = [p for p in posts if p['fields'].get('slug') in only]
            missing = only - {p['fields'].get('slug') for p in posts}
            if missing:
                self.stderr.write(self.style.WARNING(
                    f'Not in the export: {", ".join(sorted(missing))}'))

        media_root = Path(options['media_root']) if options.get('media_root') else None
        created = updated = images = 0

        try:
            with transaction.atomic():
                for post in posts:
                    f = post['fields']
                    was_created, got_image = self._import_one(f, legacy_tags, media_root)
                    created += was_created
                    updated += not was_created
                    images += got_image

                if options['dry_run']:
                    raise _Rollback()
        except _Rollback:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN — rolled back. Would create {created}, update {updated}, '
                f'copy {images} image(s).'))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Created {created}, updated {updated}, copied {images} image(s).'))

    def _import_one(self, f, legacy_tags, media_root):
        # published_date is a DateField; Insights stores a datetime. 09:00 local
        # is an arbitrary but consistent choice — the legacy data has no time, so
        # inventing one that sorts stably beats midnight, which can shift a date
        # across a timezone boundary.
        published_at = None
        if f.get('published_date'):
            naive = datetime.combine(
                datetime.strptime(f['published_date'], '%Y-%m-%d').date(), time(9, 0))
            published_at = timezone.make_aware(naive)

        article, was_created = Article.objects.update_or_create(
            slug=f['slug'],
            defaults={
                'title': f['title'],
                'summary': f.get('excerpt', ''),
                'body': f.get('content', ''),      # verbatim
                'author_name': f.get('author_name') or 'Haresign',
                'status': (Article.STATUS_PUBLISHED if f.get('is_published')
                           else Article.STATUS_DRAFT),
                'published_at': published_at,
            },
        )

        tag_objects = []
        for tag_pk in f.get('tags', []):
            fields = legacy_tags.get(tag_pk if not isinstance(tag_pk, list) else tag_pk[0])
            if not fields:
                continue
            tag, _ = Tag.objects.get_or_create(
                name=fields['name'], defaults={'slug': fields.get('slug', '')})
            tag_objects.append(tag)
        if tag_objects:
            article.tags.set(tag_objects)

        got_image = 0
        hero = f.get('hero_image')
        if hero and media_root:
            source = media_root / hero
            if source.exists():
                with source.open('rb') as fh:
                    article.featured_image.save(Path(hero).name, File(fh), save=True)
                got_image = 1
            else:
                self.stderr.write(self.style.WARNING(
                    f'  image missing for {article.slug}: {source}'))

        self.stdout.write(f'  {"+" if was_created else "~"} {article.slug}')
        return was_created, got_image


class _Rollback(Exception):
    """Signals a deliberate dry-run rollback, not a failure."""
