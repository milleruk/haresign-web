# haresign-web

The public Haresign web layer — the umbrella site that introduces the Haresign
ecosystem and sends people to the right platform.

Currently deployed as a preview at **`beta.haresign.net`**, where the future
`haresign.net` homepage is designed and reviewed before it replaces production.

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
                    haresign.net            (this repo, once promoted)
                          │
      ┌───────────┬───────┴───────┬───────────────┐
      ▼           ▼               ▼               ▼
 consulting.   app.          community.      clients.
 haresign.net  haresign.net  haresign.net    haresign.net

                    identity
                        │
                        ▼
                 auth.haresign.net
                   Haresign Core
```

Each application will own its own repository and its own application data. Core
will later own identity, organisations, roles and entitlements, and applications
will integrate through authentication/API contracts — **never** by sharing its
database. None of that is implemented here.

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
| `_icon.html` | Inline SVG by name; decorative and `aria-hidden` |

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
| `HARESIGN_URL_APP` | `https://app.haresign.net` | |
| `HARESIGN_URL_COMMUNITY` | `https://community.haresign.net` | |
| `HARESIGN_URL_CLIENTS` | `https://clients.haresign.net` | |
| `HARESIGN_URL_AUTH` | `https://auth.haresign.net` | |
| `HARESIGN_LIVE_SERVICES` | `app` | Comma-separated slugs that actually resolve. |
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
