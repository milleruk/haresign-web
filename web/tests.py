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
from web.content import HERO_SLIDES
from web.views import build_hero_slides, build_platform_cards


class HomePageTests(TestCase):
    def test_renders(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'web/home.html')

    def test_leads_with_the_growth_message(self):
        response = self.client.get('/')

        self.assertContains(response, 'Haresign')
        # "grown" closes the line in its own element, not just present in text.
        self.assertContains(response, '<span class="hs-hero__accent">grown.</span>')
        self.assertContains(response, 'Four platforms. One purpose.')

    def test_banner_carries_every_slide_and_its_destination(self):
        """Each frame reaches the page with its copy and a resolved link.

        `href` is built in the view, so a slide pointing at a route that has
        been renamed fails here rather than rendering an empty href.
        """
        response = self.client.get('/')

        for item in build_hero_slides():
            self.assertContains(response, item['slide'].body)
            self.assertContains(response, item['slide'].cta)
            self.assertContains(response, f'href="{item["href"]}"')

    def test_banner_photographs_are_decorative_and_offered_as_webp(self):
        """The images illustrate the words rather than adding to them, so they
        carry an empty alt — and each is offered as WebP with a JPEG behind it,
        as the insights images are."""
        body = self.client.get('/').content.decode()

        for item in build_hero_slides():
            self.assertIn(f'{item["slide"].image}-1600', body)
            self.assertIn(f'{item["slide"].image}-900', body)
        self.assertIn('type="image/webp"', body)
        self.assertEqual(body.count('class="hs-hero__image" alt=""'), len(HERO_SLIDES))

    def test_shows_every_platform_with_its_copy(self):
        response = self.client.get('/')

        for card in build_platform_cards():
            self.assertContains(response, card['name'])
            self.assertContains(response, card['platform'].blurb)
            self.assertContains(response, card['platform'].cta)

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
            ('hs-ecosystem"', 'ecosystem band'),
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
        white-ink file. Both the header and the footer are dark now — the header
        is navy when solid and sits on a darkened photograph when transparent —
        so both take the white-ink file. Get it wrong and the logo is invisible
        rather than obviously broken, which no other test would catch."""
        body = self.client.get('/').content.decode()
        header, _, footer = body.partition('<footer')

        # Matched on the stem with its trailing dot, because WhiteNoise's
        # manifest storage inserts a content hash before the extension
        # ("logo-primary.edeb55afdd97.png"). "logo-primary." cannot match
        # "logo-primary-dark.…", which is what makes the pair distinguishable.
        self.assertIn('logo-primary-dark.', header)
        self.assertNotIn('logo-primary.', header)
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
        edit. content.py must not carry a second copy.

        Asserted against the module's *values* rather than its source text. An
        earlier version scanned the file and so also read the comments, which
        made an explanatory note mentioning a product name fail a test about
        data — punishing the documentation for describing the rule it enforces.
        """
        from web import content

        copy = []
        for platform in content.PLATFORMS:
            copy += [platform.blurb, platform.cta] + list(platform.areas)
        for item in content.CREDIBILITY:
            copy += [item['heading'], item['body'], item['proof']]
        for route in content.ECOSYSTEM_ROUTES:
            copy += [route['service'], route['action']]

        for text in copy:
            for name in self.AGREED:
                self.assertNotIn(name, text)


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


class LegalPageTests(TestCase):
    """The four policy pages.

    Their content is a legal matter and not something a test can validate, so
    what is asserted here is everything mechanical: that they resolve, that they
    are public, that the shell is wired to the metadata, and that no link on
    them is broken.
    """

    PAGES = {
        'privacy': ('/privacy/', 'Privacy Notice'),
        'cookies': ('/cookies/', 'Cookie Policy'),
        'terms': ('/terms/', 'Terms of Use'),
        'accessibility': ('/accessibility/', 'Accessibility Statement'),
    }

    def test_all_four_routes_resolve(self):
        for slug, (path, title) in self.PAGES.items():
            with self.subTest(slug=slug):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, title)

    def test_each_page_uses_its_own_template_and_the_shared_shell(self):
        for slug, (path, _) in self.PAGES.items():
            with self.subTest(slug=slug):
                response = self.client.get(path)

                self.assertTemplateUsed(response, f'web/legal/{slug}.html')
                self.assertTemplateUsed(response, 'web/legal/base.html')
                self.assertTemplateUsed(response, 'web/base.html')

    def test_pages_are_public(self):
        """A privacy notice behind a login is not a privacy notice. Nothing here
        may ever redirect to an auth flow."""
        for slug, (path, _) in self.PAGES.items():
            with self.subTest(slug=slug):
                response = self.client.get(path)

                self.assertEqual(response.status_code, 200)
                self.assertNotIn('Location', response)

    def test_titles_and_descriptions_are_unique_per_page(self):
        titles, descriptions = set(), set()
        for slug, (path, _) in self.PAGES.items():
            body = self.client.get(path).content.decode()
            titles.add(re.search(r'<title>(.*?)</title>', body, re.S).group(1).strip())
            descriptions.add(
                re.search(r'<meta name="description" content="(.*?)"', body, re.S).group(1))

        self.assertEqual(len(titles), 4)
        self.assertEqual(len(descriptions), 4)

    def test_canonical_uses_the_configured_origin(self):
        response = self.client.get('/privacy/')

        self.assertContains(
            response, f'href="{settings.SITE_BASE_URL}/privacy/"')

    def test_open_graph_metadata_is_present(self):
        body = self.client.get('/terms/').content.decode()

        self.assertIn('property="og:title"', body)
        self.assertIn('property="og:description"', body)
        self.assertIn('Terms of Use', body)

    def test_beta_noindex_behaviour_is_unchanged(self):
        """Legal pages must follow the same environment-driven rule as the rest
        of the site, so beta cannot be indexed by adding a page."""
        for slug, (path, _) in self.PAGES.items():
            with self.subTest(slug=slug):
                self.assertContains(self.client.get(path), 'noindex, nofollow')

    @override_settings(SITE_INDEXABLE=True)
    def test_legal_pages_are_indexable_in_production(self):
        for slug, (path, _) in self.PAGES.items():
            with self.subTest(slug=slug):
                self.assertNotContains(self.client.get(path), 'noindex')

    def test_footer_links_to_every_legal_page(self):
        """Checked on the homepage, so a broken footer link is caught wherever
        the footer appears."""
        body = self.client.get('/').content.decode()

        for slug, (path, _) in self.PAGES.items():
            with self.subTest(slug=slug):
                self.assertIn(f'href="{path}"', body)

    def test_footer_has_no_placeholder_legal_links_left(self):
        """Scoped to the Legal list: "Soon" is still correct in the Platforms and
        Account columns, where the services genuinely are not live."""
        body = self.client.get('/').content.decode()
        start = body.index('aria-labelledby="footer-legal"')
        legal_list = body[start:body.index('</ul>', start)]

        self.assertNotIn('Soon', legal_list)
        self.assertEqual(legal_list.count('<a href="/'), 4)

    def test_contents_anchors_all_exist(self):
        """Every contents entry must point at a heading that is really there —
        otherwise renaming a section silently breaks the nav."""
        from web.legal import LEGAL_PAGES

        for slug, (path, _) in self.PAGES.items():
            body = self.client.get(path).content.decode()
            for anchor, label in LEGAL_PAGES[slug]['sections']:
                with self.subTest(slug=slug, anchor=anchor):
                    self.assertIn(f'href="#{anchor}"', body)
                    self.assertIn(f'id="{anchor}"', body)

    def test_pages_cross_link_to_the_others_but_not_to_themselves(self):
        for slug, (path, _) in self.PAGES.items():
            with self.subTest(slug=slug):
                body = self.client.get(path).content.decode()
                # Just the related block — slicing to the end of the document
                # would include the footer, which links to all four.
                start = body.index('hs-legal-related__list')
                related = body[start:body.index('</ul>', start)]

                for other, (other_path, _) in self.PAGES.items():
                    if other == slug:
                        self.assertNotIn(f'href="{other_path}"', related)
                    else:
                        self.assertIn(f'href="{other_path}"', related)

    def test_body_uses_the_shared_prose_component(self):
        """Legal pages read as documents, using the same long-form styling as
        articles rather than a second copy of it."""
        response = self.client.get('/privacy/')

        self.assertContains(response, 'hs-prose')
        self.assertContains(response, 'hs-container--reading')

    def test_pages_have_exactly_one_h1(self):
        for slug, (path, _) in self.PAGES.items():
            with self.subTest(slug=slug):
                self.assertEqual(
                    self.client.get(path).content.decode().count('<h1'), 1)

    def test_no_template_syntax_leaks(self):
        for slug, (path, _) in self.PAGES.items():
            with self.subTest(slug=slug):
                body = self.client.get(path).content.decode()
                for token in ('{#', '{%', '{{'):
                    self.assertNotIn(token, body)

    def test_unknown_legal_slug_404s(self):
        from django.http import Http404
        from django.test import RequestFactory

        from web.views import legal_page

        with self.assertRaises(Http404):
            legal_page(RequestFactory().get('/nope/'), slug='nope')

    def test_the_only_cookie_is_the_one_the_policy_names(self):
        """The site's cookie position changed with the newsletter, and it changed
        honestly rather than the form being smuggled in.

        A page carrying the newsletter form sets `csrftoken` — strictly
        necessary, so no consent is required — and the Cookie Policy names it and
        says which pages set it. Nothing else is set, and if anything else ever
        is, this fails before the policy becomes untrue.
        """
        response = self.client.get('/')

        for cookie in response.cookies:
            self.assertEqual(cookie, 'csrftoken')

    def test_a_page_without_the_form_still_sets_nothing(self):
        """Which is precisely the distinction the Cookie Policy draws, so it has
        to be true."""
        response = self.client.get('/privacy/')

        self.assertEqual(len(response.cookies), 0)

    def test_the_cookie_policy_names_the_cookie_that_is_actually_set(self):
        body = self.client.get('/cookies/').content.decode()

        self.assertIn('csrftoken', body)

    def test_no_analytics_and_no_external_requests(self):
        """Nothing measures visitors and nothing is loaded from a third party.
        The Privacy Notice, the Cookie Policy and the Accessibility Statement all
        say so, so all three depend on this."""
        body = self.client.get('/').content.decode()

        for external in ('googletagmanager', 'google-analytics', 'gtag(',
                         'fonts.googleapis.com', 'cdn.jsdelivr', 'unpkg.com'):
            self.assertNotIn(external, body)


class FaqPageTests(TestCase):
    """The umbrella FAQ.

    The content is a product decision and not something a test can validate. What
    is asserted here is the mechanics — that it resolves, that every answer is in
    the page whether or not it is expanded, and that it stays an *ecosystem* FAQ
    rather than drifting into consulting's territory.
    """

    def test_route_resolves(self):
        response = self.client.get('/faq/')

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'web/faq.html')

    def test_every_question_and_answer_reaches_the_page(self):
        """A `<details>` keeps its content in the DOM whether open or not, which
        is exactly why it was chosen over a JavaScript accordion: closed answers
        are still readable, searchable and crawlable."""
        from web.faq import all_questions

        body = self.client.get('/faq/').content.decode()
        for question in all_questions():
            with self.subTest(anchor=question.anchor):
                self.assertIn(question.question, body)
                for paragraph in question.answer:
                    self.assertIn(paragraph, body)

    def test_answers_work_without_javascript(self):
        """<details>/<summary> is browser-native. If this ever becomes a div
        with a click handler, the answers vanish for anyone without JS."""
        body = self.client.get('/faq/').content.decode()

        self.assertIn('<details', body)
        self.assertIn('<summary', body)
        self.assertNotIn('<script', body[body.index('<main'):body.index('</main>')])

    def test_the_first_question_of_each_section_is_open(self):
        """An accordion where everything is shut reads as an empty page."""
        body = self.client.get('/faq/').content.decode()

        self.assertIn('open>', body.replace(' open>', 'open>'))

    def test_every_question_has_a_stable_anchor(self):
        from web.faq import all_questions

        body = self.client.get('/faq/').content.decode()
        for question in all_questions():
            with self.subTest(anchor=question.anchor):
                self.assertIn(f'id="{question.anchor}"', body)

    def test_contents_links_point_at_sections_that_exist(self):
        from web.faq import FAQ_SECTIONS

        body = self.client.get('/faq/').content.decode()
        for section in FAQ_SECTIONS:
            with self.subTest(section=section.anchor):
                self.assertIn(f'href="#{section.anchor}"', body)
                self.assertIn(f'id="{section.anchor}"', body)

    def test_it_stays_an_ecosystem_faq(self):
        """Consulting's own FAQs — engagements, day rates, the client portal —
        belong to Haresign Consulting. Copying them here would rebuild the mixed
        old homepage this architecture exists to separate."""
        body = self.client.get('/faq/').content.decode().lower()

        for consulting_topic in ('day rate', 'day-rate', 'retainer',
                                 'engagement typically', 'pricing look like'):
            self.assertNotIn(consulting_topic, body)

    def test_platform_questions_link_to_live_platforms_only(self):
        """The availability rule holds here as everywhere: Intelligence is live
        and linked, Consulting is not and must not be."""
        body = self.client.get('/faq/').content.decode()

        self.assertIn('href="https://app.haresign.net"', body)
        self.assertNotIn('href="https://consulting.haresign.net"', body)

    def test_the_nhs_answer_is_unambiguous(self):
        """The one question where a vague answer would be a real problem."""
        response = self.client.get('/faq/')

        self.assertContains(response, 'Is Haresign part of the NHS?')
        self.assertContains(response, 'not part of the NHS')

    def test_no_faq_structured_data(self):
        """Deliberate: Google restricted FAQ rich results to government and
        health bodies, so the markup is now pure maintenance cost — and the
        standing risk with it is the structured copy drifting from the visible
        copy. If it is ever added, it must be generated from FAQ_SECTIONS."""
        body = self.client.get('/faq/').content.decode()

        self.assertNotIn('FAQPage', body)

    def test_page_has_exactly_one_h1(self):
        self.assertEqual(self.client.get('/faq/').content.decode().count('<h1'), 1)

    def test_no_inline_styles(self):
        body = self.client.get('/faq/').content.decode()

        self.assertNotIn('<style', body)
        self.assertNotIn('style="', body)


class ContactPageTests(TestCase):
    """The contact routing page."""

    def test_route_resolves(self):
        response = self.client.get('/contact/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Talk to Haresign')

    def test_every_route_is_offered(self):
        from web.contact import CONTACT_ROUTES

        body = self.client.get('/contact/').content.decode()
        for route in CONTACT_ROUTES:
            with self.subTest(route=route.anchor):
                self.assertIn(route.heading, body)
                self.assertIn(route.blurb, body)

    def test_each_route_carries_its_own_prefilled_subject(self):
        """Five routes into one inbox are only better than one if the subject
        line tells them apart — that is the entire mechanism."""
        from urllib.parse import quote

        from web.contact import CONTACT_ROUTES

        body = self.client.get('/contact/').content.decode()
        subjects = {route.subject for route in CONTACT_ROUTES}
        self.assertEqual(len(subjects), len(CONTACT_ROUTES))
        for subject in subjects:
            self.assertIn(f'subject={quote(subject)}', body)

    def test_there_is_no_form(self):
        """Deliberate, and the Privacy Notice depends on it: it states that this
        site has no general-enquiry form. Adding one here without updating that
        page would make the privacy notice untrue."""
        body = self.client.get('/contact/').content.decode()
        main = body[body.index('<main'):body.index('</main>')]

        self.assertNotIn('<form', main)
        self.assertNotIn('<input', main)

    def test_routes_to_unlaunched_platforms_are_not_links(self):
        body = self.client.get('/contact/').content.decode()

        self.assertNotIn('href="https://consulting.haresign.net"', body)
        self.assertNotIn('href="https://clients.haresign.net"', body)

    def test_the_general_route_is_reachable_from_the_hero(self):
        """"Not sure which?" has to go somewhere, or the page has made the
        visitor do the routing it exists to do for them."""
        response = self.client.get('/contact/')

        self.assertContains(response, 'href="#general"')
        self.assertContains(response, 'id="general"')

    def test_page_has_exactly_one_h1(self):
        self.assertEqual(self.client.get('/contact/').content.decode().count('<h1'), 1)


class CredibilityTests(TestCase):
    """One section where there were two.

    The page carried an abstract principles band *and* a strip of the facts
    behind it, saying the same four things twice. They are merged: each item
    states the principle and prints the evidence.
    """

    def test_the_merged_section_is_on_the_page(self):
        from web.content import CREDIBILITY

        response = self.client.get('/')

        self.assertContains(response, 'Built around primary care.')
        for item in CREDIBILITY:
            self.assertContains(response, item['heading'])
            self.assertContains(response, item['body'])
            self.assertContains(response, item['proof'])

    def test_the_duplicate_section_is_gone(self):
        """Both bands rendered four near-identical claims. If a second one comes
        back, this fails."""
        body = self.client.get('/').content.decode()

        self.assertEqual(body.count('hs-credibility"'), 1)
        self.assertNotIn('hs-principles-grid', body)
        self.assertNotIn('Built around what matters in primary care.', body)

    def test_it_is_not_a_biography(self):
        """The umbrella page says Haresign is founder-led and links onward. The
        people belong to Haresign Consulting."""
        body = self.client.get('/').content.decode()

        self.assertNotIn('Ben Haresign', body)
        self.assertNotIn('Benjamin', body)

    def test_the_people_link_respects_availability(self):
        """Consulting is not live, so "meet the people" is a label, not a link
        to a host that does not resolve."""
        response = self.client.get('/')

        self.assertContains(response, 'Meet the people behind Haresign')
        self.assertNotContains(response, 'href="https://consulting.haresign.net"')

    def test_no_invented_numbers(self):
        """Every claim in this section is one already published on haresign.net.
        Customer counts and performance figures are exactly what a credibility
        section invites, and there are none."""
        import re

        from web.content import CREDIBILITY

        for item in CREDIBILITY:
            with self.subTest(item=item['heading']):
                numbers = re.findall(r'\d+', item['body'])
                self.assertEqual(numbers, [], 'no numeric claim belongs in the body')


class EcosystemCtaTests(TestCase):
    """The pre-footer band: four routes in, rather than one funnel."""

    PLACEMENTS = ['/', '/faq/', '/insights/']

    def test_it_appears_where_a_page_needs_a_way_onward(self):
        for path in self.PLACEMENTS:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertContains(response, 'Find the right part of Haresign for you.')

    def test_it_offers_all_four_platforms(self):
        response = self.client.get('/')

        for name in ('Haresign Consulting', 'Haresign Intelligence',
                     'Haresign Community', 'Haresign Workspace'):
            self.assertContains(response, name)

    def test_the_names_and_urls_come_from_the_registry(self):
        """Not a second copy of the platform list. A rename or a subdomain move
        must not need this band edited."""
        from web.content import ECOSYSTEM_ROUTES

        registry = build_registry()
        for route in ECOSYSTEM_ROUTES:
            with self.subTest(service=route['service']):
                # The route names a registry slug and carries no name and no URL
                # of its own — that is what makes a rename or a subdomain move
                # one edit rather than two.
                self.assertIn(route['service'], registry)
                self.assertEqual(set(route), {'service', 'action'})
                self.assertNotIn('haresign.net', route['action'])

    def test_an_unlaunched_platform_is_named_but_not_linked(self):
        """Consulting and Workspace, since Community went live."""
        body = self.client.get('/').content.decode()

        self.assertNotIn('href="https://consulting.haresign.net"', body)
        self.assertNotIn('href="https://clients.haresign.net"', body)
        self.assertIn('hs-ecosystem__link--soon', body)

    def test_it_appears_once_per_page(self):
        for path in self.PLACEMENTS:
            with self.subTest(path=path):
                body = self.client.get(path).content.decode()

                self.assertEqual(body.count('hs-ecosystem"'), 1)

    def test_the_closing_strip_offers_a_real_direct_route(self):
        """"Contact Haresign directly" is a mailto, not a link to the form.

        The strip takes haresign.net's closing composition — direct contact, the
        question, one action — and the first of those three has to mean it. The
        address comes from settings.LEGAL, so it cannot drift from the footer's.
        """
        body = self.client.get('/').content.decode()

        self.assertIn(f'href="mailto:{settings.LEGAL["contact_email"]}"', body)
        self.assertIn('Not sure which part you need?', body)
        # The action is the arrow pill, on the contact page rather than a mailto:
        # a question that needs answering is not always an email.
        self.assertIn('hs-btn--arrow', body)

    def test_the_old_single_funnel_band_is_gone(self):
        """It offered "Open Intelligence" or "email us", which made the umbrella
        page a funnel into one platform."""
        body = self.client.get('/').content.decode()

        self.assertNotIn('hs-cta-band', body)
        self.assertNotIn('One Haresign. Wherever you start.', body)


class NavigationTests(TestCase):
    """No broken internal routes.

    The nav and footer used bare `#insights` / `#about` fragments, which are
    homepage section ids — on any other page they scrolled nowhere, and the
    footer is on every page.
    """

    PAGES = ['/', '/faq/', '/contact/', '/insights/', '/privacy/', '/cookies/',
             '/terms/', '/accessibility/']

    def test_every_public_page_resolves(self):
        for path in self.PAGES:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_no_page_links_to_a_bare_fragment_that_is_not_on_it(self):
        """Catches exactly the bug this test class is named for."""
        import re

        for path in self.PAGES:
            body = self.client.get(path).content.decode()
            for match in re.finditer(r'href="#([\w-]+)"', body):
                anchor = match.group(1)
                with self.subTest(path=path, anchor=anchor):
                    self.assertIn(f'id="{anchor}"', body,
                                  f'{path} links to #{anchor}, which is not on it')

    def test_internal_links_resolve(self):
        """Every same-site href on every page must be a real route."""
        import re

        from django.urls import Resolver404, resolve

        for path in self.PAGES:
            body = self.client.get(path).content.decode()
            for match in re.finditer(r'href="(/[^"#?]*)', body):
                target = match.group(1)
                with self.subTest(path=path, target=target):
                    if target.startswith('/static/'):
                        continue
                    try:
                        resolve(target)
                    except Resolver404:
                        self.fail(f'{path} links to {target}, which does not resolve')

    def test_the_nav_reaches_the_new_pages(self):
        body = self.client.get('/').content.decode()
        nav = body[body.index('<nav'):body.index('</nav>')]

        self.assertIn('href="/faq/"', nav)
        self.assertIn('href="/contact/"', nav)

    def test_the_footer_carries_the_agreed_information_architecture(self):
        body = self.client.get('/').content.decode()
        footer = body[body.index('<footer'):]

        for heading in ('Platforms', 'Haresign', 'Resources', 'Legal'):
            self.assertIn(f'>{heading}</h2>', footer)

    def test_documentation_is_linked_not_copied(self):
        """Web links to the service that owns the docs. If documentation ever
        appears *in* this repository, that is the boundary breaking."""
        import os

        body = self.client.get('/').content.decode()
        footer = body[body.index('<footer'):]

        self.assertIn('readthedocs.io', footer)
        self.assertFalse(os.path.exists('docs'),
                         'documentation belongs to the service that owns it')

    def test_documentation_is_attributed_to_the_service_that_owns_it(self):
        """It documents the platform, its tools and its data sources — that is
        Intelligence documentation, not ecosystem documentation."""
        body = self.client.get('/').content.decode()
        footer = body[body.index('<footer'):]

        start = footer.index('aria-labelledby="footer-resources"')
        resources = footer[start:footer.index('</ul>', start)]
        self.assertIn('Haresign Intelligence', resources)

    def test_documentation_is_not_in_the_main_nav(self):
        """Most visitors to an umbrella site are not looking for a tools manual."""
        body = self.client.get('/').content.decode()
        nav = body[body.index('<nav'):body.index('</nav>')]

        self.assertNotIn('readthedocs', nav)


class CommunityIsLiveTests(TestCase):
    """Haresign Community is live, and marking it so was one config change.

    The value of the registry is that this needed no template edit at all — the
    cards, the nav, the footer, the FAQ and the ecosystem band all ask it. These
    assertions are what prove that claim rather than just asserting it.
    """

    def test_the_registry_says_community_is_live(self):
        registry = build_registry()

        self.assertTrue(registry['community']['available'])
        self.assertEqual(registry['community']['url'], 'https://community.haresign.net')

    def test_it_is_linked_everywhere_the_registry_is_read(self):
        for path in ('/', '/faq/', '/insights/'):
            with self.subTest(path=path):
                self.assertContains(
                    self.client.get(path), 'href="https://community.haresign.net"')

    def test_no_coming_soon_is_left_against_community(self):
        """A live service still labelled "Soon" is worse than one that is not
        listed: it tells people not to click something that works."""
        body = self.client.get('/').content.decode()

        for marker in ('hs-nav__link--unavailable', 'hs-footer__link--unavailable',
                       'hs-ecosystem__link--soon'):
            for match in re.finditer(re.escape(marker) + r'[^<]*>([^<]*)', body):
                self.assertNotIn('Community', match.group(1))

    def test_the_status_is_not_hard_coded_in_any_template(self):
        """Grep, deliberately. A template that decides availability for itself
        cannot be flipped by configuration, which is the whole design."""
        import pathlib

        for template in pathlib.Path('web/templates').rglob('*.html'):
            source = template.read_text()
            with self.subTest(template=str(template)):
                self.assertNotIn('community.haresign.net', source)


class GoverningLawTests(TestCase):
    """The clause resolved in this task.

    Asserted because a legal commitment disappearing in an unrelated edit is
    exactly the kind of change that nothing else would catch.
    """

    def test_governing_law_is_stated(self):
        response = self.client.get('/terms/')

        self.assertContains(response, 'Governing law')
        self.assertContains(response, 'law of England and Wales')
        self.assertContains(response, 'courts of England and Wales')

    def test_no_todo_marker_survives_anywhere_in_the_legal_pages(self):
        for path in ('/terms/', '/privacy/', '/cookies/', '/accessibility/'):
            with self.subTest(path=path):
                body = self.client.get(path).content.decode()

                for marker in ('TODO', 'To be confirmed', 'hs-callout--todo',
                               'FIXME', 'placeholder'):
                    self.assertNotIn(marker, body)

    def test_the_consumer_right_is_preserved(self):
        """A UK consumer keeps the right to sue where they live whatever a
        website says. A clause claiming otherwise is unenforceable and reads as
        trying it on."""
        self.assertContains(self.client.get('/terms/'), 'country where you live')

    def test_website_terms_do_not_become_service_terms(self):
        """These are the terms of a website. They must not quietly become the
        terms of a consulting engagement or a subscription."""
        response = self.client.get('/terms/')

        self.assertContains(response, 'not the terms of any consulting')
