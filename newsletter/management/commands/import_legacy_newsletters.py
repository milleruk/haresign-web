"""One-way import of the monolith's newsletter issues.

Reads the JSON produced by `tools/export_from_monolith.py`. Like every importer
here it consumes a file, never a database connection.

    python manage.py import_legacy_newsletters _migration/legacy_newsletters.json --dry-run
    python manage.py import_legacy_newsletters _migration/legacy_newsletters.json

Mapping:

    legacy newsletter.Newsletter  ->  newsletter.Issue
    id            ->  legacy_id       (match key)
    title         ->  title
    slug          ->  slug
    subject       ->  subject
    intro         ->  body_source (verbatim) + body_html (rewritten)
    sent_at       ->  sent_at         (null = draft; drafts stay out of the archive)
    send_count    ->  send_count
    created_at    ->  created_at      (the issue's own date, not the import's)
    updated_at    ->  updated_at
    blog_posts    ->  articles        (resolved by slug)

`documents` is deliberately not imported. Those are `SharedDocument` rows behind
the monolith's permission-checked download view — client material rather than
public editorial content, and not this repository's to hold. The count is
reported so their absence is visible rather than silent.

**This importer cannot send anything.** It writes rows to an archive.
"""
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from insights.importing import rewrite_body
from insights.models import Article
from newsletter.models import Issue


class Command(BaseCommand):
    help = 'Import monolith newsletter issues from a JSON export (one-way, idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('export', help='Path to legacy_newsletters.json.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change, then roll back.')
        parser.add_argument('--update-existing', action='store_true', default=True)
        parser.add_argument('--no-update-existing', dest='update_existing',
                            action='store_false')
        parser.add_argument(
            '--since', metavar='YYYY-MM-DD',
            help='Only issues whose source updated_at is on or after this date.')

    def handle(self, *args, **options):
        path = Path(options['export'])
        if not path.exists():
            raise CommandError(f'Export file not found: {path}')
        payload = json.loads(path.read_text(encoding='utf-8'))
        if 'newsletters' not in payload:
            raise CommandError('No "newsletters" key — wrong export file?')

        records = payload['newsletters']
        source_total = len(records)
        skipped = []

        if options['since']:
            cutoff = datetime.strptime(options['since'], '%Y-%m-%d').date()
            kept = []
            for record in records:
                stamp = record.get('updated_at') or record.get('created_at')
                if not stamp or datetime.fromisoformat(stamp).date() >= cutoff:
                    kept.append(record)
                else:
                    skipped.append((record['slug'], f'unchanged since {options["since"]}'))
            records = kept

        known_slugs = set(Article.objects.values_list('slug', flat=True))
        created = updated = sent = draft = linked = orphan_links = documents = 0

        try:
            with transaction.atomic():
                for record in records:
                    existing = (
                        Issue.objects.filter(legacy_id=record['legacy_id']).first()
                        or Issue.objects.filter(slug=record['slug']).first()
                    )
                    if existing and not options['update_existing']:
                        skipped.append((record['slug'], 'already imported'))
                        continue

                    body, _ = rewrite_body(
                        record.get('intro', ''),
                        slug=record['slug'],
                        known_slugs=known_slugs,
                        legacy_path=record.get('legacy_path'),
                    )

                    fields = {
                        'title': record['title'],
                        'slug': record['slug'],
                        'subject': record.get('subject', ''),
                        'body_html': body,
                        'body_source': record.get('intro', ''),
                        'sent_at': self._parse(record.get('sent_at')),
                        'send_count': record.get('send_count') or 0,
                        'created_at': self._parse(record.get('created_at')),
                        'updated_at': self._parse(record.get('updated_at')),
                        'legacy_id': record.get('legacy_id'),
                        'legacy_path': record.get('legacy_path', ''),
                    }

                    if existing:
                        for key, value in fields.items():
                            if value is not None or key in ('sent_at',):
                                setattr(existing, key, value)
                        existing.save()
                        issue, was_created = existing, False
                    else:
                        issue = Issue.objects.create(**fields)
                        was_created = True

                    created += was_created
                    updated += not was_created
                    sent += bool(issue.sent_at)
                    draft += not issue.sent_at
                    documents += record.get('document_count') or 0

                    # Resolved by slug. An issue that named an article we are not
                    # importing simply keeps fewer links — never a dangling FK,
                    # and never a guess at which article was meant.
                    articles = list(
                        Article.objects.filter(slug__in=record.get('article_slugs', [])))
                    issue.articles.set(articles)
                    linked += len(articles)
                    orphan_links += len(record.get('article_slugs', [])) - len(articles)

                    self.stdout.write(f'  {"+" if was_created else "~"} {issue.slug}')

                if options['dry_run']:
                    raise _Rollback()
        except _Rollback:
            self.stdout.write(self.style.WARNING('DRY RUN — everything rolled back.'))

        out = self.stdout
        out.write('')
        out.write(self.style.MIGRATE_HEADING('Newsletter issues'))
        out.write(f'  Legacy issue count : {source_total}')
        out.write(f'  Imported (created) : {created}')
        out.write(f'  Imported (updated) : {updated}')
        out.write(f'  Sent (public)      : {sent}')
        out.write(f'  Draft (not public) : {draft}')
        out.write(f'  Article links made : {linked}')
        out.write(f'  Skipped            : {len(skipped)}')
        for slug, reason in skipped:
            out.write(self.style.WARNING(f'    - {slug}: {reason}'))
        if orphan_links:
            out.write(self.style.WARNING(
                f'  {orphan_links} article reference(s) could not be resolved — '
                f'import articles first, then re-run.'))
        if documents:
            out.write(self.style.WARNING(
                f'  {documents} attached document(s) NOT imported: they are '
                f'permission-checked client material in the monolith, not public '
                f'editorial content.'))

    def _parse(self, value):
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            from django.utils import timezone
            parsed = timezone.make_aware(parsed)
        return parsed


class _Rollback(Exception):
    """Signals a deliberate dry-run rollback, not a failure."""
