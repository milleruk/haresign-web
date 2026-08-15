"""One-way import of the monolith's newsletter subscribers.

    python manage.py import_legacy_subscribers _migration/legacy_subscribers.json --dry-run
    python manage.py import_legacy_subscribers _migration/legacy_subscribers.json

The export file is **personal data** — a list of real email addresses. It is
covered by .gitignore, and it should be deleted once the import is verified.

Three rules govern this importer, and only the first is obvious.

**1. An unsubscribe is a fact, and it survives.** Every row is imported,
including everyone who has opted out. Importing only the active list is precisely
how somebody who unsubscribed gets mailed again — and this command will never
flip `active` from False to True. If the source says active and the destination
says unsubscribed, the destination wins and the row is reported: somebody may
have unsubscribed here after the export was taken, and the safe direction of that
disagreement is obvious.

**2. Email comparison is case-insensitive.** `Person@nhs.net` and
`person@nhs.net` are one person with one inbox. The destination normalises to
lower case on the way in, so a source that never did cannot create two rows.

**3. Nothing is invented.** The monolith records no unsubscribe date, no double
opt-in and no consent evidence — `active` is the whole of it. Those fields stay
empty rather than being filled with the date of the migration, which would
manufacture a consent record that does not exist.

Importing subscribers does not make this application able to email them. It
cannot: there is no SMTP configuration, no queue and no send path anywhere in
this repository. They are here for migration validation and for eventual
ownership.
"""
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from newsletter.models import Subscriber


class Command(BaseCommand):
    help = 'Import monolith newsletter subscribers from a JSON export (one-way).'

    def add_arguments(self, parser):
        parser.add_argument('export', help='Path to legacy_subscribers.json.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change, then roll back.')
        parser.add_argument('--update-existing', action='store_true', default=True)
        parser.add_argument('--no-update-existing', dest='update_existing',
                            action='store_false')
        parser.add_argument(
            '--since', metavar='YYYY-MM-DD',
            help='Only rows whose subscribed_at is on or after this date. Use '
                 'with care: it is right for a delta of *new* subscribers, and '
                 'wrong if somebody has unsubscribed in the meantime, because '
                 'their row will not be revisited. A full re-run is safer.')

    def handle(self, *args, **options):
        path = Path(options['export'])
        if not path.exists():
            raise CommandError(f'Export file not found: {path}')
        payload = json.loads(path.read_text(encoding='utf-8'))
        if 'subscribers' not in payload:
            raise CommandError('No "subscribers" key — wrong export file?')

        records = payload['subscribers']
        source_total = len(records)
        source_active = sum(1 for r in records if r.get('active'))
        source_inactive = source_total - source_active

        stats = _Stats()

        if options['since']:
            cutoff = datetime.strptime(options['since'], '%Y-%m-%d').date()
            kept = []
            for record in records:
                stamp = record.get('subscribed_at')
                if not stamp or datetime.fromisoformat(stamp).date() >= cutoff:
                    kept.append(record)
                else:
                    stats.filtered_out += 1
            records = kept

        # Duplicate detection runs on the *source*, before anything is written,
        # so an anomaly in the export is reported as an anomaly rather than
        # quietly resolved by whichever row happened to be imported last.
        seen = Counter(r['email'].strip().lower() for r in records if r.get('email'))
        stats.source_duplicates = [e for e, n in seen.items() if n > 1]

        try:
            with transaction.atomic():
                for record in records:
                    self._import_one(record, stats, options)
                if options['dry_run']:
                    raise _Rollback()
        except _Rollback:
            self.stdout.write(self.style.WARNING('DRY RUN — everything rolled back.'))

        self._report(stats, source_total, source_active, source_inactive)

    def _import_one(self, record, stats, options):
        email = (record.get('email') or '').strip().lower()
        if not email:
            stats.invalid.append(('(blank)', 'no email address'))
            return
        try:
            validate_email(email)
        except ValidationError:
            stats.invalid.append((email, 'not a valid email address'))
            return

        token = record.get('unsubscribe_token')
        if not token:
            stats.missing_tokens += 1

        existing = (
            Subscriber.objects.filter(legacy_id=record.get('legacy_id')).first()
            if record.get('legacy_id') is not None else None
        ) or Subscriber.objects.filter(email__iexact=email).first()

        if existing and not options['update_existing']:
            stats.left_alone += 1
            return

        source_active = bool(record.get('active'))

        if existing:
            # Rule 1. A local unsubscribe outranks a source that still says
            # active — the export may simply predate it.
            if not existing.active and source_active:
                stats.kept_local_unsubscribe.append(email)
            elif existing.active and not source_active:
                existing.active = False
                stats.deactivated += 1

            if record.get('legacy_id') is not None and existing.legacy_id is None:
                existing.legacy_id = record['legacy_id']
            if not existing.name and record.get('name'):
                existing.name = record['name']
            if not existing.source:
                existing.source = 'monolith'
            existing.save()
            stats.updated += 1
            return

        fields = {
            'email': email,
            'name': record.get('name') or '',
            'active': source_active,
            'source': 'monolith',
            'legacy_id': record.get('legacy_id'),
            # No unsubscribed_at: the source has none, and stamping the
            # migration date would invent a record of when somebody left.
        }
        if token:
            # Carried over so unsubscribe links in already-sent emails keep
            # working after cutover. This is the single most important field in
            # the whole export.
            fields['unsubscribe_token'] = token

        subscriber = Subscriber(**fields)
        subscriber.save()

        # subscribed_at is auto_now_add, so it has to be written afterwards or
        # every migrated row would claim to have subscribed on migration day.
        stamp = record.get('subscribed_at')
        if stamp:
            parsed = datetime.fromisoformat(stamp)
            if parsed.tzinfo is None:
                parsed = timezone.make_aware(parsed)
            Subscriber.objects.filter(pk=subscriber.pk).update(subscribed_at=parsed)

        stats.created += 1
        stats.imported_active += source_active
        stats.imported_inactive += not source_active

    def _report(self, stats, source_total, source_active, source_inactive):
        out = self.stdout
        out.write('')
        out.write(self.style.MIGRATE_HEADING('Subscribers'))
        out.write(f'  Legacy total subscribers   : {source_total}')
        out.write(f'  Legacy active              : {source_active}')
        out.write(f'  Legacy unsubscribed        : {source_inactive}')
        out.write('')

        total = Subscriber.objects.count()
        active = Subscriber.objects.filter(active=True).count()
        out.write(f'  Imported total (this run)  : {stats.created} created, '
                  f'{stats.updated} updated')
        out.write(f'  Destination total          : {total}')
        out.write(f'  Destination active         : {active}')
        out.write(f'  Destination unsubscribed   : {total - active}')
        out.write(f'  Duplicate emails in source : {len(stats.source_duplicates)}')
        out.write(f'  Invalid emails encountered : {len(stats.invalid)}')
        out.write(f'  Missing tokens             : {stats.missing_tokens}')
        out.write(f'  Deactivated to match source: {stats.deactivated}')
        out.write(f'  Local unsubscribes kept    : {len(stats.kept_local_unsubscribe)}')
        if stats.filtered_out:
            out.write(f'  Filtered out by --since    : {stats.filtered_out}')

        for email in stats.source_duplicates:
            out.write(self.style.WARNING(f'    duplicate in source: {email}'))
        for email, why in stats.invalid:
            out.write(self.style.ERROR(f'    invalid: {email} ({why})'))
        for email in stats.kept_local_unsubscribe:
            out.write(self.style.WARNING(
                f'    kept local unsubscribe (source says active): {email}'))

        if stats.missing_tokens:
            out.write(self.style.WARNING(
                '  Rows without a token got a fresh one. Unsubscribe links in '
                'emails already sent to them will not match.'))

        out.write('')
        out.write(self.style.SUCCESS(
            'Sending remains disabled in this application. These rows exist for '
            'migration validation and eventual ownership — nothing here can mail '
            'them.'))


class _Stats:
    def __init__(self):
        self.created = self.updated = self.left_alone = 0
        self.imported_active = self.imported_inactive = 0
        self.deactivated = self.missing_tokens = self.filtered_out = 0
        self.invalid = []
        self.source_duplicates = []
        self.kept_local_unsubscribe = []


class _Rollback(Exception):
    """Signals a deliberate dry-run rollback, not a failure."""
