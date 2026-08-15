"""The newsletter archive, and the rule that this app cannot send.

The second is the one worth having a test for: importing 175 real subscribers
makes "no send path exists" a claim with consequences, and a claim with
consequences should fail loudly rather than be remembered.
"""
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from insights.models import Article
from newsletter.models import Issue


def make_issue(**kwargs):
    defaults = {
        'title': 'Issue 1',
        'slug': 'issue-1',
        'subject': 'What changed in the GP contract',
        'body_html': '<p>The issue body.</p>',
        'sent_at': timezone.now(),
    }
    defaults.update(kwargs)
    return Issue.objects.create(**defaults)


class ArchiveVisibilityTests(TestCase):
    """A draft is unfinished writing. It must not be findable."""

    def setUp(self):
        self.sent = make_issue()
        self.draft = make_issue(title='Draft', slug='draft-issue', sent_at=None)

    def test_the_index_lists_sent_issues(self):
        response = self.client.get(reverse('newsletter:issues'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.sent.subject)

    def test_the_index_hides_drafts(self):
        body = self.client.get(reverse('newsletter:issues')).content.decode()

        self.assertNotIn('Draft', body)

    def test_a_draft_404s_rather_than_explaining_itself(self):
        """Exactly as an unknown slug does — a "not sent yet" page would confirm
        the issue exists."""
        response = self.client.get(
            reverse('newsletter:issue', kwargs={'slug': 'draft-issue'}))

        self.assertEqual(response.status_code, 404)

    def test_a_sent_issue_renders(self):
        response = self.client.get(
            reverse('newsletter:issue', kwargs={'slug': 'issue-1'}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The issue body.')

    def test_the_body_uses_the_shared_prose_component(self):
        response = self.client.get(
            reverse('newsletter:issue', kwargs={'slug': 'issue-1'}))

        self.assertContains(response, 'hs-prose')

    def test_one_h1_per_page(self):
        for path in (reverse('newsletter:issues'),
                     reverse('newsletter:issue', kwargs={'slug': 'issue-1'})):
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.get(path).content.decode().count('<h1'), 1)

    def test_the_archive_routes_do_not_shadow_subscribe(self):
        """`<slug:slug>/` is last in the URLconf for this reason: it would
        otherwise swallow /newsletter/subscribe/."""
        response = self.client.get(reverse('newsletter:subscribe'))

        self.assertEqual(response.status_code, 405)   # POST-only, not a 404


class ArchiveArticleTests(TestCase):
    def setUp(self):
        self.issue = make_issue()
        self.live = Article.objects.create(
            title='A live article', slug='live', summary='S', body='<p>B</p>',
            status=Article.STATUS_PUBLISHED, published_at=timezone.now())
        self.archived = Article.objects.create(
            title='An archived article', slug='archived', summary='S', body='<p>B</p>',
            status=Article.STATUS_ARCHIVED)
        self.issue.articles.set([self.live, self.archived])

    def test_the_reading_list_is_shown(self):
        response = self.client.get(
            reverse('newsletter:issue', kwargs={'slug': 'issue-1'}))

        self.assertContains(response, 'A live article')

    def test_it_is_re_resolved_rather_than_trusted(self):
        """An issue may name an article since archived. The archive must not
        become a back door to unpublished work."""
        response = self.client.get(
            reverse('newsletter:issue', kwargs={'slug': 'issue-1'}))

        self.assertNotContains(response, 'An archived article')


class SendingStaysDisabledTests(TestCase):
    """This application collects and archives. It cannot send.

    With 175 real subscribers now imported, the cost of that becoming untrue by
    accident is somebody's inbox — so it is asserted rather than trusted.
    """

    def test_the_email_backend_discards_rather_than_sends(self):
        """Structural, not merely absent.

        Django's default EMAIL_HOST is "localhost", so "no host configured" was
        never the fact it looked like. The dummy backend is the real guarantee:
        anything that tried to send would discard instead of reaching a mail
        server, and changing that line is the deliberate act that moving sending
        here would require.

        Read from the settings *module*, not from `django.conf.settings`: the
        test runner replaces EMAIL_BACKEND with the locmem backend so tests can
        inspect `mail.outbox`, which means the live value is invisible from
        inside a test. Asserting the running value would only ever confirm what
        the runner did.
        """
        from django.conf import settings

        from config import settings as shipped

        self.assertEqual(shipped.EMAIL_BACKEND,
                         'django.core.mail.backends.dummy.EmailBackend')
        self.assertFalse(getattr(settings, 'EMAIL_HOST_USER', ''))

    def test_no_queue_or_scheduler_is_installed(self):
        from django.conf import settings

        for app in ('django_q', 'celery', 'django_celery_beat', 'huey'):
            self.assertNotIn(app, settings.INSTALLED_APPS)

    def test_nothing_in_this_app_imports_djangos_mail(self):
        """The direct check. A send would have to come through here."""
        import pathlib

        for module in pathlib.Path('newsletter').rglob('*.py'):
            # The test modules name these strings in order to forbid them.
            if module.name.startswith('test'):
                continue
            source = module.read_text()
            with self.subTest(module=str(module)):
                self.assertNotIn('django.core.mail', source)
                self.assertNotIn('send_mail', source)
                self.assertNotIn('EmailMessage', source)

    def test_the_admin_offers_no_bulk_action(self):
        """A list mailed from two systems is a list mailed twice."""
        from newsletter.admin import IssueAdmin, SubscriberAdmin

        self.assertIsNone(SubscriberAdmin.actions)
        self.assertIsNone(IssueAdmin.actions)


class MigrationProvenanceTests(TestCase):
    def test_legacy_identifiers_are_never_public(self):
        """They exist for import safety. Publishing a monolith primary key
        leaks the shape of another system for no reader's benefit."""
        issue = make_issue(legacy_id=4, legacy_path='/newsletter/archive/issue-1/')

        body = self.client.get(
            reverse('newsletter:issue', kwargs={'slug': issue.slug})).content.decode()

        self.assertNotIn('legacy_id', body)
        self.assertNotIn('/newsletter/archive/', body)

    def test_an_imported_issue_keeps_its_own_dates(self):
        """created_at is not auto_now_add, so a migrated issue does not claim to
        have been written on migration day."""
        from datetime import datetime

        stamp = timezone.make_aware(datetime(2026, 4, 1, 9, 0))
        issue = make_issue(created_at=stamp, sent_at=stamp)

        self.assertEqual(Issue.objects.get(pk=issue.pk).created_at, stamp)
