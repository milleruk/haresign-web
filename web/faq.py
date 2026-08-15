"""The umbrella FAQ — questions about **Haresign as a whole**.

Scope, and the reason the file is short: under the ownership boundary these are
ecosystem questions only. "How does an engagement start?", "what does it cost?"
and "what's in my client portal?" are *Haresign Consulting* questions and belong
to that site — haresign.net already answers them, and copying them here would
rebuild the mixed old homepage this architecture exists to separate.

Answers are data rather than markup so the tests can assert against the same
source the page renders from, and so nothing here needs raw HTML in Python.
An answer is a list of paragraphs; `link` optionally adds one trailing link,
resolved through the service registry (`service`) or given outright (`url`).
A `service` that is not live renders as a "coming soon" label, never a link.

Nothing here states a fact that is not already established on haresign.net or in
this repository. Where the honest answer is "not yet", it says that.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Question:
    # Stable anchor. Used by the contents list, by deep links from other pages,
    # and by the tests — so renaming a question does not break a link to it.
    anchor: str
    question: str
    answer: list = field(default_factory=list)
    # {'service': '<registry slug>'} or {'url': ..., 'label': ...}
    link: dict = None


@dataclass(frozen=True)
class Section:
    anchor: str
    heading: str
    questions: list = field(default_factory=list)


FAQ_SECTIONS = [
    Section(
        anchor='the-basics',
        heading='The basics',
        questions=[
            Question(
                anchor='what-is-haresign',
                question='What is Haresign?',
                answer=[
                    'Haresign is a primary care platform. It brings together '
                    'intelligence built on published NHS data, practical tools '
                    'for running a practice or PCN, consultancy and support, a '
                    'private workspace for organisations working directly with '
                    'us, and a professional community.',
                    'They are parts of one organisation rather than separate '
                    'products that happen to share a name: the same '
                    'understanding of general practice runs through all of them.',
                ],
            ),
            Question(
                anchor='who-is-it-for',
                question='Who is Haresign for?',
                answer=[
                    'GP practices, Primary Care Networks, practice and business '
                    'managers, clinicians, partners and the people leading '
                    'primary care organisations across England.',
                    'Not every part is right for everyone. The intelligence and '
                    'tools are built for people running practices and PCNs day '
                    'to day; consultancy suits organisations working through a '
                    'specific problem; the workspace is only for organisations '
                    'already working with us. The Contact page is there to point '
                    'you at whichever fits.',
                ],
                link={'url': '/contact/', 'label': 'Find the right route'},
            ),
            Question(
                anchor='is-haresign-nhs',
                question='Is Haresign part of the NHS?',
                answer=[
                    'No. Haresign Consulting Services is an independent sole '
                    'trader business. It is not part of the NHS, not an NHS '
                    'body, and not endorsed by NHS England.',
                    'Haresign Intelligence analyses data the NHS publishes, but '
                    'publishing that data does not imply any endorsement of what '
                    'we do with it. The analysis and any conclusions drawn from '
                    'it are ours.',
                ],
            ),
        ],
    ),
    Section(
        anchor='the-platforms',
        heading='The platforms',
        questions=[
            Question(
                anchor='what-is-intelligence',
                question='What is Haresign Intelligence?',
                answer=[
                    'The data and tools platform. It turns published primary '
                    'care datasets into benchmarking, dashboards and practical '
                    'tools — appointments, workforce, list size, patient '
                    'experience, funding, contracts, compliance and more — so a '
                    'practice or PCN can see where it stands and what to do next.',
                    'Some of it is open; some requires an account or a '
                    'subscription. The platform itself says which.',
                ],
                link={'service': 'intelligence'},
            ),
            Question(
                anchor='what-is-consulting',
                question='What is Haresign Consulting?',
                answer=[
                    'The advisory and support side: practical help for '
                    'practices, PCNs and primary care organisations with '
                    'strategy, access and capacity, operations, transformation '
                    'and management support.',
                    'It is hands-on work with an organisation, rather than '
                    'something you sign up to. Details of how engagements work '
                    'live on the Consulting site.',
                ],
                link={'service': 'consulting'},
            ),
            Question(
                anchor='what-is-community',
                question='What is Haresign Community?',
                answer=[
                    'A professional community for people working in primary '
                    'care — a place to ask questions, share what has worked, and '
                    'get a view from people doing the same job elsewhere.',
                    'It is separate from consultancy. You do not need to be a '
                    'client to take part.',
                ],
                link={'service': 'community'},
            ),
            Question(
                anchor='what-is-workspace',
                question='What is Haresign Workspace?',
                answer=[
                    'The private workspace for organisations working directly '
                    'with Haresign. It holds the reports, analysis, project '
                    'material and deliverables for that piece of work in one '
                    'place, rather than scattered across email.',
                    'Access is set up as part of an engagement — it is not '
                    'something you can sign up to.',
                ],
                link={'service': 'workspace'},
            ),
        ],
    ),
    Section(
        anchor='accounts-and-data',
        heading='Accounts and data',
        questions=[
            Question(
                anchor='do-i-need-an-account',
                question='Do I need a Haresign Account?',
                answer=[
                    'Not for this website. Everything here — including Insights '
                    '— is public and needs no account.',
                    'Individual platforms have their own sign-in today. Haresign '
                    'Account is the intended single Haresign identity across the '
                    'ecosystem; it is being built, and until it ships each '
                    'platform continues to work exactly as it does now. We are '
                    'not going to describe it as finished before it is.',
                ],
            ),
            Question(
                anchor='where-does-data-come-from',
                question='Where does Haresign data come from?',
                answer=[
                    'Haresign Intelligence is built on data that NHS '
                    'organisations publish openly — national collections and '
                    'statistical publications covering things like appointments, '
                    'workforce, registered list size, patient experience, '
                    'prescribing and payments.',
                    'Each tool names its own source, its period and its '
                    'limitations, because a benchmark is only as good as the '
                    'reader understanding what it was made from. The full list '
                    'is in the documentation rather than here.',
                ],
                link={'service': 'docs', 'label': 'Data sources in the documentation'},
            ),
            Question(
                anchor='patient-data',
                question='Does Haresign hold patient data?',
                answer=[
                    'This website holds none at all.',
                    'Haresign Intelligence works with published, practice-level '
                    'statistics — counts and rates for an organisation, not '
                    'records about individuals. Where a piece of consultancy '
                    'requires anything more sensitive, it is governed by a '
                    'written agreement with the organisation concerned.',
                ],
                link={'url': '/privacy/', 'label': 'Read the Privacy Notice'},
            ),
        ],
    ),
    Section(
        anchor='getting-in-touch',
        heading='Getting in touch',
        questions=[
            Question(
                anchor='how-do-i-contact-haresign',
                question='How do I contact Haresign?',
                answer=[
                    'Through the Contact page, which routes your question to the '
                    'right part of Haresign — consultancy, the platform, the '
                    'community, existing client work, or anything else.',
                    'If you would rather not work out which, use the general '
                    'route and it will get to the right place.',
                ],
                link={'url': '/contact/', 'label': 'Go to Contact'},
            ),
            Question(
                anchor='newsletter',
                question='What do I get if I subscribe?',
                answer=[
                    'New primary care analysis, research, tools and Haresign '
                    'updates as they are published — and nothing else. We do not '
                    'sell or share the list, and every email carries a one-click '
                    'unsubscribe link.',
                ],
            ),
        ],
    ),
]


def all_questions():
    """Flat list of every question, for tests and for the contents nav."""
    return [q for section in FAQ_SECTIONS for q in section.questions]
