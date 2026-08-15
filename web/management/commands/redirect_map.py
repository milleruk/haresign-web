"""Build the legacy → new URL map for the production cutover.

    python manage.py redirect_map                       # CSV to stdout
    python manage.py redirect_map --output redirects.csv
    python manage.py redirect_map --format nginx

**It generates nothing to deploy today.** Beta is not production and these
redirects belong in the monolith's URLconf or at Traefik, once the domain
actually moves. What this does is make the map a derived artefact rather than a
hand-maintained list that drifts from the content — every row comes from a
`legacy_path` recorded at import.

Rows come from three places:

1. **Articles.** `/blog/<slug>/ → /insights/<slug>/`. Slugs were imported
   unchanged, so this is one-to-one and complete.
2. **Newsletter issues.** `/newsletter/archive/<slug>/ → /newsletter/<slug>/`,
   for sent issues only — a draft has no public page on either side.
3. **Index pages**, which have no legacy_path to read and are listed explicitly.

Anything an article *links to* that has no destination here is deliberately not
in this map: see `import_legacy_articles --link-report`, which lists them. A
redirect invented for a path nobody has decided about is worse than a 404,
because it is a wrong answer given confidently.
"""
import csv
import sys
from pathlib import Path

from django.core.management.base import BaseCommand

from insights.models import Article
from newsletter.models import Issue

# Paths with no legacy_path to read from a row. Listed rather than derived,
# because they are decisions about information architecture rather than data.
INDEX_REDIRECTS = [
    ('/blog/', '/insights/'),
    ('/newsletter/archive/', '/newsletter/'),
    # The monolith's own footer links "Terms of Use" at the privacy policy —
    # a bug there, and the reason /terms/ had no source to adapt.
    ('/privacy-policy/', '/privacy/'),
    ('/cookie-policy/', '/cookies/'),
]


class Command(BaseCommand):
    help = 'Generate the legacy -> new redirect map for cutover.'

    def add_arguments(self, parser):
        parser.add_argument('--output', help='Write here instead of stdout.')
        parser.add_argument('--format', choices=['csv', 'nginx', 'traefik'],
                            default='csv')

    def handle(self, *args, **options):
        rows = list(INDEX_REDIRECTS)

        for article in Article.objects.exclude(legacy_path='').order_by('legacy_path'):
            rows.append((article.legacy_path, article.get_absolute_url()))

        # Sent issues only: a draft has no public page at either end, so a
        # redirect to it would 404 on arrival.
        for issue in Issue.objects.public().exclude(legacy_path='').order_by('legacy_path'):
            rows.append((issue.legacy_path, issue.get_absolute_url()))

        text = self._render(rows, options['format'])

        if options['output']:
            Path(options['output']).write_text(text, encoding='utf-8')
            self.stderr.write(self.style.SUCCESS(
                f'{len(rows)} redirect(s) written to {options["output"]}'))
        else:
            sys.stdout.write(text)

    def _render(self, rows, fmt):
        if fmt == 'csv':
            import io
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(['legacy_path', 'new_path'])
            writer.writerows(rows)
            return buffer.getvalue()

        if fmt == 'nginx':
            # 301, because these moves are permanent and search engines should
            # transfer the ranking rather than keep both.
            return ''.join(
                f'location = {old} {{ return 301 {new}; }}\n' for old, new in rows)

        # Traefik file-provider middleware. One regex per row rather than a
        # single clever pattern: the map is generated, so there is nothing to be
        # gained by making it compact and something to lose in readability.
        lines = ['http:', '  middlewares:']
        for index, (old, new) in enumerate(rows):
            lines += [
                f'    haresign-redirect-{index}:',
                '      redirectRegex:',
                f'        regex: "^https?://[^/]+{old}$"',
                f'        replacement: "https://haresign.net{new}"',
                '        permanent: true',
            ]
        return '\n'.join(lines) + '\n'
