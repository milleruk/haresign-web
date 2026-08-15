"""One-way import of the monolith's blog into Insights.

**It reads a JSON export file, never a database.** haresign-web does not connect
to the monolith's PostgreSQL, and it must not: a direct connection would be
exactly the shared-database coupling this repository exists to avoid, and it
would make beta depend on production being up.

Produce the export *in the monolith* (read-only; it changes nothing there):

    docker compose exec -T haresign_net python manage.py shell \\
        < tools/export_from_monolith.py
    docker compose cp haresign_net:/app/legacy_articles.json _migration/
    docker compose cp haresign_net:/app/uploads/blog _migration/media/blog
    docker compose cp haresign_net:/app/uploads/library _migration/media/library

Then here:

    python manage.py import_legacy_articles _migration/legacy_articles.json \\
        --media-root _migration/media --dry-run
    python manage.py import_legacy_articles _migration/legacy_articles.json \\
        --media-root _migration/media

The mapping is exact, not guessed. The legacy model is:

    BlogPost: title, slug, excerpt, content, hero_image, tags (M2M BlogTag),
              author_name, published_date (a DateField), is_published,
              created_at, updated_at

    legacy                  ->  insights.Article
    id                      ->  legacy_id       (match key; never shown)
    title                   ->  title
    slug                    ->  slug            (unchanged: /blog/x/ -> /insights/x/)
    excerpt                 ->  summary
    content                 ->  body_source     (byte-for-byte) + body (rewritten)
    author_name             ->  author_name
    published_date          ->  published_at    (date -> aware datetime, 09:00 local)
    is_published            ->  status          (True -> published, False -> draft)
    hero_image              ->  featured_image  (file copied; see --media-root)
    tags                    ->  tags

Legacy has **no categories, kicker, meta title/description, featured flag or
image alt text**. Those are left empty rather than invented — an imported article
with a fabricated meta description is worse than one that falls back to its
summary, which is what `seo_description` already does.

The body is rewritten by `insights.importing`, which resolves relative URLs,
repoints article-to-article links and removes Bootstrap controls that cannot work
here. The original is kept in `body_source`, so every transform is auditable and
re-runnable.

**Idempotent.** Matched on `legacy_id`, falling back to `slug` for rows imported
before that field existed. Re-running is safe, which is what makes the delta
import at cutover the same command again.
"""
import json
from datetime import datetime, time
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from insights.importing import LinkReport, audit_body, rewrite_body
from insights.models import Article, Tag

# Where inline legacy images are copied to. Must match
# `importing.LEGACY_MEDIA_PREFIX`, which is what the rewritten HTML points at.
LEGACY_MEDIA_SUBDIR = Path('insights/legacy')


class Command(BaseCommand):
    help = 'Import monolith blog articles from a JSON export (one-way, idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('export', help='Path to legacy_articles.json.')
        parser.add_argument(
            '--media-root',
            help="Directory holding the monolith's copied upload trees (expects "
                 "blog/ and library/ inside it). Without it, images are skipped "
                 "and every article still imports — but reports as missing media.",
        )
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change, then roll back.')
        parser.add_argument(
            '--update-existing', action='store_true', default=True,
            help='Update articles already here (the default). '
                 '--no-update-existing imports only what is new.')
        parser.add_argument('--no-update-existing', dest='update_existing',
                            action='store_false')
        parser.add_argument(
            '--since', metavar='YYYY-MM-DD',
            help='Only import records whose source updated_at is on or after '
                 'this date — the delta import for cutover day. Omit it and the '
                 'full export is processed, which is equally safe.')
        parser.add_argument('--only', nargs='*', metavar='SLUG',
                            help='Import just these slugs.')
        parser.add_argument(
            '--link-report', metavar='PATH',
            help='Write the link/redirect analysis here as JSON.')

    # -- entry point --------------------------------------------------------

    def handle(self, *args, **options):
        payload = self._load(options['export'])
        records = payload['articles']
        source_total = len(records)

        selected, skipped = self._select(records, options)

        # Every slug in the *export*, not just the selection: a link from a
        # delta-imported article to one imported last month must still resolve.
        known_slugs = {r['slug'] for r in records}
        known_slugs |= set(Article.objects.values_list('slug', flat=True))

        media_root = Path(options['media_root']) if options.get('media_root') else None
        if media_root and not media_root.exists():
            raise CommandError(f'--media-root does not exist: {media_root}')

        stats = _Stats(source_total=source_total, skipped=skipped)
        report = LinkReport()
        self.meta_titles_taken = 0

        try:
            with transaction.atomic():
                # Not inside the dry run. `transaction.atomic` rolls back rows,
                # not files — a "dry" run that copied 127MB onto the volume and
                # left it there would not be a dry run. Counted instead.
                if media_root:
                    stats.inline_files = self._copy_inline_media(
                        media_root, plan_only=options['dry_run'])

                for record in selected:
                    self._import_one(record, known_slugs, media_root,
                                     stats, report, options)

                if options['dry_run']:
                    raise _Rollback()
        except _Rollback:
            self.stdout.write(self.style.WARNING('DRY RUN — everything rolled back.'))

        self._report(stats, report, options)

    # -- steps --------------------------------------------------------------

    def _load(self, path_str):
        path = Path(path_str)
        if not path.exists():
            raise CommandError(f'Export file not found: {path}')
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise CommandError(f'Could not parse {path}: {exc}')
        if 'articles' not in payload:
            raise CommandError(
                'No "articles" key in the export. This command reads the file '
                'produced by tools/export_from_monolith.py.')
        return payload

    def _select(self, records, options):
        """Apply --only and --since. Returns (selected, skipped-with-reasons)."""
        selected, skipped = records, []

        if options['only']:
            wanted = set(options['only'])
            selected = [r for r in selected if r['slug'] in wanted]
            for missing in sorted(wanted - {r['slug'] for r in selected}):
                skipped.append((missing, 'named in --only but not in the export'))

        if options['since']:
            try:
                cutoff = datetime.strptime(options['since'], '%Y-%m-%d').date()
            except ValueError:
                raise CommandError('--since must be YYYY-MM-DD')
            kept = []
            for record in selected:
                stamp = record.get('updated_at') or record.get('created_at')
                # No timestamp at all: import it rather than drop it. A delta
                # that silently skips a record is worse than one that does a
                # little redundant work, and the import is idempotent anyway.
                if not stamp or datetime.fromisoformat(stamp).date() >= cutoff:
                    kept.append(record)
                else:
                    skipped.append((record['slug'], f'unchanged since {options["since"]}'))
            selected = kept

        return selected, skipped

    def _import_one(self, record, known_slugs, media_root, stats, report, options):
        existing = self._find_existing(record)

        if existing and not options['update_existing']:
            stats.skipped.append((record['slug'], 'already imported (--no-update-existing)'))
            return

        body, link_report = rewrite_body(
            record.get('content', ''),
            slug=record['slug'],
            known_slugs=known_slugs,
            legacy_path=record.get('legacy_path'),
        )
        report.merge(link_report)

        # Rule 6 lifted the article's own headline block out of the body. Those
        # values are set here rather than in the rewriter, which only ever
        # returns HTML — and only where the field is empty, so an editor who has
        # since written a better meta title keeps it through a re-import.
        extracted = link_report.extracted

        fields = {
            'title': record['title'],
            'slug': record['slug'],
            'summary': record.get('excerpt', ''),
            'body': body,
            'body_source': record.get('content', ''),   # untouched
            'author_name': record.get('author_name') or 'Haresign',
            'status': (Article.STATUS_PUBLISHED if record.get('is_published')
                       else Article.STATUS_DRAFT),
            'published_at': self._published_at(record),
            'legacy_id': record.get('legacy_id'),
            'legacy_path': record.get('legacy_path', ''),
        }
        # Only when it is *more* descriptive than the title. These articles are
        # live on haresign.net with the title as their <title>, and swapping in a
        # shorter headline would make 21 search results worse to fix a layout
        # duplicate. Where it is not taken it stays in body_source.
        headline = extracted.get('meta_title', '')
        if (headline and len(headline) > len(record['title'])
                and not (existing and existing.meta_title)):
            fields['meta_title'] = headline
            self.meta_titles_taken += 1
        if extracted.get('kicker') and not (existing and existing.kicker):
            fields['kicker'] = extracted['kicker']

        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.save()
            article, created = existing, False
        else:
            article = Article.objects.create(**fields)
            created = True

        stats.created += created
        stats.updated += not created
        if article.status == Article.STATUS_PUBLISHED:
            stats.published += 1
        elif article.status == Article.STATUS_DRAFT:
            stats.draft += 1
        if article.published_at and article.published_at > timezone.now():
            stats.future_dated += 1

        self._set_tags(article, record, stats)
        self._copy_hero(article, record, media_root, stats, options['dry_run'])

        audit = audit_body(body)
        stats.inline_images += audit['images']
        stats.images_without_alt += audit['images_without_alt']
        stats.tables += audit['tables']
        stats.form_controls += audit['forms']

        self.stdout.write(f'  {"+" if created else "~"} {article.slug}')

    def _find_existing(self, record):
        """legacy_id first, slug second.

        Matching on the source pk means a slug corrected on either side updates
        the same article rather than creating a second one. The slug fallback is
        for rows imported before `legacy_id` existed.
        """
        legacy_id = record.get('legacy_id')
        if legacy_id is not None:
            found = Article.objects.filter(legacy_id=legacy_id).first()
            if found:
                return found
        return Article.objects.filter(slug=record['slug']).first()

    def _published_at(self, record):
        """published_date is a DateField; Insights stores a datetime.

        09:00 local is arbitrary but consistent. The legacy data carries no time,
        so something has to be chosen — and midnight is the one choice that can
        shift an article's apparent date across a timezone boundary.
        """
        raw = record.get('published_date')
        if not raw:
            return None
        naive = datetime.combine(
            datetime.fromisoformat(raw).date(), time(9, 0))
        return timezone.make_aware(naive)

    def _set_tags(self, article, record, stats):
        tags = []
        for entry in record.get('tags', []):
            tag, created = Tag.objects.get_or_create(
                name=entry['name'], defaults={'slug': entry.get('slug', '')})
            stats.tags_created += created
            tags.append(tag)
        article.tags.set(tags)

    def _copy_hero(self, article, record, media_root, stats, dry_run=False):
        """Copy the hero image into this site's own media.

        Re-saved through the ImageField rather than referenced in place, so the
        destination genuinely owns the file and an imported article does not
        depend on the monolith's volume still being mounted. The bytes are copied
        unchanged — no resizing, no recompression.
        """
        name = record.get('hero_image')
        if not name:
            return
        if not media_root:
            stats.media_missing.append((article.slug, name, 'no --media-root given'))
            return

        # hero_image is stored as "blog/images/x.png" relative to the monolith's
        # MEDIA_ROOT, and --media-root points at a copy of that tree.
        source = media_root / name
        if not source.exists():
            stats.media_missing.append((article.slug, name, 'file not found'))
            return

        # Already copied: skip.
        #
        # Matched on the source *stem*, not the whole filename, and this is the
        # whole point: Django's storage appends a random suffix when a name is
        # taken, so "hero.png" is stored as "hero_be1J5P7.png". Comparing full
        # names never matches, so every re-run copied every image again — three
        # runs produced 214 files for 67 articles before this was caught. The
        # row-level import was idempotent; the file-level one was not.
        if article.featured_image:
            stored = Path(article.featured_image.name).name
            if stored == Path(name).name or stored.startswith(Path(name).stem):
                stats.hero_kept += 1
                return

        if dry_run:
            # Same reason as the inline trees: a rolled-back row does not
            # un-write the file ImageField.save() would have put on the volume.
            stats.hero_copied += 1
            return

        with source.open('rb') as handle:
            article.featured_image.save(Path(name).name, File(handle), save=True)
        stats.hero_copied += 1

    def _copy_inline_media(self, media_root, plan_only=False):
        """Copy the upload trees that article bodies reference inline.

        The rewriter points inline images at /media/insights/legacy/<path>; this
        puts the files there. Copied rather than linked, and never recompressed.

        `plan_only` counts what would be copied and writes nothing — the dry run
        needs that, because a database rollback does not un-copy a file.
        """
        from django.conf import settings
        import shutil

        destination_root = Path(settings.MEDIA_ROOT) / LEGACY_MEDIA_SUBDIR
        copied = 0
        for tree in ('blog', 'library'):
            source = media_root / tree
            if not source.exists():
                continue
            for path in source.rglob('*'):
                if not path.is_file():
                    continue
                target = destination_root / tree / path.relative_to(source)
                if target.exists() and target.stat().st_size == path.stat().st_size:
                    continue
                copied += 1
                if plan_only:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        return copied

    # -- reporting ----------------------------------------------------------

    def _report(self, stats, report, options):
        out = self.stdout
        style = self.style

        out.write('')
        out.write(style.MIGRATE_HEADING('Articles'))
        out.write(f'  Legacy article count : {stats.source_total}')
        out.write(f'  Imported (created)   : {stats.created}')
        out.write(f'  Imported (updated)   : {stats.updated}')
        out.write(f'  Published            : {stats.published}')
        out.write(f'  Draft                : {stats.draft}')
        out.write(f'  Archived             : 0   (legacy has no archived state)')
        out.write(f'  Future-dated         : {stats.future_dated}')
        out.write(f'  Categories           : 0   (legacy has none; not invented)')
        out.write(f'  Tags created         : {stats.tags_created}')
        verb = 'would copy' if options['dry_run'] else 'copied'
        out.write(f'  Featured images      : {stats.hero_copied} {verb}, '
                  f'{stats.hero_kept} already present')
        out.write(f'  Inline media files   : {stats.inline_files} {verb}')
        out.write(f'  Inline image refs    : {stats.inline_images}')
        out.write(f'  Tables in bodies     : {stats.tables}')
        out.write(f'  Skipped              : {len(stats.skipped)}')

        for slug, reason in stats.skipped:
            out.write(style.WARNING(f'    - {slug}: {reason}'))

        out.write('')
        out.write(style.MIGRATE_HEADING('Content rewriting'))
        out.write(f'  Media URLs rewritten : {len(report.media_rewrites)}')
        out.write(f'  Article links moved  : {len(report.article_links)}  (/blog/x/ -> /insights/x/)')
        out.write(f'  Dead links repaired  : {len(report.repaired_paths)}  '
                  f'(404 on haresign.net today; final segment named a known article)')
        out.write(f'  Dead controls removed: {report.removed_controls}')
        out.write(f'  Panels unhidden      : {report.unhidden_panels}')
        out.write(f'  Headlines lifted     : {report.lifted_headlines}  '
                  f'(duplicate body headline removed; the page owns the one h1)')
        out.write(f'    -> used as meta_title: {self.meta_titles_taken}  '
                  f'(only where longer than the title)')
        out.write(f'  Kickers lifted       : {report.lifted_kickers}  '
                  f'(body badge -> kicker)')
        out.write(f'  Later h1 -> h2       : {report.demoted_headings}')
        out.write(f'  Tool links left alone: {len(report.tool_links)}  (Intelligence owns these)')
        out.write(f'  External links       : {len(set(u for _, u in report.external_links))} unique')

        if stats.media_missing:
            out.write('')
            out.write(style.ERROR(f'  Missing media ({len(stats.media_missing)}):'))
            for slug, name, why in stats.media_missing:
                out.write(style.ERROR(f'    - {slug}: {name} ({why})'))

        if stats.images_without_alt:
            out.write(style.WARNING(
                f'  {stats.images_without_alt} inline image(s) have no alt text. '
                f'That is how they were written; it is reported, not invented.'))
        if stats.form_controls:
            out.write(style.WARNING(
                f'  {stats.form_controls} form control(s) in article bodies '
                f'(printable checklists in the source). They render but do '
                f'nothing — no JavaScript here reads them.'))

        if report.unresolved_internal:
            unique = sorted({path for _, path in report.unresolved_internal})
            out.write('')
            out.write(style.WARNING(
                f'  {len(unique)} legacy path(s) need a redirect decision at '
                f'cutover — left unchanged rather than guessed:'))
            for path in unique[:20]:
                out.write(f'    {path}')
            if len(unique) > 20:
                out.write(f'    … and {len(unique) - 20} more')

        if options['link_report']:
            self._write_link_report(report, options['link_report'])
            out.write('')
            out.write(style.SUCCESS(f'Link report written to {options["link_report"]}'))

    def _write_link_report(self, report, path):
        payload = {
            'article_links': [{'from': a, 'to': b} for a, b in report.article_links],
            'unresolved_internal': [
                {'from': a, 'path': b} for a, b in report.unresolved_internal],
            'tool_links': [{'from': a, 'url': b} for a, b in report.tool_links],
            'external_links': sorted({url for _, url in report.external_links}),
            'media_rewrites': [
                {'from': a, 'old': b, 'new': c} for a, b, c in report.media_rewrites],
            'repaired_paths': [
                {'from': a, 'dead_path': b} for a, b in report.repaired_paths],
            'removed_controls': report.removed_controls,
            'unhidden_panels': report.unhidden_panels,
        }
        Path(path).write_text(json.dumps(payload, indent=2), encoding='utf-8')


class _Stats:
    def __init__(self, source_total, skipped):
        self.source_total = source_total
        self.skipped = list(skipped)
        self.created = self.updated = 0
        self.published = self.draft = self.future_dated = 0
        self.tags_created = 0
        self.hero_copied = self.hero_kept = 0
        self.inline_files = self.inline_images = 0
        self.images_without_alt = self.tables = self.form_controls = 0
        self.media_missing = []


class _Rollback(Exception):
    """Signals a deliberate dry-run rollback, not a failure."""
