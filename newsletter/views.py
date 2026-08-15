"""Subscribe and unsubscribe.

**No JavaScript anywhere in this flow.** The form is an ordinary POST and the
answer is an ordinary page. The site's newsletter block appears on articles, so
an intercepted submit that failed silently would lose a subscription with nothing
to show for it; a page you can read, bookmark and go back from cannot.

**No sessions and no messages framework.** Both would set a cookie on public
pages to carry one sentence across a redirect, and this site's cookie position is
worth more than the redirect. The result is rendered directly from the POST.
Re-posting it is harmless: subscribing is idempotent.
"""
from django.core.cache import cache
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST, require_http_methods

from .forms import SubscribeForm
from .models import Subscriber

# Per-IP limit. Generous enough that nobody legitimate meets it, tight enough
# that the endpoint is not a way to test which addresses are already on a list.
RATE_LIMIT_ATTEMPTS = 5
RATE_LIMIT_WINDOW_SECONDS = 900


def _client_ip(request):
    """Client IP, honouring the proxy header Traefik sets.

    Left-most entry in X-Forwarded-For is the client. Spoofable in principle,
    which is fine here: this feeds a rate limit, not an authorisation decision.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _rate_limited(request):
    key = f'newsletter-subscribe:{_client_ip(request)}'
    attempts = cache.get(key, 0)
    if attempts >= RATE_LIMIT_ATTEMPTS:
        return True
    cache.set(key, attempts + 1, RATE_LIMIT_WINDOW_SECONDS)
    return False


@require_POST
def subscribe(request):
    """Add an address to the list.

    Every outcome that is not a malformed address renders the *same* success
    page: newly subscribed, already subscribed, reactivated, and the honeypot all
    look identical from outside. Otherwise the form answers "is this person on
    the Haresign list?" for anyone who cares to ask, one address at a time.
    """
    form = SubscribeForm(request.POST)

    if not form.is_valid():
        return render(request, 'newsletter/result.html', {
            'ok': False,
            'error': next(iter(form.errors.values()))[0],
        }, status=400)

    # Silently accepted. A bot told it failed simply tries again.
    if form.is_bot():
        return render(request, 'newsletter/result.html', {'ok': True})

    if _rate_limited(request):
        return render(request, 'newsletter/result.html', {
            'ok': False,
            'error': 'Too many attempts from this connection. '
                     'Please try again in a few minutes.',
        }, status=429)

    email = form.cleaned_data['email']
    name = form.cleaned_data['name']

    subscriber, created = Subscriber.objects.get_or_create(
        email=email,
        defaults={'name': name, 'source': form.cleaned_data['source']},
    )
    if not created and not subscriber.active:
        # Somebody who left and came back. Reactivate rather than refuse: they
        # have just asked to be on the list again.
        subscriber.active = True
        if name and not subscriber.name:
            subscriber.name = name
        subscriber.save(update_fields=['active', 'name'])

    return render(request, 'newsletter/result.html', {'ok': True})


@require_http_methods(['GET', 'POST'])
def unsubscribe(request, token):
    """Leave the list, via the link carried in every email.

    A GET *shows* the confirmation and a POST performs it, because mail clients
    and security scanners follow links in email without being asked to. If the
    GET unsubscribed people, a scanner would quietly remove them.

    No login: somebody who no longer wants our email must not have to make an
    account to say so.
    """
    subscriber = get_object_or_404(Subscriber, unsubscribe_token=token)

    if request.method == 'POST':
        if subscriber.active:
            subscriber.active = False
            subscriber.save(update_fields=['active'])
        return render(request, 'newsletter/unsubscribed.html',
                      {'subscriber': subscriber})

    return render(request, 'newsletter/unsubscribe.html', {
        'subscriber': subscriber,
        'already_gone': not subscriber.active,
    })
