# haresign-web

The public Haresign web layer — the umbrella site that introduces the Haresign
ecosystem and sends people to the right platform.

Currently deployed as a preview at **`beta.haresign.net`**, where the future
`haresign.net` homepage is designed and reviewed before it replaces production.

---

## Insights — and parallel running

`haresign-web` owns Haresign's public editorial content through the `insights`
app: articles, research, commentary and updates, published from Django Admin.

**The monolith remains the live source of articles.** `haresign.net/blog/` is
untouched and continues to be where publishing happens. Insights runs in
parallel on beta so the two can be compared before any cutover. There is
deliberately **no dual write and no synchronisation**: the two systems do not
know about each other, and a single controlled import happens at cutover.

Compare the same article in both:

```
https://haresign.net/blog/<slug>/          (monolith, live)
https://beta.haresign.net/insights/<slug>/ (this app, beta)
```

### Cutover sequence (not implemented)

1. Build and test Insights on beta · 2. copy representative articles ·
3. compare old vs new · 4. finalise rendering and media · 5. import all
articles · 6. verify counts, slugs and content · 7. briefly freeze article
changes · 8. final delta import · 9. point `haresign.net` at `haresign-web` ·
10. add permanent redirects from the old blog URLs · 11. keep the monolith blog
available for rollback · 12. retire it only after validation.

Redirect mappings belong in the **monolith** (its URLconf still owns
`/blog/…`) or at Traefik, once the real URL structure is confirmed. The likely
mapping is `/blog/<slug>/ → /insights/<slug>/`, and slugs are imported unchanged
so it should hold — but it must be verified against the live URL list rather than
assumed.

## Newsletter — two lists, deliberately, and how they end up as one

The newsletter belongs to `haresign-web` under the ownership boundary: it is
advertised beside Insights, it carries Insights, and it is a subscription to this
site's editorial content.

**Right now two lists exist**, and that is the honest position rather than a
tidy one:

| System | Table | Collects from | Sends |
|---|---|---|---|
| Monolith | `website.NewsletterSubscriber` | haresign.net | **Yes** — django-q + Graph email |
| This app | `newsletter.Subscriber` | beta.haresign.net | **No** |

This app **collects but does not send**. There is no SMTP configuration, no
queue, and the admin has `actions = None` so no bulk-mail action can be added by
accident. A list mailed from two systems is a list mailed twice.

Three things keep the duplication bounded rather than accidental:

1. **Beta is `noindex` and unlinked**, so the volume here is approximately zero
   until cutover.
2. **The fields are the monolith's fields.** `email`, `name`, `subscribed_at`,
   `active` and `unsubscribe_token` match `website.NewsletterSubscriber` exactly,
   including the UUID default — so a merge is a row copy with no field mapping.
   `source` is the one addition and is additive.
3. **A file crosses the boundary, not a connection.** `manage.py
   export_subscribers` emits that shape as JSON, the same one-way pattern as
   `import_legacy_articles`. This app never connects to the monolith's database.

```bash
python manage.py export_subscribers --output subscribers.json
python manage.py export_subscribers --all          # include unsubscribed rows
```

Unsubscribed rows are excluded by default: exporting somebody who opted out is
exactly how they get mailed again.

### Deciding sending, before cutover

Whichever way this goes, it is a decision to take rather than to drift into:

- **Keep sending from the monolith** (nothing to build): export from here,
  import there, and the monolith keeps mailing until it is retired.
- **Move sending here** (not built): needs an email provider, a queue, a send
  model and per-issue templates. Effectively re-implementing the monolith's
  `newsletter` app in this repository.
- **Move to a mail provider** (Buttondown, Mailchimp, Listmonk): the sign-up
  form and the model stay, and a small sync pushes new rows to the provider.

`unsubscribe_token` is stable and carried in the export precisely so links in
already-sent emails keep working through any of these.

### One consequence worth knowing about

`{% templatetag openblock %} csrf_token {% templatetag closeblock %}` in the sign-up form sets a **`csrftoken` cookie** on every
page carrying it. It is strictly necessary, so no consent is required — but the
site previously set no cookies at all, so the Cookie Policy and the Privacy
Notice were both rewritten to say so. `web/tests.py` asserts that `csrftoken` is
the only cookie set anywhere and that a page without the form sets none, so those
pages stay true by failing rather than by being remembered.

---

## Migration from the monolith — done, and repeatable

The full public editorial corpus has been copied across. **This was a snapshot,
not a cutover**: haresign.net remains production, remains the publishing system
and remains the sending system. A delta run happens again shortly before launch.

| | Source | Imported |
|---|---|---|
| Articles | 67 | 67 (all published) |
| Tags | 24 | 24 |
| Newsletter issues | 4 | 4 (3 sent, 1 draft) |
| Subscribers | 175 | 175 (175 active, 0 opted out) |
| Featured images | 67 | 67 |
| Inline media files | 131 | 131 |

Nothing was skipped and no counts differ.

### The three commands

```bash
# 1. Export, read-only, from the monolith. Changes nothing there — which is why
#    the script lives in *this* repository and is piped in.
cd /path/to/haresign.net
docker compose exec -T haresign_net python manage.py shell \
    < /path/to/haresign-web/tools/export_from_monolith.py
docker compose cp haresign_net:/app/legacy_articles.json     _migration/
docker compose cp haresign_net:/app/legacy_newsletters.json  _migration/
docker compose cp haresign_net:/app/legacy_subscribers.json  _migration/
docker compose cp haresign_net:/app/uploads/blog    _migration/media/blog
docker compose cp haresign_net:/app/uploads/library _migration/media/library

# 2. Import here. Always dry-run first; --dry-run writes nothing, not even files.
python manage.py import_legacy_articles _migration/legacy_articles.json \
    --media-root _migration/media --dry-run
python manage.py import_legacy_articles _migration/legacy_articles.json \
    --media-root _migration/media --link-report _migration/links.json
python manage.py import_legacy_newsletters _migration/legacy_newsletters.json
python manage.py import_legacy_subscribers _migration/legacy_subscribers.json

# 3. Clean up. legacy_subscribers.json is a list of real email addresses.
rm -rf _migration/
```

Order matters once: articles before newsletters, because an issue's reading list
is resolved by article slug.

Every importer supports `--dry-run`, `--update-existing` / `--no-update-existing`
and `--since YYYY-MM-DD`.

### Idempotency, and where it was nearly wrong

Re-running is safe and is the intended way to do the final delta — matched on
`legacy_id` first (the source primary key) and slug second, so a slug corrected
on either side updates the same row rather than creating a second.

**Row-level idempotency is not file-level idempotency**, and that distinction
cost 147 duplicate image files before it was caught. Django's storage appends a
random suffix when a filename is taken, so `hero.png` is stored as
`hero_be1J5P7.png` — and a "have I already copied this?" check comparing whole
filenames never matches. Three import runs produced 214 files for 67 articles.
The check now compares the source *stem*. Same class of bug: `--dry-run` used to
copy 127MB of media and leave it there, because `transaction.atomic` rolls back
rows and not files.

### Delta import at cutover

```bash
# Re-export, then:
python manage.py import_legacy_articles     _migration/legacy_articles.json \
    --media-root _migration/media --since 2026-08-15 --dry-run
python manage.py import_legacy_articles     _migration/legacy_articles.json \
    --media-root _migration/media --since 2026-08-15
python manage.py import_legacy_newsletters  _migration/legacy_newsletters.json --since 2026-08-15
python manage.py import_legacy_subscribers  _migration/legacy_subscribers.json
python manage.py redirect_map --output redirects.csv
```

Note the asymmetry: **subscribers are re-run in full, without `--since`.**
`--since` filters on `subscribed_at`, so it would skip somebody who subscribed
last year and unsubscribed last week — and their unsubscribe is precisely what
must not be missed. The full run is cheap and correct.

### What the import does to article HTML

Bodies are copied byte-for-byte into `Article.body_source` and rewritten on the
way to `Article.body`, so every transform is auditable and re-runnable. Six rules,
documented in `insights/importing.py` and tested in `insights/tests_importing.py`:

| Rule | Applied | Why |
|---|---|---|
| Relative URLs → absolute | 33 | TinyMCE wrote `../../../../uploads/x.png`, which only resolves at the depth it was authored at |
| Legacy uploads → own media | 33 | An imported article must not depend on the monolith's volume being mounted |
| `/blog/x/` → `/insights/x/` | 10 | Only where `x` is genuinely being imported |
| Dead paths repaired | 6 | Over-deep relative links that **404 on haresign.net today** — verified, not assumed |
| Bootstrap collapse controls removed | 91 | No Bootstrap JS here, so they cannot work |
| …and their panels unhidden | 95 | Removing the button alone would hide each article's contents list on mobile, permanently |
| Leading headline block lifted out | 21 | Legacy articles open with a badge, an `<h1>` and a standfirst — the roles the template already fills, so it printed a second headline under the first |
| A later `<h1>` demoted to `<h2>` | 1 | Not the article's headline, so it is a section: kept, with the outline fixed |

Nothing in that block is thrown away. The headline text is offered as
`meta_title` and taken in **9 of 21** cases — only where it is longer than the
title, because these articles are live with the title as their `<title>` and
swapping in a shorter headline would make real search results worse to fix a
layout duplicate. The category badge becomes `kicker`, a field the template
already rendered and nothing was filling (5 of 5 available). The standfirst stays
as the article's opening paragraph — it differs from the summary in 10 of the 13
cases where both exist. Everything untaken remains in `body_source`.

### Featured images and alt text

No alt text was invented for the 67 imported images, because the monolith has no
such field. Instead the decision is made explicit: an image with a description
gets it, and an image without one is marked `alt="" role="presentation"` —
*declared* decorative rather than left with an empty alt indistinguishable from
somebody having forgotten.

Decorative is the correct answer here rather than a shrug: each image is a
designed header card whose visible text is the headline already printed beside
it, in all four places these render. An alt repeating it would make a screen
reader say the same words twice. The rule lives in
`insights/partials/_featured_image.html` — one file, because four copies of a
decision is how three of them end up wrong — and the admin has an **Image alt**
column and filter so "we decided" and "we never looked" stop looking the same.

Four legacy paths still need a decision at cutover and were **left unchanged
rather than guessed** — `/articles` and three `/media/downloads/*` files that do
not exist in the monolith either. Run with `--link-report` to list them.

### Redirect map

```bash
python manage.py redirect_map --output redirects.csv    # 74 rows
python manage.py redirect_map --format nginx
python manage.py redirect_map --format traefik
```

Derived from the `legacy_path` recorded on every imported row, so it cannot drift
from the content. **Deploy nothing yet** — these belong in the monolith's URLconf
or at Traefik when the domain actually moves.

---

## Architecture statement

> `haresign-web` owns the public Haresign web experience. It must not become the
> shared backend for the Haresign ecosystem. Identity, primary-care application
> data and client-specific application data will be owned by their respective
> services.

This is enforced, not just written down:

- **There is no database.** `DATABASES = {}` in `config/settings.py`. An
  accidental ORM import fails loudly rather than quietly opening a connection.
- **There is no auth, session, admin or contenttypes app.** Nothing here has a
  user, so nothing here needs a session cookie.
- **Every other platform is a URL in configuration**, never an import.

`web/tests.py::DecouplingTests` asserts all three, so a future change that
crosses one of these boundaries fails the build.

### Where this sits

```
                       haresign.net              (this repo, once promoted)
                             │
      ┌────────────┬─────────┴────────┬────────────────┐
      ▼            ▼                  ▼                ▼
   Haresign     Haresign           Haresign         Haresign
  Consulting   Intelligence        Community        Workspace
 consulting.       app.            community.        clients.
 haresign.net  haresign.net       haresign.net    haresign.net

                        identity
                            │
                            ▼
                     Haresign Account
                    auth.haresign.net
              (internally: "Haresign Core")
```

**"Haresign Core" is an internal architectural term** for the identity service
and appears only in documentation like this. Users see **Haresign Account**;
`NamingTests` asserts the internal term never reaches a page.

Each application will own its own repository and its own application data. The
identity service will later own identity, organisations, roles and entitlements,
and applications will integrate through authentication/API contracts — **never**
by sharing its database. None of that is implemented here.

---

## Stack, and why

| Choice | Reason |
|---|---|
| **Django 5.1** | Server-rendered HTML with real template inheritance and includes, which is what makes the component structure below possible. It also matches the stack the rest of Haresign already runs, so the same people can maintain it. |
| **No database** | This is a marketing site. Adding one would invite exactly the coupling this repo exists to avoid. |
| **Gunicorn + WhiteNoise** | Static files are hashed and compressed at build time and served straight from the app process. One container, no separate static host, correct far-future caching for free. |
| **Bootstrap 5 (vendored)** | Grid, Reboot and utilities only — the layout foundation. Haresign identity comes from our own tokens and components, never from Bootstrap overrides. Vendored rather than a CDN so the site has no external runtime dependency. |
| **No frontend framework** | There is one page and one interactive control. A build step and a hydration story would cost more than they return. `site.js` is ~60 lines of vanilla JS. |

---

## Directory structure

```
haresign-web/
├── config/
│   ├── settings.py          # all configuration; nothing secret has a default
│   ├── services.py          # the Haresign service registry (platform URLs)
│   ├── urls.py
│   └── wsgi.py
├── insights/                # editorial content (articles, categories, tags)
├── newsletter/              # subscriber list — collects, never sends
├── web/
│   ├── content.py           # platform cards, credibility, ecosystem routes
│   ├── faq.py               # umbrella FAQ content
│   ├── contact.py           # contact routes
│   ├── legal.py             # legal page metadata
│   ├── context_processors.py
│   ├── views.py
│   ├── tests.py
│   ├── urls.py
│   ├── templates/web/
│   │   ├── base.html
│   │   ├── home.html
│   │   ├── faq.html
│   │   ├── contact.html
│   │   ├── legal/           # shared shell + four documents
│   │   └── partials/
│   │       ├── header.html
│   │       ├── footer.html
│   │       ├── _platform_card.html
│   │       ├── _article_card.html
│   │       ├── _section_header.html
│   │       ├── _service_link.html
│   │       ├── _credibility.html
│   │       ├── _ecosystem_cta.html
│   │       ├── _newsletter.html
│   │       ├── _contact_route.html
│   │       ├── _faq_item.html
│   │       ├── _signin.html
│   │       └── _icon.html
│   └── static/
│       ├── css/
│       │   ├── tokens.css
│       │   ├── base.css
│       │   ├── layout.css
│       │   ├── components.css
│       │   └── pages/        # home, insights, legal, faq, contact
│       ├── js/site.js
│       ├── images/
│       └── vendor/bootstrap/
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

### Routes

| Route | Purpose |
|---|---|
| `/` | The umbrella homepage |
| `/faq/` | Umbrella FAQ — **ecosystem questions only** (see below) |
| `/contact/` | Contact *routing* — five routes, no form (see below) |
| `/insights/`, `/insights/<slug>/` | Editorial content |
| `/privacy/`, `/cookies/`, `/terms/`, `/accessibility/` | Legal pages |
| `/newsletter/subscribe/` | POST only; 405 on GET |
| `/newsletter/unsubscribe/<uuid>/` | GET offers, POST performs |
| `/health/` | Liveness probe — `{"status": "ok"}`, uncached, touches no dependency |
| `/robots.txt` | Follows `SITE_INDEXABLE`; disallows everything on beta |

---

## Design system

The point of this repository is to establish a frontend approach the other
Haresign applications can adopt. Two rules carry most of it.

**1. All brand values live in `tokens.css`.** Every other stylesheet reads from
it. No brand hex appears anywhere else — re-theming Haresign should be an edit
to one file, and a hard-coded colour elsewhere is a bug.

**2. No inline CSS.** No `<style>` blocks and no `style=""` attributes.
`web/tests.py` asserts this against the rendered page, so it fails the build
rather than drifting.

### CSS load order (the contract)

```
vendor/bootstrap  →  tokens  →  base  →  layout  →  components  →  pages/*
```

| File | Owns |
|---|---|
| `tokens.css` | Colour, type scale, spacing, radius, shadow, motion, layout and focus variables |
| `base.css` | Element defaults, focus treatment, skip link, reduced-motion |
| `layout.css` | Container, sections, header, nav, footer — structure only |
| `components.css` | Reusable UI: button, badge, eyebrow, card, platform card, article card, principle |
| `pages/home.css` | Only what exists on the homepage (mostly the hero) |

If something in `pages/` gets used on a second page, move it to
`components.css`.

### Typography

Headings use **Mona Sans**, body copy **DM Sans**, both self-hosted as latin
variable subsets (~77KB total, `web/static/fonts/`).

The production stylesheet names these two faces but its `@import` paths are
broken and no font files ship, so `haresign.net` has always rendered in the
browser's default sans. Serving them here delivers the typography the brand
already intended, and *removes* a third-party request rather than adding one —
there is no Google Fonts call, so nothing to disclose in a cookie banner. Body
copy is weight 500 at 1.75 line-height, matching production's 16px/28px setting.

### Colour hierarchy

Navy anchors, teal is the primary interactive colour, coral is warmth used
sparingly, aqua is the secondary data accent. Components reference
`--hs-primary`, so the hierarchy can move without touching them.

**`--hs-primary` is the deep teal `#0b7d7d`, not brand teal `#0fa3a3`.** Brand
teal gives white text only 3.09:1 and cannot legally carry a button label; the
deep teal is 4.95:1. Bright teal stays for marks and for text on navy (5.73:1).

Coral has **two** inks because the thresholds genuinely differ:

| Token | Use | Ratio |
|---|---|---|
| `--hs-coral-ink` `#cf353c` | small text (card CTA) | 4.97:1 — clears AA 4.5 |
| `--hs-coral-ink-large` `#e8484f` | large text only (hero emphasis) | 3.62:1 — clears the 3.0 large-text threshold |

Reaching for `--hs-coral` as a text colour is the mistake this prevents.

### Accent theming

A component sets `--hs-accent` once via an `.hs-accent-*` class and its children
read it. That is what lets **one** platform-card component render in four
colourways with no per-colour rules.

`--hs-accent-ink` exists separately because **fill and ink are not the same
variable**: brand coral passes contrast as a *mark* on white (3.03:1) but fails
as text, so anything typographic uses the darkened `--hs-coral-ink` (3.84:1).

### Palette validation

The four accents were validated, not chosen by eye:

```bash
python3 validate_palette.py "#FF5B61,#0FA3A3,#0D5BB8,#111827" light "#ffffff" all
```

Every pair clears the OKLab separation floors under normal vision, protanopia
and deuteranopia. Navy fails the *categorical-mark* lightness/chroma band, which
a near-black brand colour never will — it is a card accent beside a text label,
not a data mark, and every card names itself in words, so hue is never the only
cue. Re-run this before changing any brand colour.

### Components

| Partial | Notes |
|---|---|
| `header.html` | Brand, nav, Sign in. Responsive disclosure panel below 992px |
| `footer.html` | Platforms / Haresign / Legal, plus configurable company details |
| `_platform_card.html` | One component, four colourways |
| `_article_card.html` | Standard and `featured=True` variants |
| `_section_header.html` | Eyebrow + heading + lead; `split=True` adds a right-hand action |
| `_service_link.html` | A link to another platform — **or a plain label when it is not live** |
| `_signin.html` | Sign in, disabled until identity exists |
| `_icon.html` | Inline SVG by name; solid shapes, decorative and `aria-hidden` |
| `_credibility.html` | "Built around primary care" — principle + the fact behind it |
| `_ecosystem_cta.html` | The pre-footer band: four routes into Haresign |
| `_newsletter.html` | Sign-up block; `variant='inline'` for after an article |
| `_contact_route.html` | One contact route, with its pre-filled mail subject |
| `_faq_item.html` | `<details>`/`<summary>` disclosure — works with no JavaScript |

Plus CSS-only components: `.hs-link-arrow`, `.hs-input`, `.hs-notice`, and
button variants `--primary` (teal), `--navy`, `--light`, `--secondary`,
`--on-dark`. **Coral is never a button fill** — it is the warmth and emphasis
colour, and making it the default action would spend it.

Two components carry a rule worth restating: `_ecosystem_cta.html` and
`_newsletter.html` are included on pages whose own `pages/*.css` is not loaded,
so **their styles must live in `components.css`**. `.hs-section--cta` moved out
of `pages/home.css` for exactly this reason.

### Section rhythm

warm hero → white credibility → light platforms → navy principles → white
insights → navy CTA band → navy footer. No two adjacent sections share a ground,
so the page reads as a sequence rather than one long scroll of white cards on
pale grey.

---

## Nothing links to a service that does not exist

Three of the four platforms have no DNS yet. `config/services.py` holds a
registry of URLs plus an `available` flag driven by `HARESIGN_LIVE_SERVICES`.

- Available → a real link.
- Not available → a **label with a "Soon" badge**, or a disabled button plus a
  "Coming soon" badge on the platform card. Never an `<a>` to a dead host.

This applies in the **cards, the nav and the footer** — an early version guarded
only the cards, and the test suite caught the nav and footer still pointing at
subdomains that do not resolve.

Switching a platform on is a config change: add its slug to
`HARESIGN_LIVE_SERVICES` and restart. No code, no rebuild.

**Sign in is deliberately inert.** Authentication is not part of this
repository's scope, and a working-looking Sign in button implies otherwise. Add
`auth` to `HARESIGN_LIVE_SERVICES` when Core ships.

---

## Content

Page copy lives in Python, not in markup — so it can be tested, and so the
sections that will later be re-pointed have a seam.

| Module | Holds |
|---|---|
| `web/content.py` | Platform cards, the credibility items, the ecosystem routes, and `get_insights()` |
| `web/faq.py` | The umbrella FAQ, as sections of questions |
| `web/contact.py` | The five contact routes |
| `web/legal.py` | Metadata for the four legal pages (their prose is in templates) |

`get_insights()` is the seam between the homepage and editorial content.
Everything goes through it and callers get `Article` objects either way, so
re-pointing it is one function body — no template learns where an article came
from.

**No customer numbers, practice counts or performance claims appear anywhere.**
A test enforces it for the credibility section, which is where such a claim would
naturally be invented.

### Two sections became one

The homepage used to carry an abstract "principles" band *and* a strip of the
facts behind it — Evidence-led / Built from experience / Practical against 25+
years / NHS data / IGPM. They made the same four points twice. `CREDIBILITY` now
pairs each principle with the fact that substantiates it, and `PRINCIPLES` is
gone.

### The FAQ is an *ecosystem* FAQ

What Haresign is, who each platform is for, where the data comes from, whether
Haresign is part of the NHS. Consulting's own FAQs — how engagements start, day
rates, what is in a client portal — stay with Haresign Consulting; copying them
here would rebuild the mixed old homepage this architecture exists to separate. A
test asserts they have not crept in.

Answers are `<details>`/`<summary>`, not a JavaScript accordion: the browser
supplies the behaviour, the keyboard handling and the ARIA, and — the part that
matters — the answer is in the DOM whether open or not, so it works with scripts
off, is found by in-page search, and is readable by a crawler.

**There is deliberately no `FAQPage` structured data.** Google restricted FAQ
rich results to government and health bodies, so the markup is now pure
maintenance cost, and its standing risk is the structured copy drifting from the
visible copy. If it is ever added, generate it from `FAQ_SECTIONS`.

### Contact routes rather than captures

`/contact/` exists to get the right question to the right part of Haresign. Five
routes, each a `mailto:` with the subject already filled in — that subject line
is the entire mechanism, and it is what makes five routes better than one inbox.

**There is no form**, and that is load-bearing: the Privacy Notice states that
this site has no enquiry form. Adding one would mean spam handling, an SMTP
credential in this deployment, and a rewrite of that page. It is a decision to
take deliberately, not a detail to slip in with a routing page.

---

## Database

PostgreSQL, owned by this application. `docker-compose.yml` runs it as `web_db`
on its own volume — **not** the monolith's database, and never to be pointed at
it. `DecouplingTests` asserts there is exactly one alias and that its name is not
the monolith's.

```bash
docker compose up -d --build
docker compose exec haresign_web python manage.py migrate
docker compose exec haresign_web python manage.py createsuperuser
```

Variables: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`,
`POSTGRES_PORT`, `DB_CONN_MAX_AGE`. Host and port are set by compose to the
`web_db` service, so `.env` only needs them when running outside compose.

Discrete variables rather than a `DATABASE_URL`, so a password containing `@` or
`/` needs no encoding and cannot silently truncate a connection string.

`/health/` deliberately does **not** touch the database. It answers "is this
process serving requests", which is the only thing it can answer about itself; a
health check that fails on a dependency turns a working deploy into a red light.

## TinyMCE

Articles are authored in TinyMCE and stored as HTML — the same model as the
monolith's blog, deliberately, so legacy articles can be imported later without
rewriting a single one. Integration is
[`django-tinymce`](https://github.com/jazzband/django-tinymce) (Jazzband), served
from the installed package rather than a CDN, so the admin works on a locked-down
network and the site keeps no external runtime dependency.

Configuration is `TINYMCE_DEFAULT_CONFIG` in `config/settings.py`. The toolbar is
what Haresign articles actually use — headings, emphasis, links, lists, quotes,
tables, images, and a source view for fixing imported markup. `block_formats` is
restricted to the block types `.hs-prose` actually styles, so an author cannot
pick a heading level the design does not render.

`convert_urls: False` is set on purpose — see "Legacy image paths" below.

## Media

Uploaded images go to `MEDIA_ROOT` (bind-mounted at `./media`), never into
PostgreSQL: the database stores the path, the volume stores the bytes.

Storage is declared through `STORAGES['default']`, so moving to **Cloudflare R2**
later is a settings change plus a file copy:

```python
STORAGES['default'] = {'BACKEND': 'storages.backends.s3.S3Storage'}
```

The `Article` model, the templates and the admin are unaffected, because they
only ever touch `article.featured_image.url`.

In beta, media is served by a WhiteNoise wrapper in `config/wsgi.py` with
`autorefresh=True` — without it WhiteNoise indexes files once at boot and a newly
uploaded image would 404 until the container restarted.

### Legacy image paths

Monolith article bodies reference images as `../../../../uploads/library/…` — a
TinyMCE `convert_urls` artefact that resolves correctly only at the URL depth it
was authored at. So that imported articles render **without rewriting their
HTML**, beta also serves `/uploads/` from `MEDIA_ROOT/legacy`.

That is a comparison affordance, not the migration plan. The real import should
rewrite these paths to `MEDIA_URL`. The new editor sets `convert_urls: False` so
no future article acquires them.

## Migration from the monolith

Superseded — see **"Migration from the monolith — done, and repeatable"**
near the top of this file. The corpus has been imported; that section carries
the commands, the reconciliation and the delta-import procedure.

---

## Backup

Two things, and they are not the same thing:

- **PostgreSQL** — `pg_dump` of the `web_db` volume. Articles, taxonomy, admin users.
- **`./media`** — uploaded images. A database dump alone restores articles whose
  images are all broken.

---

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # then set SECRET_KEY, or just use DEBUG=True

DEBUG=True python manage.py runserver
```

`DEBUG=True` supplies a development `SECRET_KEY` so there is nothing to
configure to get started. With `DEBUG=False` and no key the app **refuses to
start** rather than running on a placeholder.

```bash
python manage.py test          # 28 tests, no database required
python manage.py check --deploy
```

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | — | **Required** when `DEBUG=False`. |
| `DEBUG` | `False` | |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated. |
| `LOG_LEVEL` | `INFO` | |
| `SITE_BASE_URL` | `https://beta.haresign.net` | Canonical origin for canonical/OG URLs. |
| `SITE_NAME` | `Haresign` | |
| `SITE_INDEXABLE` | `false` | **Opt-in.** Controls `noindex` and `robots.txt`. |
| `SITE_ENVIRONMENT_LABEL` | `Beta` | Header badge; empty string removes it. |
| `HARESIGN_URL_CONSULTING` | `https://consulting.haresign.net` | |
| `HARESIGN_URL_INTELLIGENCE` | `https://app.haresign.net` | Haresign Intelligence. |
| `HARESIGN_URL_COMMUNITY` | `https://community.haresign.net` | |
| `HARESIGN_URL_WORKSPACE` | `https://clients.haresign.net` | Haresign Workspace. |
| `HARESIGN_URL_ACCOUNT` | `https://auth.haresign.net` | Haresign Account. |
| `HARESIGN_URL_API` | `https://api.haresign.net` | Haresign API. |
| `HARESIGN_URL_DOCS` | `https://haresign.readthedocs.io/en/latest/` | Documentation — linked, never copied. |
| `HARESIGN_LIVE_SERVICES` | `intelligence,docs` | Comma-separated slugs that actually resolve. |
| `LEGAL_COMPANY_NAME` | `Haresign Consulting Services` | |
| `LEGAL_COMPANY_NUMBER` | *(unset)* | Omitted from the footer when blank. |
| `LEGAL_REGISTERED_ADDRESS` | *(unset)* | Omitted when blank. |
| `LEGAL_ICO_REGISTRATION` | *(unset)* | Omitted when blank. |
| `LEGAL_CONTACT_EMAIL` | `contact@haresign.net` | |
| `GUNICORN_WORKERS` / `_THREADS` / `_TIMEOUT` | `2` / `4` / `30` | |
| `SECURE_SSL_REDIRECT` | `true` | Set `false` when running without a TLS proxy. |

> **Legal details are placeholders by design.** The real company number,
> registered address and ICO registration belong to the business, not to this
> repository. Unset values are *omitted* from the footer rather than shown as
> invented text. (The four legal pages now exist and are real links.)

---

## Docker

```bash
docker compose up -d --build
```

The image runs as an unprivileged user, has no build toolchain or database
client, runs `collectstatic` at **build** time (so every container in a rollout
serves byte-identical assets and start-up cannot fail doing work), and carries a
`HEALTHCHECK` against `/health/`.

`docker-compose.yml` joins the existing external `t3_proxy` network and carries
Traefik labels for `beta.haresign.net`.

---

## Deployment — `beta.haresign.net`

DNS, TLS and the Traefik route already exist for this hostname; it is currently
served by the **monolith** (`HaresignDotNet`). Pointing it here is a cutover, not
a new setup.

1. **Create `.env`** on the host from `.env.example` and set `SECRET_KEY`.
2. **Stop the monolith answering for this host.** Remove
   `|| Host(\`beta.haresign.net\`)` from `haresign-rtr.rule` and unset
   `BETA_HOST` in the monolith's `docker-compose.yml`, then `docker compose up -d`
   there. The router here sets `priority=200` so it wins even before that
   happens, but leaving two routers claiming one hostname is a trap for whoever
   next edits either file.
3. **Bring this up**: `docker compose up -d --build`.
4. **Verify**: `curl -sS https://beta.haresign.net/health/`.

TLS needs nothing new — certificates are issued per Traefik *entrypoint* as a
wildcard for `*.haresign.net`, and Cloudflare DNS for `beta` already resolves.

### Promoting to production

1. Point `haresign.net` at this service.
2. `SITE_BASE_URL=https://haresign.net`, `SITE_ENVIRONMENT_LABEL=`,
   `SITE_INDEXABLE=true`.
3. Publish the legal pages and replace the footer placeholders.

---

## The Insights index: paging, filters and image weight

67 articles were rendering on one page. The markup was fine — 70KB for the lot —
but the hero images behind it came to **64.8 MB**, averaging 991 KB each, and
that grows with every article published. Lazy loading meant nothing looked
broken, which is why it went unnoticed: the cost lands on whoever is reading on
a phone on mobile data.

### Paging

12 per page, six pages. Previous / position / next rather than a strip of page
numbers — six numbered links is a row of near-identical small targets on a phone,
and "Page 2 of 6" answers the question the numbers exist to answer.

The featured article leads **page one only, and only unfiltered**: on page two it
is stale furniture, and under a filter it is an article ignoring the filter the
reader just set.

An unknown tag or an out-of-range page is a **404, not an empty list** — those
URLs name something that does not exist, and "no articles found" invites the
reader to conclude the archive is empty. Note `InvalidPage`, not `EmptyPage`:
Django raises `PageNotAnInteger` for `?page=abc`, which is a *sibling* rather
than a subclass, and catching only `EmptyPage` turned a junk query string into a
500.

### Filters, and why they print their counts

The tags are topical labels rather than a taxonomy. The median article carries
five, and the largest covers more than half the archive:

```
Governance 36 · Practice Management 32 · Workforce 31 · Operational Risk 29
Compliance 29 · NHS Contracts 22 · Access 19 · Digital Tools 18 · Finance 17
```

A chip that silently returns 36 of 67 articles feels broken. One that says
`Governance (36)` is telling the reader what it will do before they spend a click
finding out — which is why the counts are part of the control rather than
decoration, and why only the top ten are offered.

Counts are taken over **live** articles, so a count can never promise more than
the filter delivers. Everything is a plain link: no JavaScript filters the page,
every filtered view has its own URL to bookmark, the back button behaves, and
each view canonicalises to itself rather than to page one.

### Images

```bash
python manage.py optimise_images --dry-run
python manage.py optimise_images
```

| | Before | After |
|---|---|---|
| What a WebP browser downloads | 64.8 MB | **4.9 MB** (−93%) |
| What a browser without WebP downloads | 64.8 MB | 57.2 MB (−12%) |

Two files per image: the original path is resized in place **in its own format**,
so it stays the `<img src>` and every existing reference keeps working; and a
`.webp` sibling is written and offered first through `<picture>`.

WebP alone would be smaller still, but this audience includes locked-down NHS
desktops — the fallback costs one element and means a browser that has never
heard of WebP gets an image rather than a broken one. The `<source>` is emitted
only when the file genuinely exists (`Article.featured_image_webp_url`), because
a `<source>` pointing at a missing file breaks the image for *everyone else*.

**Originals are never destroyed**: every file is copied to `insights/original/`
before it is touched, and that directory is served by nothing. Re-run the command
after any import; it skips what it has already done.

The fallback only improves 12% because these are PNG exports already at or below
the width limit — PNG is simply the wrong format for a photographic composite,
and converting it would change the file extension and therefore every stored URL.
Since WebP has been universal since Safari 14, the 4.9 MB figure is what nearly
every reader actually experiences.

---

## Responsive and accessibility QA

```bash
pip install playwright && python -m playwright install --with-deps chromium
python qa/responsive.py                 # against beta
python qa/responsive.py --screenshots   # also writes qa/screenshots/
```

**1,228 checks across 7 viewports (320–1440px) and 15 pages**, driven through a
real Chromium. Deliberately outside `manage.py test`: the unit suite must not
need a browser or a network, and "does this overflow at 320px" has no answer
without layout.

Functional assertions, not screenshot diffs — a pixel-comparison suite on a site
under active design breaks on every intentional change and teaches everyone to
ignore it. What is asserted is what never intentionally changes: no horizontal
overflow, images inside their column, one `<h1>`, headings that descend, 24px
minimum targets, the mobile nav opening and closing on Escape, `<details>`
working by keyboard, a visible focus ring, and reduced motion being honoured.
Screenshots are written for a person to look at, not compared.

It found four real defects, all now fixed:

- **Tap targets below 24px** (WCAG 2.2 SC 2.5.8) throughout the footer, the legal
  contents rails, the policy cross-links and every `.hs-link-arrow` — 20–22px
  tall at 17px type. These are lists of links, not words in a sentence, so the
  standard's inline exception does not cover them.
- **`.hs-icon` had no default size.** `_icon.html` sets no width or height, so an
  icon in any context without a container rule fell back to the browser's
  default replaced-element size. The 390px homepage screenshot showed the arrow
  inside "Explore our platforms" several times the height of its own label — a
  defect no CSS reading would have found.
- Two bugs in the QA suite itself: it checked focus by calling `.focus()`, which
  deliberately does not match `:focus-visible`, and reported a defect that was
  purely an artefact of how it looked; and it named an article slug that does not
  exist.

One warning is left and is content, not layout: four places in the archive skip
from an `<h2>` to an `<h4>`. That is editorial work, not something a script
should do to published articles.

---

## Analytics — what is here, and what production does

**This site runs no analytics.** No Google Analytics, no tag manager, no
third-party measurement of any kind, and no requests to any external host: fonts,
styles, scripts and images are all served from here. A test asserts it, because
the Privacy Notice, the Cookie Policy *and* the Accessibility Statement all
depend on it being true.

**Production haresign.net runs GA4** (`G-F6H5DE6RQM`), loaded only after explicit
consent through the cookie banner in `base_site.html`. That is a correct PECR
implementation; it is simply not carried over here.

That was deliberate, not an omission. Migrating GA because the legacy site had it
would import a consent banner, a third-party request and a cookie into a site
that currently needs none of them — and the consent rate on such a banner means
the data is partial anyway. Three options, for a decision before cutover:

| Option | Consent needed | Cost |
|---|---|---|
| **Nothing** (today) | No | No visitor numbers at all |
| **Server-side log analysis** (GoAccess over Traefik logs) | No — no cookie, no device access | A container; no per-visitor journeys |
| **Privacy-first analytics** (Plausible / Umami, self-hosted) | Generally no cookie; check placement | A container; one external request unless proxied |
| **GA4, as production** | **Yes** — banner + policy rewrite | Loses the "no cookies, no trackers" position |

The middle two keep the current cookie position intact, which is worth more on a
healthcare-adjacent site than a funnel report. **If GA4 is chosen, the Cookie
Policy and Privacy Notice must be rewritten first** — both currently state
plainly that nothing measures visitors.

---

## Accessibility

Semantic landmarks, one `<h1>` per page, labelled sections, a skip link,
`:focus-visible` rings (including a forced-colors fallback), 44px touch targets,
`prefers-reduced-motion` honoured, decorative graphics `aria-hidden`, and
unavailable actions exposed via `aria-describedby` rather than colour alone.

Automated checks cover the heading count, the skip link and the absence of
inline styles. **Manual testing with a screen reader and a real keyboard has not
been done** and should happen before promotion.

---

## Next improvements

- Real `/insights/` and article pages, replacing `get_insights()` with a content
  source.
- The Privacy / Cookies / Terms / Accessibility pages.
- An OG share image designed for the umbrella brand (currently the favicon).
- A sitemap, once there is more than one page.
- Lighthouse and axe runs, plus screen-reader testing, before promotion.
