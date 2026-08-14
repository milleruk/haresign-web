"""Tests for the public web layer.

Page-rendering tests use `TestCase`: the homepage reads published articles from
the `insights` app, so rendering it touches the database. `DecouplingTests` stays
on `SimpleTestCase` because it only inspects settings — and keeping it there
means a future change that makes an architectural assertion hit the database
fails loudly instead of quietly acquiring a connection.

Insights behaviour itself is covered in `insights/tests.py`; what is tested here
is that the homepage renders whatever the seam returns.
"""
import re

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from config.services import build_registry
from web.content import PRINCIPLES
from web.views import build_platform_cards


class HomePageTests(TestCase):
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

    def test_page_landmarks_appear_exactly_once(self):
        """Guards against duplicated sections.

        A block of markup was once inserted before *every* `{% endblock %}`
        rather than the one closing `content`, so the CTA band rendered six
        times — including inside `page_css`, which put it in <head>, from where
        the browser hoisted it above the header. Django renders all of that
        without complaint, so only counting catches it.
        """
        body = self.client.get('/').content.decode()

        for marker, label in (
            ('<header', 'header'),
            ('<footer', 'footer'),
            ('<main', 'main'),
            ('hs-cta-band"', 'CTA band'),
            ('hs-hero"', 'hero'),
            ('hs-credibility"', 'credibility strip'),
            ('id="platforms"', 'platforms section'),
        ):
            self.assertEqual(body.count(marker), 1, f'{label} should appear once')

    def test_nothing_renders_before_the_header(self):
        """<head> blocks must not leak markup into the body. Anything emitted
        there is hoisted above the header by the browser, which is how the
        duplicate CTA band became visible."""
        body = self.client.get('/').content.decode()

        self.assertLess(body.index('<header'), body.index('<main'))
        # The only thing before the header is the skip link.
        before = body[body.index('<body'):body.index('<header')]
        self.assertNotIn('<section', before)
        self.assertNotIn('<h2', before)

    def test_head_blocks_contain_no_markup(self):
        """title/description/og_* are attribute and text content — a stray tag in
        them corrupts the metadata rather than erroring."""
        body = self.client.get('/').content.decode()
        head = body[:body.index('</head>')]

        title = re.search(r'<title>(.*?)</title>', head, re.S).group(1)
        self.assertNotIn('<', title)
        for match in re.finditer(r'<meta[^>]*content="([^"]*)"', head):
            self.assertNotIn('<section', match.group(1))

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


class PlatformAvailabilityTests(TestCase):
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


class NamingTests(TestCase):
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


class SeoTests(TestCase):
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


class HealthTests(TestCase):
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

    def test_exactly_one_database_and_it_is_this_apps_own(self):
        """The boundary moved but did not loosen.

        This app now has a database because it owns editorial content. What must
        stay true is that there is exactly *one*, that nothing configures a
        second connection to somebody else's, and that its name is not the
        monolith's. A second alias here would be the beginning of the shared
        backend this repository exists not to become.
        """
        self.assertEqual(list(settings.DATABASES), ['default'])
        self.assertNotIn(
            settings.DATABASES['default']['NAME'], {'haresign', 'haresign_net'},
            'This must not point at the monolith database.',
        )

    def test_no_model_is_imported_from_another_haresign_service(self):
        """Applications integrate through contracts, never by sharing models."""
        installed = set(settings.INSTALLED_APPS)
        for app in ('modules.core.website', 'modules.core.practicedata',
                    'modules.core.oauth_server'):
            self.assertNotIn(app, installed)

    def test_platform_urls_are_configuration(self):
        """Subdomains will move during the migration; nothing may hard-code one."""
        registry = build_registry()

        for slug in ('consulting', 'intelligence', 'community', 'workspace',
                     'account', 'api'):
            self.assertTrue(registry[slug]['url'].startswith('https://'))
