"""Tests for the legacy HTML rewriter.

Written against the shapes that actually appear in the monolith's 67 articles —
Bootstrap collapse panels, TinyMCE's over-deep relative URLs, absolute links back
to haresign.net — rather than against tidy invented markup. Each test names the
rule it covers, and the rules are documented in `insights/importing.py`.
"""
from django.test import SimpleTestCase

from insights.importing import audit_body, rewrite_body

KNOWN = {'an-article', 'another-article'}


def rewrite(html, slug='an-article', known=None):
    return rewrite_body(html, slug=slug, known_slugs=known or KNOWN)


class RelativeUrlTests(SimpleTestCase):
    """Rule 1."""

    def test_over_deep_relative_image_resolves_to_the_root(self):
        html = '<img src="../../../../uploads/library/2026/08/1.png">'

        out, _ = rewrite(html)

        self.assertIn('/media/insights/legacy/library/2026/08/1.png', out)

    def test_absolute_legacy_url_is_treated_as_internal(self):
        html = '<img src="https://haresign.net/uploads/blog/images/x.png">'

        out, report = rewrite(html)

        self.assertIn('/media/insights/legacy/blog/images/x.png', out)
        self.assertEqual(len(report.media_rewrites), 1)

    def test_in_page_anchors_are_left_alone(self):
        """An article's own contents list is full of these. Rewriting one would
        break the very navigation the article ships with."""
        html = '<a href="#methodology">Method</a>'

        out, report = rewrite(html)

        self.assertIn('href="#methodology"', out)
        self.assertEqual(report.unresolved_internal, [])

    def test_external_links_are_untouched(self):
        html = '<a href="https://www.england.nhs.uk/long-read/x/">NHS England</a>'

        out, report = rewrite(html)

        self.assertIn('https://www.england.nhs.uk/long-read/x/', out)
        self.assertEqual(len(report.external_links), 1)

    def test_mailto_survives(self):
        out, _ = rewrite('<a href="mailto:contact@haresign.net">Email</a>')

        self.assertIn('mailto:contact@haresign.net', out)


class ArticleLinkTests(SimpleTestCase):
    """Rule 3 — and the restraint that makes it safe."""

    def test_a_link_to_an_imported_article_follows_it(self):
        out, report = rewrite('<a href="/blog/another-article/">See also</a>')

        self.assertIn('href="/insights/another-article/"', out)
        self.assertEqual(report.article_links, [('an-article', 'another-article')])

    def test_a_link_to_an_article_not_being_imported_is_left_alone(self):
        """Guessing at a destination is how a live link becomes a 404."""
        out, report = rewrite('<a href="/blog/not-migrated/">Elsewhere</a>')

        self.assertIn('href="/blog/not-migrated/"', out)
        self.assertEqual(report.unresolved_internal, [('an-article', '/blog/not-migrated/')])

    def test_a_dead_path_ending_in_a_known_slug_is_repaired(self):
        """TinyMCE wrote some links one ../ too deep, so they 404 on
        haresign.net today. Where the last segment names a real article the
        intent is unambiguous."""
        out, report = rewrite('<a href="../../../../../articles/another-article/">x</a>')

        self.assertIn('href="/insights/another-article/"', out)
        self.assertEqual(len(report.repaired_paths), 1)

    def test_a_dead_path_that_names_nothing_is_reported_not_guessed(self):
        out, report = rewrite('<a href="/media/downloads/briefing.pdf">Download</a>')

        self.assertIn('/media/downloads/briefing.pdf', out)
        self.assertEqual(len(report.unresolved_internal), 1)

    def test_tool_links_stay_pointing_at_the_tools(self):
        """Intelligence owns the tools. Web does not, and must not claim to."""
        out, report = rewrite('<a href="https://haresign.net/tools/nwrs-workforce/">Tool</a>')

        self.assertIn('/tools/nwrs-workforce/', out)
        self.assertNotIn('/insights/tools', out)
        self.assertEqual(len(report.tool_links), 1)


class BootstrapTests(SimpleTestCase):
    """Rules 4 and 5, which only make sense together."""

    COLLAPSE = (
        '<button data-bs-toggle="collapse" data-bs-target="#c">View contents</button>'
        '<div id="c" class="collapse d-lg-block"><p>Contents</p></div>'
    )

    def test_the_dead_control_is_removed(self):
        out, report = rewrite(self.COLLAPSE)

        self.assertNotIn('data-bs-toggle', out)
        self.assertEqual(report.removed_controls, 1)

    def test_what_it_controlled_is_left_visible(self):
        """Removing the button alone would be destructive: `collapse` hides the
        panel below 992px, so an article's contents would be unreachable on a
        phone with nothing left to open it."""
        out, report = rewrite(self.COLLAPSE)

        self.assertNotIn('collapse', out)
        self.assertIn('<p>Contents</p>', out)
        self.assertEqual(report.unhidden_panels, 1)

    def test_ordinary_bootstrap_layout_is_kept(self):
        """The vendored build is full Bootstrap, so cards and grids render. The
        importer's job is not to restyle articles."""
        out, _ = rewrite('<div class="card h-100"><div class="card-body">Hi</div></div>')

        self.assertIn('card h-100', out)
        self.assertIn('card-body', out)


class HeadlineBlockTests(SimpleTestCase):
    """Rule 6 — the leading headline block is moved, not deleted.

    The real markup: a category badge, an h1 and a standfirst, inside a
    <header> above the article proper. The page template renders a kicker, a
    title and a summary in exactly those roles, so importing it unchanged
    printed a second headline under the first.
    """

    HEADER = (
        '<article><header class="mb-5">'
        '<div class="mb-3"><span class="badge text-bg-primary"> Data &amp; Insight </span></div>'
        '<h1 class="h1 fw-bold">Benchmarking Is Not a League Table</h1>'
        '<p class="lead">A standfirst that is not the summary.</p>'
        '<div class="alert">The central principle.</div>'
        '</header><p>Body.</p></article>'
    )

    def test_the_duplicate_headline_leaves_the_body(self):
        out, report = rewrite(self.HEADER)

        self.assertNotIn('<h1', out)
        self.assertNotIn('Benchmarking Is Not a League Table', out)
        self.assertEqual(report.lifted_headlines, 1)

    def test_the_headline_text_is_handed_back_rather_than_lost(self):
        _, report = rewrite(self.HEADER)

        self.assertEqual(report.extracted['meta_title'],
                         'Benchmarking Is Not a League Table')

    def test_the_badge_becomes_a_kicker(self):
        """A field the template already renders and nothing was filling."""
        out, report = rewrite(self.HEADER)

        self.assertEqual(report.extracted['kicker'], 'Data & Insight')
        self.assertNotIn('badge', out)

    def test_the_standfirst_stays(self):
        """It is a real opening paragraph and differs from the summary in 10 of
        the 13 cases where both exist. Removing it would lose writing."""
        out, _ = rewrite(self.HEADER)

        self.assertIn('A standfirst that is not the summary.', out)

    def test_editorial_content_inside_the_header_survives(self):
        """The <header> is not stripped wholesale — these blocks contain real
        callouts, and taking the lot to remove one heading would be
        destructive."""
        out, _ = rewrite(self.HEADER)

        self.assertIn('The central principle.', out)

    def test_a_later_h1_is_demoted_rather_than_lifted(self):
        """Only the *first* heading is the article's own headline. An h1 further
        down is a section, and removing it would lose a section title."""
        out, report = rewrite('<h2>A section</h2><h1>Not the headline</h1>')

        self.assertIn('<h2>Not the headline</h2>', out)
        self.assertEqual(report.demoted_headings, 1)
        self.assertEqual(report.lifted_headlines, 0)

    def test_an_unrelated_badge_further_down_is_not_taken_as_a_kicker(self):
        html = ('<div><h1>Headline</h1></div>'
                '<div><span class="badge">Some label</span></div>')

        _, report = rewrite(html)

        self.assertNotIn('kicker', report.extracted)

    def test_a_body_with_no_headline_block_is_untouched(self):
        html = '<p>Straight into it.</p><h2>A section</h2>'

        out, report = rewrite(html)

        self.assertEqual(report.lifted_headlines, 0)
        self.assertIn('<h2>A section</h2>', out)


class NonDestructiveTests(SimpleTestCase):
    def test_empty_bodies_do_not_explode(self):
        for value in ('', None):
            with self.subTest(value=value):
                out, report = rewrite(value)
                self.assertEqual(out, value)

    def test_tables_survive_untouched(self):
        html = ('<table class="table"><thead><tr><th>A</th></tr></thead>'
                '<tbody><tr><td>1</td></tr></tbody></table>')

        out, _ = rewrite(html)

        self.assertIn('<th>A</th>', out)
        self.assertIn('<td>1</td>', out)

    def test_rewriting_is_stable(self):
        """Running the rewriter over its own output must change nothing —
        otherwise a re-import would drift the content a little each time."""
        html = ('<h1>T</h1><a href="/blog/another-article/">x</a>'
                '<img src="../../../../uploads/library/1.png">'
                '<button data-bs-toggle="collapse">b</button>')

        once, _ = rewrite(html)
        twice, _ = rewrite(once)

        self.assertEqual(once, twice)


class AuditTests(SimpleTestCase):
    def test_it_counts_what_the_import_report_needs(self):
        html = ('<img src="/a.png"><img src="/b.png" alt="described">'
                '<table></table><input type="checkbox">')

        audit = audit_body(html)

        self.assertEqual(audit['images'], 2)
        self.assertEqual(audit['images_without_alt'], 1)
        self.assertEqual(audit['tables'], 1)
        self.assertEqual(audit['forms'], 1)
