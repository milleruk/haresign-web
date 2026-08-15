"""The Haresign newsletter list.

**Why this lives here.** Under the ownership boundary, `haresign-web` owns public
editorial content, and the newsletter is the subscription to that content — it is
advertised beside Insights and it carries Insights. It belongs with Insights, not
with the consulting site or the tools platform.

**Why it is a new table rather than the monolith's.** The rule has not moved:
this application never connects to the monolith's database. The monolith's
`website.NewsletterSubscriber` keeps collecting on haresign.net until the cutover,
so for the moment two lists exist. That is deliberate and bounded rather than
accidental — see README, "Newsletter", for the migration plan. What makes it safe
is below.

**The fields are the monolith's fields, on purpose.** `email`, `name`,
`subscribed_at`, `active` and `unsubscribe_token` match
`modules/core/website/models.py` exactly, including the UUID default. A merge in
either direction is therefore a straight row copy with no field mapping and no
lossy conversion — `manage.py export_subscribers` emits precisely that shape.
`source` is the one addition, and it is additive: a column the monolith does not
have costs it nothing on import.
"""
import uuid

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Subscriber(models.Model):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=150, blank=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)

    # Unsubscribing deactivates rather than deletes, so a later re-subscribe does
    # not silently resurrect somebody who asked to be removed and then had their
    # row recreated by an import. Purge inactive rows deliberately, not by accident.
    active = models.BooleanField(default=True)

    # In every email we send. Generated at creation so a send never has to mint
    # one, and stable so an old email's link keeps working.
    unsubscribe_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    # Which page the person subscribed from. Not in the monolith's table; it is
    # additive, so it cannot break a merge in either direction. Worth having:
    # "the article footer converts, the homepage band does not" is otherwise
    # unanswerable.
    source = models.CharField(max_length=60, blank=True)

    # When they left. **Null does not mean "still subscribed"** — read `active`
    # for that. The monolith records no unsubscribe date at all, so every
    # migrated opt-out arrives with `active=False` and this empty, and inventing
    # a date for them would be fabricating a consent record. Populated from here
    # on for anyone who unsubscribes on this site.
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    # Migration provenance. Never shown publicly.
    legacy_id = models.PositiveIntegerField(
        null=True, blank=True, unique=True, db_index=True,
        help_text='Primary key of the monolith NewsletterSubscriber row.',
    )

    class Meta:
        ordering = ['-subscribed_at']
        verbose_name = 'Newsletter subscriber'
        verbose_name_plural = 'Newsletter subscribers'

    def __str__(self):
        return f'{self.email} ({self.name})' if self.name else self.email


class IssueQuerySet(models.QuerySet):
    def public(self):
        """Issues the archive may show: the ones that were actually sent.

        The same rule the monolith's archive applies. An unsent draft is a work
        in progress, and publishing it because it happens to exist would put
        unfinished writing on a public page.
        """
        return self.filter(sent_at__isnull=False)


class Issue(models.Model):
    """One edition of the newsletter.

    **Deliberately not an `Article`.** They both hold HTML, which is the only
    thing they have in common. An Insight is a piece of research or commentary
    that stands on its own; an issue is a dated edition that was sent to a list,
    and it usually points *at* Insights rather than containing them. Merging them
    would mean an archive of editions cluttering the research index, and every
    query on either having to filter for the other.

    This app **still does not send anything** (see the module docstring). The
    archive is a record of what was sent by the monolith, which remains the
    sending system.
    """

    title = models.CharField(
        max_length=200,
        help_text='Internal name for the issue — not the email subject line.',
    )
    slug = models.SlugField(max_length=200, unique=True)
    subject = models.CharField(
        max_length=200,
        help_text='The subject line recipients saw. Shown in the archive as the '
                  'issue heading, because it is what the issue actually said it was.',
    )
    body_html = models.TextField(
        blank=True,
        help_text='The issue body, as HTML. Rendered through .hs-prose.',
    )
    body_source = models.TextField(
        blank=True,
        help_text='The monolith HTML exactly as exported, before the import '
                  'rewrote links. Kept so the rewriting is auditable; never rendered.',
    )

    # The reading list an issue carried. Resolved by slug at import, so the two
    # systems never share an id space.
    articles = models.ManyToManyField(
        'insights.Article', blank=True, related_name='newsletter_issues',
        help_text='Insights featured in this issue.',
    )

    sent_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text='When this went out. Empty means a draft — drafts are never '
                  'shown in the public archive.',
    )
    send_count = models.PositiveIntegerField(
        default=0, help_text='How many subscribers this issue went to.')

    # Not auto_now_add/auto_now: an imported issue keeps the dates it had in the
    # monolith. auto fields would stamp every migrated issue with the date of the
    # migration, which would make the archive's own history a record of the
    # import rather than of the newsletter.
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    legacy_id = models.PositiveIntegerField(
        null=True, blank=True, unique=True, db_index=True,
        help_text='Primary key of the monolith Newsletter this came from.',
    )
    legacy_path = models.CharField(
        max_length=255, blank=True,
        help_text='Where this lived on haresign.net. Used for the redirect map.',
    )

    objects = IssueQuerySet.as_manager()

    class Meta:
        ordering = ['-sent_at', '-created_at']
        verbose_name = 'Newsletter issue'
        verbose_name_plural = 'Newsletter issues'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)[:200]
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('newsletter:issue', kwargs={'slug': self.slug})

    @property
    def is_draft(self):
        return self.sent_at is None
