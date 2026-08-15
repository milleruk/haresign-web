"""Metadata for the legal and policy pages.

The pages themselves are templates — four static documents do not justify a
content model, and legal text belongs in version control where changes are
reviewable and dated.

What lives here is everything the *shell* needs: the title, the meta
description, the last-reviewed date and the section list that builds the
contents nav. Keeping it in Python means one template renders all four pages and
the tests can assert against the same source the pages render from.

`sections` must match the `id` on each `<h2>` in the corresponding template;
`LegalPageTests.test_contents_anchors_all_exist` enforces that, so a renamed
heading cannot leave a contents link pointing at nothing.
"""

# Reviewed date shown on each page. A single constant because all four were
# written together; split it per page the moment they stop changing together.
LAST_REVIEWED = 'August 2026'


LEGAL_PAGES = {
    'privacy': {
        'title': 'Privacy Notice',
        'lead': 'How Haresign handles personal information collected through '
                'this website.',
        'meta_description': 'How Haresign collects, uses and protects personal '
                            'information through the public Haresign website.',
        'sections': [
            ('who-we-are', 'Who we are'),
            ('what-this-covers', 'What this notice covers'),
            ('what-we-collect', 'What information we collect'),
            ('how-we-use-it', 'How we use it, and our lawful basis'),
            ('sharing', 'Who we share it with'),
            ('retention', 'How long we keep it'),
            ('security', 'Security'),
            ('your-rights', 'Your rights'),
            ('other-services', 'Other Haresign services'),
            ('changes', 'Changes to this notice'),
            ('contact', 'Contact and complaints'),
        ],
    },
    'cookies': {
        'title': 'Cookie Policy',
        'lead': 'What this website stores on your device — and what it does not.',
        'meta_description': 'Cookies used by the public Haresign website, and '
                            'how to control them.',
        'sections': [
            ('what-are-cookies', 'What cookies are'),
            ('what-this-site-uses', 'What this site uses'),
            ('essential', 'Essential cookies'),
            ('optional', 'Analytics and optional cookies'),
            ('third-party', 'Third-party content'),
            ('controlling', 'Controlling cookies'),
            ('changes', 'Changes to this policy'),
            ('contact', 'Contact'),
        ],
    },
    'terms': {
        'title': 'Terms of Use',
        'lead': 'The terms on which you may use this website.',
        'meta_description': 'Terms of use for the public Haresign website.',
        'sections': [
            ('about', 'About these terms'),
            ('using', 'Using this website'),
            ('content', 'The nature of our content'),
            ('ip', 'Intellectual property'),
            ('acceptable-use', 'Acceptable use'),
            ('external-links', 'Links to other sites'),
            ('availability', 'Availability'),
            ('liability', 'Liability'),
            ('other-services', 'Other Haresign services'),
            ('changes', 'Changes to these terms'),
            ('law', 'Governing law'),
            ('contact', 'Contact'),
        ],
    },
    'accessibility': {
        'title': 'Accessibility Statement',
        'lead': 'How this website is built to be usable by as many people as '
                'possible — and where it currently falls short.',
        'meta_description': 'Accessibility of the Haresign website: our '
                            'approach, what we have done, and known limitations.',
        'sections': [
            ('commitment', 'Our commitment'),
            ('standard', 'The standard we work to'),
            ('what-we-do', 'What we have built in'),
            ('limitations', 'Known limitations'),
            ('reporting', 'Reporting a problem'),
            ('changes', 'Changes to this statement'),
        ],
    },
}
