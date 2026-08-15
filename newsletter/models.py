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

    class Meta:
        ordering = ['-subscribed_at']
        verbose_name = 'Newsletter subscriber'
        verbose_name_plural = 'Newsletter subscribers'

    def __str__(self):
        return f'{self.email} ({self.name})' if self.name else self.email
