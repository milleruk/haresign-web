"""Responsive and accessibility QA, driven through a real browser.

    pip install playwright && python -m playwright install --with-deps chromium
    python qa/responsive.py                      # against beta
    python qa/responsive.py --base http://localhost:8000
    python qa/responsive.py --screenshots        # also write qa/screenshots/

Run against a *served* site, not the Django test client: the questions here are
"does this overflow at 320px" and "can this be tapped", and neither has an answer
without layout. That is also why it lives outside `manage.py test` — the unit
suite must not need a browser or a network.

**Functional assertions, not screenshot diffs.** A pixel-comparison suite on a
site under active design breaks on every intentional change and teaches everyone
to ignore it. What is asserted here is what actually matters and never
intentionally changes: nothing overflows sideways, controls are big enough to
hit, headings descend in order, images stay inside their column, and the nav
opens and closes. Screenshots are written for a human to look at, not compared.
"""
import argparse
import re
import sys

from playwright.sync_api import sync_playwright

# The widths that correspond to real devices, plus 320 because it is the floor
# below which nothing is expected to work and above which everything must.
VIEWPORTS = [
    ('320x568', 320, 568),      # iPhone SE, the narrowest phone still in use
    ('375x667', 375, 667),      # iPhone SE 2/3
    ('390x844', 390, 844),      # iPhone 14/15
    ('430x932', 430, 932),      # iPhone 15 Pro Max
    ('768x1024', 768, 1024),    # iPad portrait
    ('1024x768', 1024, 768),    # iPad landscape / small laptop
    ('1440x900', 1440, 900),    # desktop
]

PAGES = [
    ('home', '/'),
    ('insights', '/insights/'),
    ('insights-page2', '/insights/?page=2'),
    ('insights-filtered', '/insights/?tag=governance'),
    # A real imported article: Bootstrap cards, a contents panel, tables and
    # images. The single most likely page to break on a phone.
    ('article', '/insights/benchmarking-is-not-a-league-table/'),
    # The two worst cases in the imported corpus, picked by counting: ten tables
    # in one, twelve images in the other. If .hs-prose holds at 320px here it
    # holds everywhere.
    ('article-tables', '/insights/qof-changes/'),
    ('article-images', '/insights/why-cant-i-get-a-gp-appointment-follow-the-money/'),
    ('newsletter-archive', '/newsletter/'),
    ('newsletter-issue', '/newsletter/newsletter-002/'),
    ('faq', '/faq/'),
    ('contact', '/contact/'),
    ('privacy', '/privacy/'),
    ('cookies', '/cookies/'),
    ('terms', '/terms/'),
    ('accessibility', '/accessibility/'),
]

SCREENSHOT_WIDTHS = {390, 768, 1440}
SCREENSHOT_PAGES = {'home', 'insights', 'article', 'faq', 'contact',
                    'newsletter-archive'}

# Sub-pixel rounding means a page can measure a fraction wider than its viewport
# without a scrollbar ever appearing. Two pixels is comfortably inside that and
# far below anything a person could see.
OVERFLOW_TOLERANCE = 2


def _goto(page, url, attempts=3):
    """Navigate, retrying transient network failures.

    Runs against the deployed site over the network, so an occasional
    ERR_NETWORK_CHANGED says nothing about the page. Retried rather than treated
    as a finding — a QA suite that reports flakes as defects gets ignored.
    """
    last = None
    for attempt in range(attempts):
        try:
            return page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception as exc:                      # noqa: BLE001 - any nav error
            last = exc
            page.wait_for_timeout(1500 * (attempt + 1))
    print(f'  (giving up on {url}: {last})', file=sys.stderr)
    return None


class Results:
    def __init__(self):
        self.failures = []
        self.warnings = []
        self.checks = 0

    def check(self, ok, label, detail=''):
        self.checks += 1
        if not ok:
            self.failures.append(f'{label}: {detail}')
        return ok

    def warn(self, label, detail=''):
        self.warnings.append(f'{label}: {detail}')


def check_overflow(page, results, label):
    """Nothing may scroll sideways. The single most common mobile defect."""
    metrics = page.evaluate("""() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
    })""")
    overflow = metrics['scrollWidth'] - metrics['clientWidth']
    results.check(
        overflow <= OVERFLOW_TOLERANCE, f'{label} horizontal overflow',
        f"scrollWidth {metrics['scrollWidth']} vs clientWidth {metrics['clientWidth']}")

    if overflow > OVERFLOW_TOLERANCE:
        # Name the culprit rather than just the symptom — "something is 40px too
        # wide" is not actionable, "this table is" is.
        culprits = page.evaluate("""(limit) => {
            const out = [];
            document.querySelectorAll('body *').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.right > limit + 2 || r.left < -2) {
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        cls: (el.className || '').toString().slice(0, 60),
                        left: Math.round(r.left), right: Math.round(r.right),
                    });
                }
            });
            return out.slice(0, 5);
        }""", metrics['clientWidth'])
        for culprit in culprits:
            results.warn(f'{label} overflowing element',
                         f"<{culprit['tag']} class=\"{culprit['cls']}\"> "
                         f"{culprit['left']}..{culprit['right']}")


def check_images(page, results, label):
    """Images must stay inside their container and not distort.

    `.hs-prose img` is the one that matters: article bodies carry images with
    hard-coded width attributes from the old editor.
    """
    bad = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('img').forEach(img => {
            const parent = img.parentElement;
            if (!parent) return;
            const i = img.getBoundingClientRect();
            const p = parent.getBoundingClientRect();
            if (i.width > p.width + 2) {
                out.push({src: img.currentSrc || img.src, w: Math.round(i.width),
                          pw: Math.round(p.width)});
            }
        });
        return out.slice(0, 5);
    }""")
    results.check(not bad, f'{label} image overflow',
                  '; '.join(f"{b['src'].split('/')[-1]} {b['w']}>{b['pw']}" for b in bad))


def check_tap_targets(page, results, label):
    """Interactive things need to be big enough to hit.

    24x24 CSS pixels is WCAG 2.2 AA (2.5.8). The 44px figure often quoted is
    Apple's guidance and AAA — worth aiming at, not worth failing a build over,
    so anything between the two is a warning.
    """
    small = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('a, button, summary, input, [role=button]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;      // hidden
            if (el.closest('.hs-prose')) return;              // inline body links
            if (Math.min(r.width, r.height) < 24) {
                out.push({tag: el.tagName.toLowerCase(),
                          text: (el.textContent || '').trim().slice(0, 30),
                          w: Math.round(r.width), h: Math.round(r.height)});
            }
        });
        return out.slice(0, 8);
    }""")
    results.check(not small, f'{label} tap targets below 24px',
                  '; '.join(f"{s['tag']} \"{s['text']}\" {s['w']}x{s['h']}" for s in small))


def check_headings(page, results, label):
    """One h1, and levels that descend without skipping."""
    headings = page.evaluate(
        """() => [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
                 .map(h => ({level: +h.tagName[1],
                             text: (h.textContent || '').trim().slice(0, 40)}))""")
    h1s = [h for h in headings if h['level'] == 1]
    results.check(len(h1s) == 1, f'{label} exactly one h1',
                  f'found {len(h1s)}: ' + '; '.join(h["text"] for h in h1s[:4]))

    previous = 0
    for heading in headings:
        if previous and heading['level'] > previous + 1:
            results.warn(f'{label} heading level skipped',
                         f'h{previous} -> h{heading["level"]} at "{heading["text"]}"')
        previous = heading['level']


def check_landmarks(page, results, label):
    counts = page.evaluate("""() => ({
        header: document.querySelectorAll('body > header').length,
        main: document.querySelectorAll('main').length,
        footer: document.querySelectorAll('body > footer').length,
        skip: document.querySelectorAll('.hs-skip-link').length,
    })""")
    results.check(counts['main'] == 1, f'{label} one main landmark', str(counts))
    results.check(counts['skip'] == 1, f'{label} skip link present', str(counts))


def check_alt_text(page, results, label):
    """Reported, never invented. Legacy article images may genuinely lack alt
    text; that is a content problem for an editor, not something an importer
    should paper over."""
    missing = page.evaluate(
        """() => [...document.querySelectorAll('img')]
                 .filter(i => !i.hasAttribute('alt'))
                 .map(i => (i.currentSrc || i.src).split('/').pop()).slice(0, 5)""")
    if missing:
        results.warn(f'{label} images without an alt attribute', ', '.join(missing))


def check_text_size(page, results, label):
    """Body text below 16px triggers zoom-on-focus in iOS Safari and is hard
    work on a phone regardless."""
    size = page.evaluate(
        "() => parseFloat(getComputedStyle(document.body).fontSize)")
    results.check(size >= 15.9, f'{label} body text size', f'{size}px')


def check_mobile_nav(page, results, label):
    """The disclosure panel: opens, closes, and closes on Escape."""
    toggle = page.locator('#hs-nav-toggle')
    if not toggle.is_visible():
        return
    nav = page.locator('#hs-nav')

    toggle.click()
    results.check(nav.is_visible(), f'{label} nav opens')
    results.check(toggle.get_attribute('aria-expanded') == 'true',
                  f'{label} nav reports expanded')

    page.keyboard.press('Escape')
    results.check(toggle.get_attribute('aria-expanded') == 'false',
                  f'{label} Escape closes the nav')

    toggle.click()
    # With the panel open, nothing may be pushed sideways.
    check_overflow(page, results, f'{label} nav open')
    toggle.click()


def check_faq_disclosure(page, results, label):
    """<details>/<summary> must work, and opening one must not cause overflow."""
    items = page.locator('details.hs-faq__item')
    count = items.count()
    results.check(count > 0, f'{label} FAQ items present', str(count))
    if not count:
        return

    last = items.nth(count - 1)
    last.locator('summary').click()
    results.check(last.evaluate('el => el.open'), f'{label} FAQ item opens')
    check_overflow(page, results, f'{label} FAQ open')

    # And the content is in the DOM whether open or not — the reason this is a
    # <details> rather than a JavaScript accordion.
    closed_text = items.nth(0).evaluate(
        "el => el.querySelector('.hs-faq__answer').textContent.trim().length")
    results.check(closed_text > 0, f'{label} closed answers still in the DOM')


def check_newsletter_form(page, results, label):
    """The form has to be usable, which at 320px means the inputs are not
    squeezed into eight characters."""
    form = page.locator('.hs-newsletter__form').first
    if not form.is_visible():
        return
    email = form.locator('input[type=email]')
    results.check(email.is_visible(), f'{label} email input visible')
    box = email.bounding_box()
    if box:
        results.check(box['width'] >= 140, f'{label} email input width',
                      f"{round(box['width'])}px")
        results.check(box['height'] >= 40, f'{label} email input height',
                      f"{round(box['height'])}px")
    submit = form.locator('button[type=submit]')
    results.check(submit.is_visible(), f'{label} subscribe button visible')


# Transport failures from running over the public internet. They say nothing
# about the page, and a QA suite that reports the network as a site defect is a
# QA suite people learn to ignore.
_TRANSIENT = ('ERR_NETWORK_CHANGED', 'ERR_NETWORK_IO_SUSPENDED',
              'ERR_CONNECTION_RESET', 'ERR_TIMED_OUT', 'ERR_ABORTED')


def check_console(page, results, label, errors):
    real = [e for e in errors if not any(t in e for t in _TRANSIENT)]
    results.check(not real, f'{label} console errors', '; '.join(real[:3]))


def check_community_is_live(page, results, base):
    """Community went live in this pass. It must be a link, everywhere."""
    count = page.evaluate(
        """() => document.querySelectorAll(
             'a[href="https://community.haresign.net"]').length""")
    results.check(count > 0, 'Community linked on the homepage', str(count))

    soon = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('.hs-badge').forEach(b => {
            const row = b.closest('li, span, article, a') || b.parentElement;
            if (row && /community/i.test(row.textContent || '')) {
                out.push((row.textContent || '').trim().slice(0, 40));
            }
        });
        return out;
    }""")
    results.check(not soon, 'no "Soon" badge left against Community',
                  '; '.join(soon))


def run(base, want_screenshots):
    results = Results()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        for width_label, width, height in VIEWPORTS:
            context = browser.new_context(
                viewport={'width': width, 'height': height},
                device_scale_factor=2 if width < 600 else 1,
                is_mobile=width < 768,
                has_touch=width < 768,
            )

            for name, path in PAGES:
                page = context.new_page()
                errors = []
                page.on('console', lambda m: (
                    errors.append(m.text) if m.type == 'error' else None))
                page.on('pageerror', lambda e: errors.append(str(e)))

                response = _goto(page, f'{base}{path}')
                label = f'{name}@{width_label}'

                if not response or response.status != 200:
                    results.check(False, f'{label} loads',
                                  f'status {response.status if response else "none"}')
                    page.close()
                    continue

                check_overflow(page, results, label)
                check_images(page, results, label)
                check_headings(page, results, label)
                check_landmarks(page, results, label)
                check_text_size(page, results, label)
                check_alt_text(page, results, label)
                if width < 992:
                    check_tap_targets(page, results, label)
                    check_mobile_nav(page, results, label)
                if name == 'faq':
                    check_faq_disclosure(page, results, label)
                if name in ('home', 'insights', 'newsletter-archive'):
                    check_newsletter_form(page, results, label)
                if name == 'home' and width == 1440:
                    check_community_is_live(page, results, base)
                check_console(page, results, label, errors)

                if want_screenshots and width in SCREENSHOT_WIDTHS and name in SCREENSHOT_PAGES:
                    import pathlib
                    directory = pathlib.Path('qa/screenshots')
                    directory.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(directory / f'{name}-{width}.png'),
                                    full_page=True)

                page.close()

            context.close()

        # Keyboard-only pass. Done once, at one width: it is about focus order
        # and visible focus, neither of which is a function of viewport.
        context = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = context.new_page()
        page.goto(f'{base}/faq/', wait_until='networkidle')
        page.keyboard.press('Tab')
        first = page.evaluate(
            "() => document.activeElement.className || document.activeElement.tagName")
        results.check('hs-skip-link' in str(first),
                      'first Tab reaches the skip link', str(first))

        # Tabbed to, not focused programmatically. The ring is `:focus-visible`,
        # which deliberately does *not* match a scripted `.focus()` — the first
        # version of this check called focus() directly, saw outline:none and
        # reported a defect that was purely an artefact of how it looked.
        for _ in range(6):
            page.keyboard.press('Tab')
        outline = page.evaluate("""() => {
            const el = document.activeElement;
            const s = getComputedStyle(el);
            return {tag: el.tagName.toLowerCase(),
                    cls: (el.className || '').toString().slice(0, 40),
                    outline: s.outlineStyle, width: s.outlineWidth,
                    shadow: s.boxShadow};
        }""")
        results.check(
            outline['outline'] not in ('none', ''),
            'focus is visible when tabbing', str(outline))

        # <details> by keyboard: Enter on a focused summary toggles it.
        page.evaluate("() => document.querySelector('details.hs-faq__item summary').focus()")
        was_open = page.evaluate(
            "() => document.querySelector('details.hs-faq__item').open")
        page.keyboard.press('Enter')
        now_open = page.evaluate(
            "() => document.querySelector('details.hs-faq__item').open")
        results.check(now_open != was_open, 'FAQ item toggles by keyboard',
                      f'open stayed {now_open}')

        # prefers-reduced-motion must actually remove motion.
        context.close()
        context = browser.new_context(viewport={'width': 1440, 'height': 900},
                                      reduced_motion='reduce')
        page = context.new_page()
        page.goto(base, wait_until='networkidle')
        duration = page.evaluate("""() => getComputedStyle(document.documentElement)
                                        .getPropertyValue('--hs-duration-base').trim()""")
        results.check(duration.startswith('0.01'), 'reduced motion honoured', duration)
        context.close()

        browser.close()

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='https://beta.haresign.net')
    parser.add_argument('--screenshots', action='store_true')
    args = parser.parse_args()

    results = run(args.base.rstrip('/'), args.screenshots)

    print()
    print(f'{results.checks} checks across {len(VIEWPORTS)} viewports '
          f'and {len(PAGES)} pages')

    if results.warnings:
        print(f'\n{len(results.warnings)} warning(s):')
        seen = set()
        for warning in results.warnings:
            key = re.sub(r'@\d+x\d+', '', warning)
            if key in seen:
                continue
            seen.add(key)
            print(f'  ! {warning}')

    if results.failures:
        print(f'\n{len(results.failures)} FAILURE(S):')
        for failure in results.failures:
            print(f'  x {failure}')
        return 1

    print('\nAll responsive and accessibility checks passed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
