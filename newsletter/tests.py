"""Tests for the newsletter.

The behaviour worth pinning down here is mostly what the endpoint *refuses* to
reveal, and the boundary: this list is Web's own and nothing reaches across to
another Haresign service to maintain it.
"""
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from newsletter.models import Subscriber


class SubscribeTests(TestCase):
    def setUp(self):
        # The rate limiter is a cache counter keyed by IP, and every test client
        # request comes from the same one. Without this, tests interfere.
        cache.clear()

    def post(self, **data):
        payload = {'email': 'someone@example.nhs.uk'}
        payload.update(data)
        return self.client.post(reverse('newsletter:subscribe'), payload)

    def test_a_valid_address_is_added(self):
        response = self.post(name='Sam')

        self.assertEqual(response.status_code, 200)
        subscriber = Subscriber.objects.get()
        self.assertEqual(subscriber.email, 'someone@example.nhs.uk')
        self.assertEqual(subscriber.name, 'Sam')
        self.assertTrue(subscriber.active)

    def test_email_is_normalised(self):
        """Otherwise Someone@…, someone@… and SOMEONE@… are three subscribers
        who each get three copies of every email."""
        self.post(email='  SoMeOne@Example.NHS.uk ')

        self.assertEqual(Subscriber.objects.get().email, 'someone@example.nhs.uk')

    def test_subscribing_twice_is_harmless(self):
        self.post()
        self.post()

        self.assertEqual(Subscriber.objects.count(), 1)

    def test_an_already_subscribed_address_is_indistinguishable_from_a_new_one(self):
        """The endpoint must not answer "is this person on the Haresign list?".

        Same status and same body either way — this is the whole reason the view
        does not use a ModelForm, whose unique-field error would say so outright.
        """
        first = self.post()
        second = self.post()

        self.assertEqual(first.status_code, second.status_code)
        self.assertEqual(first.content, second.content)

    def test_someone_who_left_and_came_back_is_reactivated(self):
        self.post()
        Subscriber.objects.update(active=False)

        self.post()

        self.assertTrue(Subscriber.objects.get().active)

    def test_a_malformed_address_is_rejected(self):
        response = self.post(email='not-an-address')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Subscriber.objects.exists())

    def test_the_honeypot_is_accepted_but_stores_nothing(self):
        """A bot told it failed simply tries again, so it is told it worked."""
        response = self.post(website='http://spam.example.com')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Subscriber.objects.exists())

    def test_the_source_is_recorded(self):
        self.post(source='article')

        self.assertEqual(Subscriber.objects.get().source, 'article')

    def test_repeated_attempts_are_rate_limited(self):
        for index in range(5):
            self.post(email=f'person{index}@example.nhs.uk')

        response = self.post(email='sixth@example.nhs.uk')

        self.assertEqual(response.status_code, 429)
        self.assertEqual(Subscriber.objects.count(), 5)

    def test_get_is_not_allowed(self):
        """A subscribe that works over GET can be triggered by an <img> tag."""
        response = self.client.get(reverse('newsletter:subscribe'))

        self.assertEqual(response.status_code, 405)


class UnsubscribeTests(TestCase):
    def setUp(self):
        self.subscriber = Subscriber.objects.create(email='someone@example.nhs.uk')
        self.url = reverse('newsletter:unsubscribe',
                           kwargs={'token': self.subscriber.unsubscribe_token})

    def test_a_get_only_offers_to_unsubscribe(self):
        """Mail clients and security scanners follow links in email without a
        person being involved. A GET that unsubscribed would quietly remove
        people who never clicked anything."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.subscriber.refresh_from_db()
        self.assertTrue(self.subscriber.active)

    def test_a_post_unsubscribes(self):
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 200)
        self.subscriber.refresh_from_db()
        self.assertFalse(self.subscriber.active)

    def test_the_row_is_kept_so_a_later_import_cannot_resurrect_them(self):
        self.client.post(self.url)

        self.assertTrue(Subscriber.objects.filter(pk=self.subscriber.pk).exists())

    def test_unsubscribing_needs_no_account(self):
        """Somebody who no longer wants our email must not have to make an
        account to say so."""
        self.assertNotIn('Location', self.client.get(self.url))

    def test_an_unknown_token_404s(self):
        response = self.client.get(reverse(
            'newsletter:unsubscribe',
            kwargs={'token': '00000000-0000-0000-0000-000000000000'}))

        self.assertEqual(response.status_code, 404)

    def test_a_second_visit_says_so_rather_than_erroring(self):
        self.client.post(self.url)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already unsubscribed')


class NewsletterComponentTests(TestCase):
    """The reusable block, checked where it is actually placed."""

    PLACEMENTS = ['/', '/insights/']

    def test_the_form_appears_where_it_should(self):
        for path in self.PLACEMENTS:
            with self.subTest(path=path):
                response = self.client.get(path)

                self.assertContains(response, 'hs-newsletter')
                self.assertContains(response, reverse('newsletter:subscribe'))

    def test_the_form_records_where_it_was_shown(self):
        body = self.client.get('/').content.decode()

        self.assertIn('name="source" value="home"', body)

    def test_the_email_field_has_a_real_label_not_just_a_placeholder(self):
        """A placeholder vanishes the moment you type, leaving anyone who loses
        their place with an unlabelled box."""
        body = self.client.get('/').content.decode()

        self.assertIn('<label class="hs-visually-hidden" for="nl-email-home">', body)
        self.assertIn('id="nl-email-home"', body)

    def test_the_honeypot_is_hidden_from_assistive_technology(self):
        """It is invisible to people either way; what matters is that a screen
        reader user is not asked to fill in a field that must stay empty."""
        body = self.client.get('/').content.decode()

        self.assertIn('hs-newsletter__trap', body)
        self.assertIn('tabindex="-1"', body)

    def test_the_block_links_to_the_privacy_notice(self):
        self.assertContains(self.client.get('/'), 'href="/privacy/"')


class BoundaryTests(TestCase):
    """The list is Web's own, and integration is a file rather than a
    connection."""

    def test_the_model_lives_in_this_repository(self):
        self.assertEqual(Subscriber._meta.app_label, 'newsletter')

    def test_field_names_match_the_monolith_so_a_merge_needs_no_mapping(self):
        """These names are `website.NewsletterSubscriber`'s. Keeping them is what
        makes the eventual merge a row copy rather than a migration script."""
        fields = {field.name for field in Subscriber._meta.get_fields()}

        self.assertTrue(
            {'email', 'name', 'subscribed_at', 'active', 'unsubscribe_token'}
            <= fields)

    def test_export_produces_the_shared_shape(self):
        import json
        from io import StringIO

        from django.core.management import call_command

        Subscriber.objects.create(email='a@example.nhs.uk', name='A')
        out = StringIO()
        call_command('export_subscribers', stdout=out)

        rows = json.loads(out.getvalue())
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            set(rows[0]),
            {'email', 'name', 'subscribed_at', 'active', 'unsubscribe_token', 'source'})

    def test_export_omits_people_who_unsubscribed(self):
        """Exporting an opted-out row is how somebody gets mailed again after
        asking not to be."""
        import json
        from io import StringIO

        from django.core.management import call_command

        Subscriber.objects.create(email='gone@example.nhs.uk', active=False)
        out = StringIO()
        call_command('export_subscribers', stdout=out)

        self.assertEqual(json.loads(out.getvalue()), [])


class LegacyImportTests(TestCase):
    """The subscriber importer, and the three rules that matter.

    Written against small synthetic exports rather than the real 175-row file:
    the file is personal data and does not belong in a test fixture.
    """

    def _run(self, rows, **options):
        import json
        import tempfile
        from io import StringIO

        from django.core.management import call_command

        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as handle:
            json.dump({'subscribers': rows}, handle)
            path = handle.name

        out = StringIO()
        call_command('import_legacy_subscribers', path, stdout=out, **options)
        return out.getvalue()

    def test_active_and_unsubscribed_rows_are_both_imported(self):
        """Importing only the active list is precisely how somebody who opted
        out gets mailed again."""
        self._run([
            {'legacy_id': 1, 'email': 'a@example.nhs.uk', 'active': True},
            {'legacy_id': 2, 'email': 'b@example.nhs.uk', 'active': False},
        ])

        self.assertEqual(Subscriber.objects.count(), 2)
        self.assertFalse(Subscriber.objects.get(email='b@example.nhs.uk').active)

    def test_a_local_unsubscribe_outranks_a_source_that_says_active(self):
        """The export may simply predate the unsubscribe. The safe direction of
        that disagreement is obvious."""
        Subscriber.objects.create(
            email='gone@example.nhs.uk', active=False, legacy_id=7)

        output = self._run([
            {'legacy_id': 7, 'email': 'gone@example.nhs.uk', 'active': True}])

        self.assertFalse(Subscriber.objects.get(email='gone@example.nhs.uk').active)
        self.assertIn('kept local unsubscribe', output)

    def test_a_source_unsubscribe_deactivates_a_local_active_row(self):
        Subscriber.objects.create(email='left@example.nhs.uk', legacy_id=8)

        self._run([{'legacy_id': 8, 'email': 'left@example.nhs.uk', 'active': False}])

        self.assertFalse(Subscriber.objects.get(email='left@example.nhs.uk').active)

    def test_email_matching_is_case_insensitive(self):
        """One person, one inbox — whatever case the source stored."""
        Subscriber.objects.create(email='person@example.nhs.uk')

        self._run([{'legacy_id': 3, 'email': 'Person@Example.NHS.uk', 'active': True}])

        self.assertEqual(Subscriber.objects.count(), 1)

    def test_the_unsubscribe_token_is_carried_over(self):
        """The single most important field in the export: without it, the
        unsubscribe link in every already-sent email stops working at cutover."""
        token = '11111111-2222-3333-4444-555555555555'

        self._run([{'legacy_id': 4, 'email': 'c@example.nhs.uk',
                    'active': True, 'unsubscribe_token': token}])

        self.assertEqual(
            str(Subscriber.objects.get(email='c@example.nhs.uk').unsubscribe_token),
            token)

    def test_the_original_subscribed_date_is_preserved(self):
        """subscribed_at is auto_now_add, so it has to be written afterwards —
        otherwise every migrated row claims to have subscribed on migration day."""
        self._run([{'legacy_id': 5, 'email': 'd@example.nhs.uk', 'active': True,
                    'subscribed_at': '2026-01-15T10:30:00+00:00'}])

        self.assertEqual(
            Subscriber.objects.get(email='d@example.nhs.uk').subscribed_at.year, 2026)

    def test_no_unsubscribe_date_is_invented(self):
        """The monolith records none. Stamping the migration date would
        manufacture a consent record that does not exist."""
        self._run([{'legacy_id': 6, 'email': 'e@example.nhs.uk', 'active': False}])

        self.assertIsNone(
            Subscriber.objects.get(email='e@example.nhs.uk').unsubscribed_at)

    def test_invalid_addresses_are_reported_not_imported(self):
        output = self._run([
            {'legacy_id': 9, 'email': 'not-an-address', 'active': True},
            {'legacy_id': 10, 'email': '', 'active': True},
        ])

        self.assertEqual(Subscriber.objects.count(), 0)
        self.assertIn('invalid', output.lower())

    def test_duplicates_in_the_source_are_reported(self):
        output = self._run([
            {'legacy_id': 11, 'email': 'dup@example.nhs.uk', 'active': True},
            {'legacy_id': 12, 'email': 'DUP@example.nhs.uk', 'active': True},
        ])

        self.assertEqual(Subscriber.objects.count(), 1)
        self.assertIn('duplicate', output.lower())

    def test_it_is_idempotent(self):
        rows = [{'legacy_id': 13, 'email': 'f@example.nhs.uk', 'active': True}]

        self._run(rows)
        self._run(rows)

        self.assertEqual(Subscriber.objects.count(), 1)

    def test_dry_run_writes_nothing(self):
        self._run([{'legacy_id': 14, 'email': 'g@example.nhs.uk', 'active': True}],
                  dry_run=True)

        self.assertEqual(Subscriber.objects.count(), 0)

    def test_unsubscribing_here_records_when(self):
        """Unlike migrated rows, an unsubscribe that happens on this site has a
        real date to record."""
        subscriber = Subscriber.objects.create(email='h@example.nhs.uk')

        self.client.post(reverse('newsletter:unsubscribe',
                                 kwargs={'token': subscriber.unsubscribe_token}))

        subscriber.refresh_from_db()
        self.assertFalse(subscriber.active)
        self.assertIsNotNone(subscriber.unsubscribed_at)
