"""Tests for the public web layer.

`SimpleTestCase` throughout — there is no database, and using it asserts that:
any test needing one would fail loudly rather than quietly acquiring a
connection this application is not supposed to have.
"""
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from config.services import build_registry
from web.content import PRINCIPLES, get_insights
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

        for card in build_platform_cards():
            self.assertContains(response, card['name'])
            self.assertContains(response, card['platform'].blurb)
            self.assertContains(response, card['platform'].cta)

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

    def test_no_template_syntax_leaks_into_the_page(self):
        """`{# … #}` comments only ever cover a SINGLE line — a multi-line one
        renders straight into the page as text, which is exactly what happened
        in <head> and showed above the hero. Nothing errors, so only a test
        catches it."""
        body = self.client.get('/').content.decode()

        for token in ('{#', '#}', '{%', '%}', '{{', '}}'):
            self.assertNotIn(token, body)

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
        self.assertTrue(registry['intelligence']['available'])
        self.assertFalse(registry['consulting']['available'])

        with self.settings(HARESIGN_SERVICES=_registry_with_live('intelligence,consulting')):
            cards = {c['platform'].service: c for c in build_platform_cards()}
            self.assertTrue(cards['consulting']['available'])

    def test_sign_in_does_not_imply_authentication_exists(self):
        """Auth is a later piece of work. The control must not navigate."""
        response = self.client.get('/')

        self.assertNotContains(response, 'href="https://auth.haresign.net"')
        self.assertContains(response, 'aria-describedby="hs-account-note"')

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


class NamingTests(SimpleTestCase):
    """The agreed product naming: **Haresign + a clear functional name**.

    Written down as assertions because naming drifts silently — nothing breaks
    when a superseded label reappears, so nothing catches it either.
    """

    AGREED = [
        'Haresign Consulting',
        'Haresign Intelligence',
        'Haresign Community',
        'Haresign Workspace',
    ]

    # Retired customer-facing labels. "Haresign Core" is the internal
    # architectural term for the identity service; users see "Haresign Account".
    SUPERSEDED = [
        'Haresign App',
        'Haresign Clients',
        'Client Portal',
        'Client Login',
        'Haresign Core',
    ]

    def test_agreed_product_names_are_used(self):
        response = self.client.get('/')

        for name in self.AGREED:
            self.assertContains(response, name)

    def test_no_superseded_label_survives(self):
        body = self.client.get('/').content.decode()

        for label in self.SUPERSEDED:
            self.assertNotIn(label, body)

    def test_nav_uses_the_short_label_not_the_full_name(self):
        """The nav has no room for the full name four times, and the logo beside
        it already states the master brand."""
        body = self.client.get('/').content.decode()
        nav = body[body.index('<nav'):body.index('</nav>')]

        self.assertIn('>Intelligence<', nav)
        self.assertIn('>Workspace<', nav)
        self.assertNotIn('Haresign Intelligence', nav)

    def test_account_is_the_public_name_for_identity(self):
        registry = build_registry()

        self.assertEqual(registry['account']['name'], 'Haresign Account')
        self.assertEqual(registry['account']['url'], 'https://auth.haresign.net')

    def test_product_renames_did_not_move_the_hosts(self):
        """Renaming a product is not renaming a live subdomain — the slugs are
        the product names, the hosts stay where they are deployed."""
        registry = build_registry()

        self.assertEqual(registry['intelligence']['url'], 'https://app.haresign.net')
        self.assertEqual(registry['workspace']['url'], 'https://clients.haresign.net')

    def test_names_are_defined_once(self):
        """Every name on the page comes from the registry, so a rename is one
        edit. content.py must not carry a second copy."""
        from web import content

        source = (content.__file__ and open(content.__file__).read()) or ''
        for name in self.AGREED:
            self.assertNotIn(name, source)


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

        for slug in ('consulting', 'intelligence', 'community', 'workspace',
                     'account', 'api'):
            self.assertTrue(registry[slug]['url'].startswith('https://'))
