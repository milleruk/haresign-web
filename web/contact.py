"""Contact routes — where a question should go.

This page's job is **routing**, not lead capture. A single "how can we help?"
box would put a consulting enquiry, a billing question and a bug report in the
same inbox with nothing to tell them apart, which is exactly the mixing the new
architecture separates. Haresign Consulting owns consulting enquiry forms; this
page's job is to get the right question to the right place.

Every route is a `mailto:` with a subject already filled in, so the destination
is visible before you click and no server-side email path exists to be abused.
There is deliberately no form — see the README for what adding one would cost
(spam handling, an SMTP credential in this deployment, and a change to the
Privacy Notice, which currently says truthfully that this site has no
general-enquiry form).

`service` names a registry slug where one exists, so a route can show whether
that platform is live and link to it. `None` means the route is Haresign itself.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContactRoute:
    anchor: str
    heading: str
    blurb: str
    # Pre-filled mail subject. Not decoration: it is what makes the inbox
    # sortable, and it is why the routes are separate at all.
    subject: str
    icon: str
    accent: str
    service: str = None
    # Extra things worth saying under the button, e.g. "you'll already have a
    # contact for this".
    notes: list = field(default_factory=list)


CONTACT_ROUTES = [
    ContactRoute(
        anchor='consulting',
        heading='Consulting',
        blurb='Practice and PCN support, projects, management advice and '
              'anything you would like to talk through before committing to.',
        subject='Consulting enquiry',
        icon='compass',
        accent='coral',
        service='consulting',
        notes=['There is no charge for an initial conversation.'],
    ),
    ContactRoute(
        anchor='intelligence',
        heading='Intelligence',
        blurb='Questions about the tools, dashboards and data — including '
              'subscriptions, access, and anything that looks wrong in a figure.',
        subject='Haresign Intelligence enquiry',
        icon='chart',
        accent='teal',
        service='intelligence',
        notes=['If a number looks wrong, tell us which tool, which practice and '
               'which period — it is usually enough for us to reproduce it.'],
    ),
    ContactRoute(
        anchor='community',
        heading='Community',
        blurb='Joining, taking part, moderation, or anything to do with your '
              'community membership.',
        subject='Haresign Community enquiry',
        icon='community',
        accent='aqua',
        service='community',
    ),
    ContactRoute(
        anchor='workspace',
        heading='Workspace',
        blurb='For organisations already working with Haresign: access to your '
              'workspace, reports and project material.',
        subject='Workspace / client enquiry',
        icon='folder',
        accent='navy',
        service='workspace',
        notes=['If you are already working with us, your usual contact is the '
               'fastest route.'],
    ),
    ContactRoute(
        anchor='general',
        heading='Anything else',
        blurb='Partnerships, media, research collaboration, speaking, or a '
              'question that does not fit any of the above.',
        subject='General enquiry',
        icon='evidence',
        accent='navy',
        notes=['Not sure which of these you need? Use this one — we will point '
               'you the right way.'],
    ),
]
