"""Export the list as JSON — the only integration point with anything else.

This is the same shape as `import_legacy_articles` reads, and for the same
reason: a file crosses the boundary, a database connection does not. Whatever
does the sending imports this; nothing reaches into this database, and this
application reaches into nobody else's.

Field names match `website.NewsletterSubscriber` in the monolith exactly, so a
merge needs no mapping. `source` is extra and is ignored by anything that does
not know about it.

    python manage.py export_subscribers --output subscribers.json
    python manage.py export_subscribers --all          # include unsubscribed
"""
import json

from django.core.management.base import BaseCommand

from newsletter.models import Subscriber


class Command(BaseCommand):
    help = 'Export newsletter subscribers as JSON for a one-way merge.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            help='File to write. Defaults to stdout.',
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Include unsubscribed rows. Off by default: exporting people '
                 'who have opted out is how they get mailed again.',
        )

    def handle(self, *args, **options):
        rows = Subscriber.objects.all()
        if not options['all']:
            rows = rows.filter(active=True)

        payload = [
            {
                'email': row.email,
                'name': row.name,
                'subscribed_at': row.subscribed_at.isoformat(),
                'active': row.active,
                'unsubscribe_token': str(row.unsubscribe_token),
                'source': row.source,
            }
            for row in rows.order_by('subscribed_at')
        ]

        text = json.dumps(payload, indent=2)
        if options['output']:
            with open(options['output'], 'w', encoding='utf-8') as handle:
                handle.write(text)
            self.stdout.write(self.style.SUCCESS(
                f'Exported {len(payload)} subscriber(s) to {options["output"]}'))
        else:
            # self.stdout, not sys.stdout: the command's own stream is what
            # `call_command(stdout=…)` redirects, and writing past it makes the
            # output uncapturable by anything calling this programmatically.
            self.stdout.write(text)
