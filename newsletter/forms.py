"""The subscribe form.

Deliberately not a `ModelForm`. A `ModelForm` on a unique field turns an
already-subscribed address into a validation error that says so — which tells an
anonymous visitor whether a given person is on the list. The view decides what
happens to a known address (nothing visible), so the form's only job is to
validate the shape of what was typed.
"""
from django import forms


class SubscribeForm(forms.Form):
    email = forms.EmailField(
        max_length=254,
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'That does not look like an email address.',
        },
    )
    name = forms.CharField(max_length=150, required=False)

    # Honeypot. Hidden from people by CSS and from screen readers by aria-hidden
    # + tabindex, so only something filling every input reaches it. A quiet,
    # zero-friction alternative to a CAPTCHA, which would mean a third-party
    # request — and this site deliberately makes none.
    website = forms.CharField(required=False)

    # Where the form was rendered. Not user-facing; validated by choice-free
    # length so a crafted value cannot bloat the column.
    source = forms.CharField(max_length=60, required=False)

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean_name(self):
        return self.cleaned_data['name'].strip()

    def is_bot(self):
        """True when the honeypot was filled.

        Checked separately rather than raised as an error: a bot should be told
        it succeeded, not shown a form to try again with.
        """
        return bool(self.data.get('website', '').strip())
