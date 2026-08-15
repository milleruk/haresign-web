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
from insights.selectors import (PAGE_SIZE, featured_article, filter_tags,
                                recent_articles)


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


class IndexPaginationTests(TestCase):
    """Paging the archive.

    The reason for paginating was never HTML weight — the whole archive was 70KB
    of markup. It was images: 64.8MB of hero images behind one page, growing with
    every article published.
    """

    def setUp(self):
        for index in range(20):
            make_article(
                title=f'Article {index:02d}', slug=f'article-{index:02d}',
                published_at=timezone.now() - timedelta(days=index))

    def test_the_first_page_shows_a_page_worth(self):
        response = self.client.get(reverse('insights:index'))

        # 12 in the grid, plus the featured article pulled out above it.
        self.assertEqual(len(response.context['articles']), PAGE_SIZE)
        self.assertIsNotNone(response.context['featured'])

    def test_later_pages_carry_the_rest(self):
        response = self.client.get(reverse('insights:index'), {'page': 2})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page'].number, 2)

    def test_no_article_appears_on_two_pages(self):
        seen = []
        for number in (1, 2):
            response = self.client.get(reverse('insights:index'), {'page': number})
            seen += [a.pk for a in response.context['articles']]
            if response.context['featured']:
                seen.append(response.context['featured'].pk)

        self.assertEqual(len(seen), len(set(seen)))

    def test_the_featured_article_leads_page_one_only(self):
        """On page two it would be stale furniture at the top of the page."""
        response = self.client.get(reverse('insights:index'), {'page': 2})

        self.assertIsNone(response.context['featured'])

    def test_a_page_past_the_end_is_a_404(self):
        """It names a page that does not exist. Answering with an empty list
        invites the reader to conclude the archive is empty."""
        response = self.client.get(reverse('insights:index'), {'page': 99})

        self.assertEqual(response.status_code, 404)

    def test_a_page_that_is_not_a_number_is_a_404_not_a_500(self):
        """Django raises PageNotAnInteger here, which is a *sibling* of
        EmptyPage rather than a subclass — catching only EmptyPage turned a junk
        query string into a server error."""
        for value in ('abc', '-1', '0', ''):
            with self.subTest(page=value):
                response = self.client.get(reverse('insights:index'), {'page': value})

                self.assertIn(response.status_code, (200, 404))
                self.assertNotEqual(response.status_code, 500)

    def test_pagination_controls_only_appear_when_there_is_more_than_one_page(self):
        Article.objects.exclude(slug='article-00').delete()

        body = self.client.get(reverse('insights:index')).content.decode()

        self.assertNotIn('hs-pagination', body)


class IndexFilterTests(TestCase):
    """Filtering by tag."""

    def setUp(self):
        self.governance = Tag.objects.create(name='Governance', slug='governance')
        self.workforce = Tag.objects.create(name='Workforce', slug='workforce')
        for index in range(5):
            article = make_article(title=f'G{index}', slug=f'g-{index}')
            article.tags.add(self.governance)
        article = make_article(title='W', slug='w')
        article.tags.add(self.workforce)

    def test_filtering_narrows_the_list(self):
        response = self.client.get(reverse('insights:index'), {'tag': 'workforce'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['articles']), 1)
        self.assertEqual(response.context['active_tag'], self.workforce)

    def test_the_featured_article_is_dropped_when_filtering(self):
        """It would be an article ignoring the filter the reader just set."""
        response = self.client.get(reverse('insights:index'), {'tag': 'workforce'})

        self.assertIsNone(response.context['featured'])

    def test_an_unknown_tag_is_a_404(self):
        response = self.client.get(reverse('insights:index'), {'tag': 'nonsense'})

        self.assertEqual(response.status_code, 404)

    def test_filters_show_their_counts(self):
        """These tags are topical labels, not a taxonomy: the largest covers more
        than half the archive. A chip that silently returns most of it feels
        broken; one that says so is telling the reader what it will do."""
        body = self.client.get(reverse('insights:index')).content.decode()

        self.assertIn('Governance', body)
        self.assertIn('hs-filter__count', body)
        self.assertIn('>5<', body)

    def test_counts_are_of_live_articles_only(self):
        """A count must never promise more than the filter delivers."""
        Article.objects.filter(slug='g-0').update(status=Article.STATUS_DRAFT)

        counts = {tag.name: tag.article_count for tag in filter_tags()}

        self.assertEqual(counts['Governance'], 4)

    def test_the_active_filter_is_marked_for_assistive_technology(self):
        """Not by chip colour alone."""
        body = self.client.get(
            reverse('insights:index'), {'tag': 'workforce'}).content.decode()

        self.assertIn('aria-current="page"', body)

    def test_filtering_needs_no_javascript(self):
        """Every filtered view has its own URL, so it can be bookmarked and
        shared and the back button behaves."""
        body = self.client.get(reverse('insights:index')).content.decode()
        main = body[body.index('<main'):body.index('</main>')]

        self.assertNotIn('<script', main)
        self.assertIn('href="/insights/?tag=governance"', main)

    def test_each_view_canonicalises_to_itself(self):
        """Pointing every page at page one would tell a search engine that five
        sixths of the archive duplicates the first sixth."""
        response = self.client.get(reverse('insights:index'), {'tag': 'governance'})

        self.assertContains(response, 'insights/?tag=governance"')


class FeaturedImageFormatTests(TestCase):
    """`<picture>` with a WebP source and the original as fallback."""

    def setUp(self):
        self._media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self._media)
        override.enable()
        self.addCleanup(override.disable)
        self.article = make_article(slug='with-image')

    def _attach_image(self, with_webp=False):
        from django.core.files.uploadedfile import SimpleUploadedFile

        gif = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
               b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
               b'\x00\x02\x02D\x01\x00;')
        self.article.featured_image = SimpleUploadedFile('hero.gif', gif, 'image/gif')
        self.article.save()
        if with_webp:
            sibling = pathlib.Path(self._media) / pathlib.Path(
                self.article.featured_image.name).with_suffix('.webp')
            sibling.parent.mkdir(parents=True, exist_ok=True)
            sibling.write_bytes(b'not really webp, but it exists')

    def test_no_webp_source_when_the_file_does_not_exist(self):
        """A <source> pointing at a missing file shows a broken image to every
        browser that prefers WebP — which is nearly all of them."""
        self._attach_image(with_webp=False)

        response = self.client.get(self.article.get_absolute_url())

        self.assertNotContains(response, '<picture>')
        self.assertNotContains(response, 'image/webp')

    def test_the_webp_is_offered_when_it_exists(self):
        self._attach_image(with_webp=True)

        response = self.client.get(self.article.get_absolute_url())

        self.assertContains(response, '<picture>')
        self.assertContains(response, 'type="image/webp"')

    def test_the_original_remains_the_fallback(self):
        """One extra element buys a working image on a browser that has never
        heard of WebP — which this audience's locked-down desktops may be."""
        self._attach_image(with_webp=True)

        response = self.client.get(self.article.get_absolute_url())

        self.assertContains(response, self.article.featured_image.url)
