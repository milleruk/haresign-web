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
├── web/
│   ├── content.py           # page copy + the insights content seam
│   ├── context_processors.py
│   ├── views.py
│   ├── tests.py
│   ├── urls.py
│   ├── templates/web/
│   │   ├── base.html
│   │   ├── home.html
│   │   └── partials/
│   │       ├── header.html
│   │       ├── footer.html
│   │       ├── _platform_card.html
│   │       ├── _article_card.html
│   │       ├── _section_header.html
│   │       ├── _service_link.html
│   │       ├── _signin.html
│   │       └── _icon.html
│   └── static/
│       ├── css/
│       │   ├── tokens.css
│       │   ├── base.css
│       │   ├── layout.css
│       │   ├── components.css
│       │   └── pages/home.css
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

Plus CSS-only components: `.hs-credibility` (the factual strip), `.hs-cta-band`
(the closing band), and button variants `--primary` (teal), `--navy`, `--light`,
`--secondary`, `--on-dark`. **Coral is never a button fill** — it is the warmth
and emphasis colour, and making it the default action would spend it.

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

Page copy lives in `web/content.py`, not in markup — so it can be tested, and so
the insights section has a seam.

```python
def get_insights(limit=4):
    """Today: a placeholder list. Tomorrow: a CMS or content API."""
```

Everything goes through this one function and callers get `Article` objects
either way, so re-pointing it at a real source is one function body — no
template learns where an article came from.

The current articles are **placeholders and are labelled "Sample" on the page**.
They assert no findings, figures or outcomes: a placeholder that reads as real
research is a claim nobody made. They also carry no URL, so they render as
static cards rather than dead links.

No customer numbers, practice counts or performance claims appear anywhere.

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

Legacy content is untouched. `insights/management/commands/import_legacy_articles.py`
performs a **one-way** import from a JSON export — it never connects to the
monolith's database, because that would be the shared-database coupling this
repository exists to avoid, and would make beta depend on production being up.

In the monolith:

```bash
docker compose exec haresign_net python manage.py dumpdata \
    website.BlogPost website.BlogTag --indent 1 > legacy_articles.json
```

Then here:

```bash
docker compose run --rm \
    -v "$(pwd)/legacy_articles.json:/tmp/legacy.json:ro" \
    -v "/path/to/monolith/uploads:/tmp/legacy-media:ro" \
    haresign_web python manage.py import_legacy_articles /tmp/legacy.json \
    --media-root /tmp/legacy-media --dry-run --only <slug> <slug>
```

Drop `--dry-run` to commit, drop `--only` to take everything. Matched on slug and
idempotent, so the delta import at cutover is the same command again.

| legacy | → | `insights.Article` |
|---|---|---|
| `title` | → | `title` |
| `slug` | → | `slug` (unchanged, so `/blog/x/` → `/insights/x/` holds) |
| `excerpt` | → | `summary` |
| `content` | → | `body` (HTML verbatim) |
| `author_name` | → | `author_name` |
| `published_date` (date) | → | `published_at` (aware datetime, 09:00 local) |
| `is_published` | → | `status` |
| `hero_image` | → | `featured_image` |
| `tags` | → | `tags` |

Legacy has **no categories, kicker, meta fields or featured flag**, so those are
left empty rather than invented.

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
| `HARESIGN_LIVE_SERVICES` | `intelligence` | Comma-separated slugs that actually resolve. |
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
> invented text. The Privacy / Cookies / Terms / Accessibility footer links are
> structured but render as text with a "Soon" badge until those pages exist — a
> Privacy link that 404s on a healthcare site is worse than one visibly still to
> come.

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
