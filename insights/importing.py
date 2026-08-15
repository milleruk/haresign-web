"""Deterministic rewriting of legacy article HTML.

Separated from the management command so the rules can be tested directly on
awkward real markup, and so a rule change is reviewable as a rule change rather
than buried in an import loop.

**Nothing here is lossy.** `Article.body_source` keeps the monolith's HTML
byte-for-byte; every transform below runs on the way to `Article.body`. If a rule
turns out to be wrong, the fix is to change the rule and re-import — the original
never left.

Five rules, each with a reason:

1. **Relative URLs become absolute.** TinyMCE stored `../../../../uploads/x.png`,
   which only resolves correctly at the URL depth it happened to be authored at.
   Resolved against the article's own legacy path, so the result is what the link
   meant on haresign.net rather than what it would accidentally mean here.

2. **Legacy upload paths point at media this site owns.** `/uploads/…` becomes
   `/media/insights/legacy/…`, matching where `import_legacy_articles --media-root`
   copies the files. An imported article must not depend on the monolith's
   container still being up.

3. **Article-to-article links follow the article.** `/blog/<slug>/` becomes
   `/insights/<slug>/` — but **only when that slug is in the import set**. A link
   to something not being migrated is left alone and reported, because guessing
   at a destination is how a live link becomes a 404.

   The same rule repairs links that rule 1 resolved to a path that never
   existed. TinyMCE wrote some of these one `../` too deep, so
   `/articles/<slug>/` and bare `/<slug>/` are **404 on haresign.net today** —
   verified against production, not assumed. Where the final segment is a known
   article slug the author's intent is unambiguous, so it is repointed; where it
   is not, nothing is guessed and the path goes in the report.

4. **Dead Bootstrap controls are removed.** The bodies contain
   `data-bs-toggle="collapse"` buttons. This site loads no Bootstrap JavaScript,
   so they are controls that cannot do anything.

5. **…and what they controlled is unhidden.** Rule 4 alone would be destructive:
   `class="collapse d-lg-block"` means *hidden below 992px*, so removing the
   button while leaving the class would make each article's contents list
   unreachable on a phone. Dropping `collapse` leaves it visible at every width.

6. **A body `<h1>` becomes an `<h2>`.** 22 of the 67 legacy articles open with
   their own `<h1>`, a variant headline written above the body. The page template
   already renders the title as the page's one `<h1>`, so importing them
   unchanged gives every one of those articles two — which is both a duplicated
   headline on screen and a broken document outline for a screen reader.

   Demoted rather than deleted: only six of the 22 repeat the title exactly, and
   the other sixteen are a *different* headline. Removing them would throw away
   editorial writing to fix a structural problem.
"""
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

# Where legacy upload trees are copied to. Mirrors the monolith's own layout
# under one prefix, so `uploads/library/2026/08/1.png` keeps its shape and a file
# can be traced back to its source by eye.
LEGACY_MEDIA_PREFIX = '/media/insights/legacy/'

# Hosts that are the monolith. An absolute link to one of these is an internal
# link wearing a domain name, and is treated as such.
LEGACY_HOSTS = {'haresign.net', 'www.haresign.net'}

_UPLOADS = re.compile(r'^/uploads/(?P<rest>.+)$')
_BLOG = re.compile(r'^/blog/(?P<slug>[^/]+)/?$')


@dataclass
class LinkReport:
    """What the rewriter did, and what a human still has to decide.

    `unresolved_internal` is the one that matters at cutover: links to legacy
    paths that are not articles and so have no destination here yet.
    """
    article_links: list = field(default_factory=list)      # (from_slug, to_slug)
    unresolved_internal: list = field(default_factory=list)  # (from_slug, path)
    tool_links: list = field(default_factory=list)          # (from_slug, url)
    external_links: list = field(default_factory=list)      # (from_slug, url)
    media_rewrites: list = field(default_factory=list)      # (from_slug, old, new)
    repaired_paths: list = field(default_factory=list)      # (from_slug, dead_path)
    removed_controls: int = 0
    unhidden_panels: int = 0
    demoted_headings: int = 0

    def merge(self, other):
        self.article_links += other.article_links
        self.unresolved_internal += other.unresolved_internal
        self.tool_links += other.tool_links
        self.external_links += other.external_links
        self.media_rewrites += other.media_rewrites
        self.repaired_paths += other.repaired_paths
        self.removed_controls += other.removed_controls
        self.unhidden_panels += other.unhidden_panels
        self.demoted_headings += other.demoted_headings


def _absolutise(url, base_path):
    """Resolve a URL against the article's legacy path.

    Returns `(path, is_internal)`. Fragments, mailto: and tel: are returned
    unchanged and flagged not-internal — an in-page anchor is not a link to
    somewhere else, and rewriting one would break the article's own contents list.
    """
    if not url or url.startswith(('#', 'mailto:', 'tel:', 'data:')):
        return url, False

    parsed = urlparse(url)

    if parsed.scheme in ('http', 'https'):
        if parsed.netloc.lower() in LEGACY_HOSTS:
            # An internal link that was written absolutely. Same thing.
            return urlunparse(('', '', parsed.path, '', parsed.query, parsed.fragment)), True
        return url, False

    if parsed.scheme:            # some other scheme; leave it alone
        return url, False

    if url.startswith('/'):
        return url, True

    # Relative. Resolve against the article's directory, exactly as a browser
    # would have on haresign.net.
    segments = [s for s in base_path.split('/') if s]
    parts = url.split('/')
    while parts and parts[0] in ('.', '..'):
        if parts[0] == '..' and segments:
            segments.pop()
        parts.pop(0)
    resolved = '/' + '/'.join(segments + parts) if segments or parts else '/'
    return resolved, True


def rewrite_body(html, *, slug, known_slugs, legacy_path=None):
    """Return `(rewritten_html, LinkReport)`.

    `known_slugs` is the set of article slugs being imported. It is what makes
    rule 3 safe: a `/blog/x/` link is only repointed when `x` is genuinely
    arriving here too.
    """
    report = LinkReport()
    if not html:
        return html, report

    base = legacy_path or f'/blog/{slug}/'
    soup = BeautifulSoup(html, 'html.parser')

    # --- Rule 4: dead controls -------------------------------------------
    for control in soup.select('[data-bs-toggle]'):
        control.decompose()
        report.removed_controls += 1

    # --- Rule 5: unhide what they controlled ------------------------------
    for panel in soup.select('.collapse'):
        classes = [c for c in panel.get('class', []) if c != 'collapse']
        panel['class'] = classes
        report.unhidden_panels += 1

    # --- Rule 6: the page owns the h1 -------------------------------------
    for heading in soup.find_all('h1'):
        heading.name = 'h2'
        report.demoted_headings += 1

    # --- Rules 1-3: URLs ---------------------------------------------------
    for img in soup.find_all('img'):
        original = img.get('src', '')
        path, internal = _absolutise(original, base)
        if not internal:
            if original.startswith(('http://', 'https://')):
                report.external_links.append((slug, original))
            continue
        match = _UPLOADS.match(path)
        new = LEGACY_MEDIA_PREFIX + match.group('rest') if match else path
        if new != original:
            img['src'] = new
            report.media_rewrites.append((slug, original, new))
        # An image with no alt is a real accessibility gap in the source. It is
        # reported by the command rather than filled in with invented text.

    for anchor in soup.find_all('a'):
        original = anchor.get('href', '')
        path, internal = _absolutise(original, base)
        if not internal:
            if original.startswith(('http://', 'https://')):
                report.external_links.append((slug, original))
            continue

        blog = _BLOG.match(path)
        if blog:
            target = blog.group('slug')
            if target in known_slugs:
                anchor['href'] = f'/insights/{target}/'
                report.article_links.append((slug, target))
            else:
                # Points at a legacy article that is not being imported. Left
                # exactly as it is: a wrong destination is worse than an old one,
                # and the redirect map is where this gets resolved.
                report.unresolved_internal.append((slug, path))
            continue

        upload = _UPLOADS.match(path)
        if upload:
            anchor['href'] = LEGACY_MEDIA_PREFIX + upload.group('rest')
            report.media_rewrites.append((slug, original, anchor['href']))
            continue

        if path.startswith('/tools/'):
            # Tools belong to Haresign Intelligence. Deliberately not rewritten
            # to anything here — Web does not own them and must not claim to.
            report.tool_links.append((slug, path))
            if path != original:
                anchor['href'] = path
            continue

        # Rule 3, second half: a path whose final segment names a known article.
        # These are TinyMCE's over-deep relative links, and they 404 on
        # haresign.net right now — repointing them is a repair, not a guess.
        segments = [s for s in path.split('/') if s]
        if segments and segments[-1] in known_slugs:
            anchor['href'] = f'/insights/{segments[-1]}/'
            report.article_links.append((slug, segments[-1]))
            report.repaired_paths.append((slug, path))
            continue

        report.unresolved_internal.append((slug, path))
        if path != original:
            anchor['href'] = path

    return str(soup), report


def audit_body(html):
    """Facts about a body, for the import summary. Reads, never writes."""
    if not html:
        return {'images': 0, 'images_without_alt': 0, 'tables': 0, 'iframes': 0,
                'inline_styles': 0, 'forms': 0}
    soup = BeautifulSoup(html, 'html.parser')
    images = soup.find_all('img')
    return {
        'images': len(images),
        'images_without_alt': sum(1 for i in images if not i.get('alt', '').strip()),
        'tables': len(soup.find_all('table')),
        'iframes': len(soup.find_all('iframe')),
        'inline_styles': len(soup.select('[style]')),
        # <input>/<button> in an article body: printable checklists in the
        # source. Counted so a genuinely interactive widget cannot arrive
        # unnoticed and quietly do nothing.
        'forms': len(soup.find_all(['input', 'button', 'select', 'textarea'])),
    }
