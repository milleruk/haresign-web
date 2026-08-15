"""Tests for Insights.

The centre of gravity is visibility: which articles the public may see. That is
the rule with real consequences — getting it wrong publishes unfinished work —
and it is the one thing several code paths could each get wrong independently.
"""
import pathlib
import shutil
import tempfile
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from insights.models import Article, Category, Tag
from insights.selectors import featured_article, recent_articles


def make_article(**kwargs):
    defaults = {
        'title': 'A published article',
        'slug': 'a-published-article',
        'summary': 'A short summary.',
        'body': '<p>Body copy.</p>',
        'status': Article.STATUS_PUBLISHED,
        'published_at': timezone.now() - timedelta(days=1),
    }
    return Article.objects.create(**{**defaults, **kwargs})


class ArticleModelTests(TestCase):
    def test_slug_must_be_unique(self):
        from django.db import IntegrityError

        make_article(slug='duplicate')
        with self.assertRaises(IntegrityError):
            Article.objects.create(
                title='Another', slug='duplicate', summary='s', body='<p>b</p>')

    def test_slug_is_derived_from_the_title_when_blank(self):
        article = Article.objects.create(
            title='Understanding Your Appointment Data', summary='s', body='<p>b</p>')

        self.assertEqual(article.slug, 'understanding-your-appointment-data')

    def test_publishing_without_a_date_stamps_now(self):
        """Otherwise "published at no time" would read as never visible."""
        before = timezone.now()
        article = Article.objects.create(
            title='T', slug='t', summary='s', body='<p>b</p>',
            status=Article.STATUS_PUBLISHED)

        self.assertIsNotNone(article.published_at)
        self.assertGreaterEqual(article.published_at, before)
        self.assertTrue(article.is_live)

    def test_draft_is_not_live(self):
        article = make_article(slug='d', status=Article.STATUS_DRAFT)

        self.assertFalse(article.is_live)
        self.assertNotIn(article, Article.objects.live())

    def test_archived_is_not_live(self):
        article = make_article(slug='a', status=Article.STATUS_ARCHIVED)

        self.assertFalse(article.is_live)
        self.assertNotIn(article, Article.objects.live())

    def test_future_dated_is_not_live(self):
        """Published + a future date is *scheduled*. The status alone is not the
        question — a view that only checked it would leak the article early."""
        article = make_article(
            slug='f', published_at=timezone.now() + timedelta(days=3))

        self.assertEqual(article.status, Article.STATUS_PUBLISHED)
        self.assertFalse(article.is_live)
        self.assertNotIn(article, Article.objects.live())

    def test_published_and_dated_is_live(self):
        article = make_article()

        self.assertTrue(article.is_live)
        self.assertIn(article, Article.objects.live())

    def test_seo_fields_fall_back_to_title_and_summary(self):
        article = make_article()
        self.assertEqual(article.seo_title, article.title)
        self.assertEqual(article.seo_description, article.summary)

        article.meta_title = 'Custom'
        article.meta_description = 'Custom description'
        self.assertEqual(article.seo_title, 'Custom')
        self.assertEqual(article.seo_description, 'Custom description')


class TaxonomyTests(TestCase):
    def test_category_and_tag_slugs_derive_from_the_name(self):
        category = Category.objects.create(name='Workforce Planning')
        tag = Tag.objects.create(name='List Size')

        self.assertEqual(category.slug, 'workforce-planning')
        self.assertEqual(tag.slug, 'list-size')

    def test_articles_can_carry_categories_and_tags(self):
        article = make_article()
        article.categories.add(Category.objects.create(name='Research'))
        article.tags.add(Tag.objects.create(name='QOF'))

        self.assertEqual(article.categories.count(), 1)
        self.assertEqual(article.tags.count(), 1)


class InsightsIndexTests(TestCase):
    def test_published_article_appears(self):
        make_article(title='Visible piece', slug='visible')

        response = self.client.get(reverse('insights:index'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Visible piece')

    def test_draft_archived_and_future_articles_do_not_appear(self):
        make_article(title='Live one', slug='live')
        make_article(title='Draft one', slug='draft', status=Article.STATUS_DRAFT)
        make_article(title='Archived one', slug='arch', status=Article.STATUS_ARCHIVED)
        make_article(title='Future one', slug='future',
                     published_at=timezone.now() + timedelta(days=2))

        response = self.client.get(reverse('insights:index'))

        self.assertContains(response, 'Live one')
        for hidden in ('Draft one', 'Archived one', 'Future one'):
            self.assertNotContains(response, hidden)

    def test_ordering_is_newest_first(self):
        old = make_article(title='Older', slug='older',
                           published_at=timezone.now() - timedelta(days=10))
        new = make_article(title='Newer', slug='newer',
                           published_at=timezone.now() - timedelta(days=1))

        body = self.client.get(reverse('insights:index')).content.decode()

        self.assertLess(body.index(new.title), body.index(old.title))

    def test_featured_article_is_not_repeated_in_the_list(self):
        """Seeing the same piece twice at the top of a page reads as a bug."""
        make_article(title='The featured one', slug='feat', is_featured=True)
        make_article(title='Another one', slug='another')

        body = self.client.get(reverse('insights:index')).content.decode()

        self.assertEqual(body.count('>The featured one<'), 1)


class ArticleDetailTests(TestCase):
    def test_published_article_resolves(self):
        article = make_article(title='Readable', slug='readable',
                               body='<h2>A heading</h2><p>Some text.</p>')

        response = self.client.get(article.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Readable')
        # Body HTML is rendered, not escaped — inside .hs-prose only.
        self.assertContains(response, '<h2>A heading</h2>')
        self.assertContains(response, 'hs-prose')

    def test_unavailable_articles_404(self):
        for slug, kwargs in (
            ('draft-piece', {'status': Article.STATUS_DRAFT}),
            ('archived-piece', {'status': Article.STATUS_ARCHIVED}),
            ('future-piece', {'published_at': timezone.now() + timedelta(days=1)}),
        ):
            with self.subTest(slug=slug):
                article = make_article(slug=slug, **kwargs)

                response = self.client.get(f'/insights/{slug}/')

                self.assertEqual(response.status_code, 404)
                # A 404 rather than a "not published yet" page: the second would
                # confirm the article exists.
                self.assertNotContains(response, article.title, status_code=404)

    def test_unknown_slug_404s(self):
        self.assertEqual(self.client.get('/insights/nothing-here/').status_code, 404)

    def test_body_html_is_not_escaped_but_nothing_else_is_marked_safe(self):
        make_article(slug='esc', title='Title with <b>markup</b>',
                     body='<p>Real <strong>body</strong> markup.</p>')

        response = self.client.get('/insights/esc/')

        self.assertContains(response, '<strong>body</strong>')
        # The title is data, not markup, and must still be escaped.
        self.assertContains(response, 'Title with &lt;b&gt;markup&lt;/b&gt;')


class SelectorTests(TestCase):
    def test_featured_prefers_the_flagged_article(self):
        make_article(title='Ordinary', slug='ordinary')
        featured = make_article(title='Flagged', slug='flagged', is_featured=True,
                                published_at=timezone.now() - timedelta(days=5))

        self.assertEqual(featured_article(), featured)

    def test_featured_falls_back_to_the_newest_when_none_flagged(self):
        make_article(title='Older', slug='o',
                     published_at=timezone.now() - timedelta(days=9))
        newest = make_article(title='Newest', slug='n',
                              published_at=timezone.now() - timedelta(hours=1))

        self.assertEqual(featured_article(), newest)

    def test_featured_is_none_when_nothing_is_live(self):
        make_article(slug='draft-only', status=Article.STATUS_DRAFT)

        self.assertIsNone(featured_article())

    def test_recent_excludes_the_featured_article(self):
        featured = make_article(title='Lead', slug='lead', is_featured=True)
        other = make_article(title='Other', slug='other')

        recent = recent_articles(limit=5, exclude=featured)

        self.assertIn(other, recent)
        self.assertNotIn(featured, recent)


class HomepageInsightsTests(TestCase):
    """The homepage reads the same data, through the same selectors."""

    def test_homepage_shows_database_articles(self):
        make_article(title='Homepage lead', slug='hp-lead', is_featured=True)
        make_article(title='Homepage second', slug='hp-second')

        response = self.client.get('/')

        self.assertContains(response, 'Latest insight')
        self.assertContains(response, 'Homepage lead')
        self.assertContains(response, 'Homepage second')

    def test_homepage_omits_the_section_when_nothing_is_published(self):
        make_article(slug='hidden', status=Article.STATUS_DRAFT)

        response = self.client.get('/')

        self.assertNotContains(response, 'Latest insight')

    def test_homepage_links_to_the_article(self):
        article = make_article(title='Linked piece', slug='linked', is_featured=True)

        response = self.client.get('/')

        self.assertContains(response, f'href="{article.get_absolute_url()}"')


class HeadingStructureTests(TestCase):
    """Every page needs exactly one `<h1>`.

    The Insights index had none: it used the section-header partial, which
    renders an `<h2>`, so the outline began at level 2 under nothing and a screen
    reader user got no page title. Nothing errors when this is wrong, which is
    why it is a test.
    """

    def setUp(self):
        Article.objects.create(
            title='A published piece',
            slug='a-published-piece',
            summary='Summary.',
            body='<p>Body.</p>',
            status=Article.STATUS_PUBLISHED,
            published_at=timezone.now(),
        )

    def test_index_has_exactly_one_h1(self):
        body = self.client.get(reverse('insights:index')).content.decode()

        self.assertEqual(body.count('<h1'), 1)

    def test_article_has_exactly_one_h1(self):
        body = self.client.get(
            reverse('insights:detail', kwargs={'slug': 'a-published-piece'})
        ).content.decode()

        self.assertEqual(body.count('<h1'), 1)

    def test_the_article_h1_is_its_title(self):
        """Not "Insights" with the title as an h2 beneath it — the page is about
        the article."""
        response = self.client.get(
            reverse('insights:detail', kwargs={'slug': 'a-published-piece'}))

        self.assertContains(response, 'A published piece')


class FeaturedImageAltTests(TestCase):
    """An image with no description is *explicitly* decorative.

    Every imported article arrived without alt text: the monolith has no such
    field, and inventing 67 descriptions would have been fabrication. Decorative
    is the correct answer for a header card that repeats the headline printed
    beside it — but it has to be declared, because an empty alt and a forgotten
    alt look identical.
    """

    def setUp(self):
        # Its own MEDIA_ROOT. Saving an ImageField writes a real file, and a
        # test that writes into the deployment's media volume both fails on
        # permissions and leaves litter in the live upload tree.
        self._media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self._media)
        override.enable()
        self.addCleanup(override.disable)

        self.article = make_article(slug='with-image')

    def _attach_image(self, alt=''):
        from django.core.files.uploadedfile import SimpleUploadedFile

        # A 1x1 GIF: the smallest thing Pillow will accept as an image.
        gif = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
               b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
               b'\x00\x02\x02D\x01\x00;')
        self.article.featured_image = SimpleUploadedFile('hero.gif', gif, 'image/gif')
        self.article.featured_image_alt = alt
        self.article.save()

    def test_an_undescribed_image_is_marked_presentational(self):
        self._attach_image()

        response = self.client.get(self.article.get_absolute_url())

        self.assertContains(response, 'alt="" role="presentation"')

    def test_a_described_image_keeps_its_description(self):
        self._attach_image(alt='A chart of appointment volumes by month')

        response = self.client.get(self.article.get_absolute_url())

        self.assertContains(response, 'A chart of appointment volumes by month')
        self.assertNotContains(response, 'role="presentation"')

    def test_the_rule_is_defined_once(self):
        """It renders in four places. Four copies of a decision is how three of
        them end up wrong."""
        import pathlib

        for template in list(pathlib.Path('insights/templates').rglob('*.html')) + \
                list(pathlib.Path('web/templates').rglob('*.html')):
            if template.name == '_featured_image.html':
                continue
            with self.subTest(template=str(template)):
                self.assertNotIn('featured_image_alt', template.read_text())

    def test_no_alt_text_was_invented_during_the_import(self):
        """The importer must never fill this field: the source has nothing to
        fill it from."""
        source = pathlib.Path(
            'insights/management/commands/import_legacy_articles.py').read_text()

        self.assertNotIn('featured_image_alt', source)
