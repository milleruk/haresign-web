"""Tests for the public web layer.

`SimpleTestCase` throughout — there is no database, and using it asserts that:
any test needing one would fail loudly rather than quietly acquiring a
connection this application is not supposed to have.
"""
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from config.services import build_registry
from web.content import PLATFORMS, PRINCIPLES, get_insights
from web.views import build_platform_cards


class HomePageTests(SimpleTestCase):
    def test_renders(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'web/home.html')

    def test_leads_with_the_growth_message(self):
        response = self.client.get('/')

        self.assertContains(response, 'Haresign has')
        # "grown" is emphasised in its own element, not just present in text.
        self.assertContains(response, 'hs-hero__emphasis')
        self.assertContains(response, 'Four platforms. One purpose.')

    def test_shows_every_platform_with_its_copy(self):
        response = self.client.get('/')

        for platform in PLATFORMS:
            self.assertContains(response, platform.heading)
            self.assertContains(response, platform.blurb)
            self.assertContains(response, platform.cta)

    def test_shows_the_four_principles(self):
        response = self.client.get('/')

        for principle in PRINCIPLES:
            self.assertContains(response, principle['heading'])
            self.assertContains(response, principle['body'])

    def test_heading_hierarchy_has_exactly_one_h1(self):
        """A single h1 per page; sections descend from it via h2."""
        body = self.client.get('/').content.decode()

        self.assertEqual(body.count('<h1'), 1)

    def test_page_has_a_skip_link_to_the_main_landmark(self):
        response = self.client.get('/')

        self.assertContains(response, 'hs-skip-link')
        self.assertContains(response, 'id="main"')

    def test_no_inline_style_attributes_or_style_blocks(self):
        """The design system lives in CSS files. A <style> block or a style=""
        attribute means something bypassed it, which is how token discipline
        rots — so it fails the build rather than being noticed later."""
        body = self.client.get('/').content.decode()

        self.assertNotIn('<style', body)
        self.assertNotIn('style="', body)

    def test_logo_ink_matches_the_ground_it_sits_on(self):
        """The filename suffix names the *background*, not the ink: -dark is the
        white-ink file. The header is white and the footer deep navy, so they
        take opposite variants. Get it wrong and the logo is invisible rather
        than obviously broken, which no other test would catch."""
        body = self.client.get('/').content.decode()
        header, _, footer = body.partition('<footer')

        # Matched on the stem with its trailing dot, because WhiteNoise's
        # manifest storage inserts a content hash before the extension
        # ("logo-primary.edeb55afdd97.png"). "logo-primary." cannot match
        # "logo-primary-dark.…", which is what makes the pair distinguishable.
        self.assertIn('logo-primary.', header)
        self.assertNotIn('logo-primary-dark.', header)
        self.assertIn('logo-primary-dark.', footer)


class PlatformAvailabilityTests(SimpleTestCase):
    """Three of the four platforms do not exist yet. A card must never link to
    a host that does not resolve."""

    def test_unavailable_platform_offers_no_link(self):
        response = self.client.get('/')

        self.assertContains(response, 'Coming soon')
        # Consulting is not live by default, so its URL must not appear as an href.
        self.assertNotContains(response, 'href="https://consulting.haresign.net"')

    def test_available_platform_is_linked(self):
        response = self.client.get('/')

        self.assertContains(response, 'href="https://app.haresign.net"')

    def test_availability_is_configuration_not_code(self):
        registry = build_registry()
        self.assertTrue(registry['app']['available'])
        self.assertFalse(registry['consulting']['available'])

        with self.settings(HARESIGN_SERVICES=_registry_with_live('app,consulting')):
            cards = {c['platform'].service: c for c in build_platform_cards()}
            self.assertTrue(cards['consulting']['available'])

    def test_sign_in_does_not_imply_authentication_exists(self):
        """Auth is a later piece of work. The control must not navigate."""
        response = self.client.get('/')

        self.assertNotContains(response, 'href="https://auth.haresign.net"')
        self.assertContains(response, 'aria-describedby="hs-signin-note"')

    def test_card_domain_label_matches_where_it_points(self):
        """The label under a card is derived from the URL, so the two cannot
        disagree after a subdomain move."""
        for card in build_platform_cards():
            self.assertTrue(card['url'].endswith(card['domain']))


def _registry_with_live(live_csv):
    import os
    previous = os.environ.get('HARESIGN_LIVE_SERVICES')
    os.environ['HARESIGN_LIVE_SERVICES'] = live_csv
    try:
        return build_registry()
    finally:
        if previous is None:
            os.environ.pop('HARESIGN_LIVE_SERVICES', None)
        else:
            os.environ['HARESIGN_LIVE_SERVICES'] = previous


class InsightsTests(SimpleTestCase):
    def test_featured_article_plus_three_cards(self):
        response = self.client.get('/')

        self.assertContains(response, 'Latest insight')
        self.assertEqual(len(response.context['recent_articles']), 3)

    def test_placeholder_articles_are_labelled_not_passed_off_as_published(self):
        response = self.client.get('/')

        self.assertContains(response, 'Sample')

    def test_articles_without_a_url_are_not_rendered_as_links(self):
        """Every placeholder lacks a URL; none may become a dead anchor."""
        for article in get_insights():
            self.assertFalse(article.has_link)

    def test_section_is_omitted_when_there_is_no_content(self):
        """An empty "Latest insight" strip says more about the site than none."""
        with self.settings():
            response = self.client.get('/')
            self.assertContains(response, 'Latest insight')

        # The template gates on featured_article, so an empty source removes it.
        from unittest.mock import patch
        with patch('web.views.get_insights', return_value=[]):
            response = self.client.get('/')
            self.assertNotContains(response, 'Latest insight')


class SeoTests(SimpleTestCase):
    def test_beta_is_noindex_by_default(self):
        """Indexing is opt-in, so beta cannot be indexed by forgetting a flag."""
        response = self.client.get('/')

        self.assertContains(response, 'noindex, nofollow')

    @override_settings(SITE_INDEXABLE=True)
    def test_indexable_when_explicitly_enabled(self):
        response = self.client.get('/')

        self.assertNotContains(response, 'noindex')

    def test_robots_txt_matches_the_indexing_setting(self):
        response = self.client.get('/robots.txt')

        self.assertEqual(response.status_code, 200)
        self.assertIn('Disallow: /', response.content.decode())

    @override_settings(SITE_INDEXABLE=True)
    def test_robots_txt_allows_when_indexable(self):
        body = self.client.get('/robots.txt').content.decode()

        self.assertIn('Allow: /', body)
        self.assertIn('Sitemap:', body)

    def test_canonical_uses_the_configured_origin_not_the_request_host(self):
        response = self.client.get('/', HTTP_HOST='testserver')

        self.assertContains(response, f'href="{settings.SITE_BASE_URL}/"')

    def test_title_and_description_are_set(self):
        body = self.client.get('/').content.decode()

        self.assertIn('<title>Haresign', body)
        self.assertIn('name="description"', body)
        self.assertIn('property="og:title"', body)


class HealthTests(SimpleTestCase):
    def test_health_returns_ok(self):
        response = self.client.get('/health/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_health_is_not_cached(self):
        """A cached health check reports the past, which is the one thing a
        health check must never do."""
        response = self.client.get('/health/')

        self.assertIn('no-cache', response['Cache-Control'])


class DecouplingTests(SimpleTestCase):
    """This repository owns the public web layer and nothing else. These are the
    architectural boundaries written down as assertions."""

    def test_no_database_is_configured(self):
        """settings.py sets DATABASES = {}. Django's ConnectionHandler back-fills
        a `default` alias with the *dummy* backend as soon as connections are
        touched, so asserting `== {}` would pass at import and fail under the
        test runner. The invariant that actually matters is that no engine
        capable of connecting to anything is configured."""
        engines = {
            config.get('ENGINE', '')
            for config in settings.DATABASES.values()
        }

        self.assertTrue(engines <= {'', 'django.db.backends.dummy'}, engines)

    def test_no_auth_session_or_admin_apps(self):
        for app in ('django.contrib.auth', 'django.contrib.sessions',
                    'django.contrib.admin', 'django.contrib.contenttypes'):
            self.assertNotIn(app, settings.INSTALLED_APPS)

    def test_platform_urls_are_configuration(self):
        """Subdomains will move during the migration; nothing may hard-code one."""
        registry = build_registry()

        for slug in ('consulting', 'app', 'community', 'clients', 'auth'):
            self.assertTrue(registry[slug]['url'].startswith('https://'))
