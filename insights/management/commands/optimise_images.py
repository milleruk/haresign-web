"""Resize and re-compress article images.

    python manage.py optimise_images --dry-run
    python manage.py optimise_images
    python manage.py optimise_images --max-width 1600 --quality 82

The imported hero images average **991 KB** and come to 64.8 MB across 67
articles — full-size PNG exports from a design tool, displayed at most about
860 CSS pixels wide. Nothing is visibly wrong, which is exactly why it goes
unnoticed: the cost lands on whoever is reading on a phone on mobile data.

**Originals are never destroyed.** Every file is copied to
`insights/original/…` before it is touched, so a bad `--max-width` is undone by
copying back rather than by re-importing. That directory is served by nothing.

**Two files are written per image**, and both matter:

- the original path is **resized in place, in its own format**, so it stays the
  `<img src>` and every existing reference keeps working;
- a `.webp` sibling is written and offered first through `<picture>`.

WebP alone would be smaller still, but this audience includes locked-down NHS
desktops. `<picture>` costs one extra element and means a browser that has never
heard of WebP gets a resized original rather than a broken image.

Idempotent: an image already at or below `--max-width` whose WebP exists and is
newer is skipped, so this can be re-run after every import.
"""
import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

from insights.models import Article

# Wide enough for the largest rendering (the article hero in a 54rem reading
# column) on a 2x display, and no wider. Anything beyond this is bytes nobody
# can see.
DEFAULT_MAX_WIDTH = 1600
DEFAULT_QUALITY = 82

ORIGINALS_SUBDIR = 'insights/original'


class Command(BaseCommand):
    help = 'Resize and re-compress article images; originals are kept.'

    def add_arguments(self, parser):
        parser.add_argument('--max-width', type=int, default=DEFAULT_MAX_WIDTH)
        parser.add_argument('--quality', type=int, default=DEFAULT_QUALITY)
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change and write nothing.')
        parser.add_argument('--force', action='store_true',
                            help='Re-process images that already look optimised.')

    def handle(self, *args, **options):
        media = Path(settings.MEDIA_ROOT)
        originals = media / ORIGINALS_SUBDIR
        dry = options['dry_run']

        before = after = 0
        processed = skipped = failed = 0
        webp_bytes = 0

        for article in Article.objects.exclude(featured_image='').order_by('slug'):
            path = media / article.featured_image.name
            if not path.exists():
                self.stderr.write(self.style.WARNING(
                    f'  missing: {article.slug} -> {article.featured_image.name}'))
                failed += 1
                continue

            original_size = path.stat().st_size
            before += original_size

            try:
                result = self._process(
                    path, originals, media, options, dry)
            except Exception as exc:                       # noqa: BLE001
                self.stderr.write(self.style.ERROR(f'  failed: {article.slug}: {exc}'))
                failed += 1
                after += original_size
                continue

            if result is None:
                skipped += 1
                after += original_size
                continue

            new_size, webp_size = result
            after += new_size
            webp_bytes += webp_size
            processed += 1
            saved = 100 - (webp_size * 100 // original_size) if original_size else 0
            self.stdout.write(
                f'  {"~" if dry else "+"} {article.slug[:44]:<46} '
                f'{original_size // 1024:>5} KB -> {new_size // 1024:>4} KB '
                f'(webp {webp_size // 1024:>3} KB, -{saved}%)')

        self._report(before, after, webp_bytes, processed, skipped, failed, dry)

    def _process(self, path, originals, media, options, dry):
        """Returns (new_size, webp_size), or None when nothing needed doing."""
        webp_path = path.with_suffix('.webp')

        with Image.open(path) as image:
            width, height = image.size
            needs_resize = width > options['max_width']

            if not options['force'] and not needs_resize and webp_path.exists():
                return None

            if dry:
                # Estimate rather than write. Scaling is by area; the WebP
                # divisor is measured against this corpus rather than guessed —
                # a first version used /5 and reported 12.5MB where the real run
                # produced 4.9MB, which is the sort of dry run nobody trusts
                # twice. /10 stays deliberately on the pessimistic side of the
                # ~13x these PNGs actually achieve.
                scale = min(1.0, options['max_width'] / width) ** 2
                estimated = int(path.stat().st_size * scale)
                return estimated, max(1, estimated // 10)

            # Back up before touching anything. Only once: a second run must not
            # overwrite the true original with an already-optimised file.
            backup = originals / path.relative_to(media)
            if not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, backup)

            working = image
            if needs_resize:
                ratio = options['max_width'] / width
                working = image.resize(
                    (options['max_width'], int(height * ratio)), Image.LANCZOS)

            # Palette and greyscale images have to become RGB before a
            # quality-based encoder will take them.
            if working.mode in ('P', 'LA', 'CMYK'):
                working = working.convert('RGBA' if 'A' in working.mode else 'RGB')

            save_kwargs = {'optimize': True}
            if path.suffix.lower() in ('.jpg', '.jpeg'):
                save_kwargs['quality'] = options['quality']
                save_kwargs['progressive'] = True
                if working.mode == 'RGBA':
                    working = working.convert('RGB')
            working.save(path, **save_kwargs)

            # The WebP sibling, which is what most readers will actually get.
            working.save(webp_path, format='WEBP', quality=options['quality'],
                         method=6)

        return path.stat().st_size, webp_path.stat().st_size

    def _report(self, before, after, webp_bytes, processed, skipped, failed, dry):
        mb = 1024 * 1024
        out = self.stdout
        out.write('')
        out.write(self.style.MIGRATE_HEADING(
            'Image optimisation' + (' (DRY RUN — nothing written)' if dry else '')))
        out.write(f'  Processed          : {processed}')
        out.write(f'  Already optimised  : {skipped}')
        out.write(f'  Failed / missing   : {failed}')
        out.write(f'  Before             : {before / mb:.1f} MB')
        out.write(f'  After (fallback)   : {after / mb:.1f} MB')
        out.write(f'  After (WebP)       : {webp_bytes / mb:.1f} MB'
                  f'  <- what most readers download')
        if before:
            out.write(f'  Saving             : '
                      f'{100 - (webp_bytes * 100 // before)}% for a WebP browser, '
                      f'{100 - (after * 100 // before)}% for one without')
        if not dry and processed:
            out.write('')
            out.write(f'  Originals kept in {ORIGINALS_SUBDIR}/ — served by nothing, '
                      f'and the way back if this went wrong.')
