---
name: urlovingly-workspace
description: Complete context for the URLovingly workspace (personalized digital event invitations). MUST be read before making any change in this repository and updated after every change that alters structure, behaviour, commands, configuration, data or decisions. Covers the Flask customer app (plans, Gmail login, payments, studio, guest-link hosting), the Cloudflare Worker + D1 edge hydration service, the legacy static generator, tests, conventions and change log.
---

# URLovingly workspace skill

> **Rule for every AI model working here:**
> 1. **Read this whole file before editing anything.**
> 2. Make the change.
> 3. **Update this file in the same change** if you added, removed, renamed or altered files, routes, tables, env vars, commands, plans, behaviours, conventions or decisions. Add one line to the [Change log](#13-change-log).
> 4. Run the tests (section 9). `tests/test_skill_file.py` fails when this file no longer mentions a module, directory, edge file or environment variable that exists.
> 5. If the requirement set changed, update `docs/REQUIREMENTS.md` (the specification) too.

---

## 1. What this project is

URLovingly lets a host turn a celebration into an animated, mobile-first invitation website with a **personalized link per guest or family**: `/<celebration-slug>/to/<guest-slug>/` (for example `/aarav-and-priya/to/rahul-sharma-and-family/`).

Customers see a public landing page (features, uniqueness, pricing, payment portal), choose a plan, sign in with **Gmail**, pay if the plan is paid, and only then reach the **studio** where they enter event and guest details. The studio shows only the options included in the plan.

Currency is INR; amounts are stored in paise. Primary audience is Indian weddings and family ceremonies (muhurtham, Haldi, UPI Shagun, WhatsApp sharing).

## 2. The three parts of the repository

The git repository root is the `Invitation/` folder (the VS Code workspace root is its parent `P1/`, which is **not** a git repo).

| Part | Location | Status | Role |
|---|---|---|---|
| **A. Customer app (Flask + SQLite)** | `server/`, `index.html`, `private/studio.html`, `private/owner.html`, `schema.sql`, `run.py` | Active, tested | Landing page, Google sign-in, plans, payments, plan-gated studio, owner-only customer and asset dashboard, publishing and hosting guest links, RSVP, WhatsApp, UPI, audio |
| **B. Edge hydration (Cloudflare Worker + D1)** | `edge/` | Active, independent | Serves `/:couple_slug/to/:guest_slug` by reading D1 and filling one HTML template at request time (no per-guest static files) |
| **C. Legacy static pipeline** | `generate.py`, `.github/workflows/urlovingly-builder.yml`, `aarav-and-aleena/`, `aarav-and-priya/`, `groom-and-bride/` | Legacy, untouched | Old flow: a Cloudflare Worker (not in this repo) triggered GitHub Actions, which committed one static `index.html` per guest to GitHub Pages. The studio no longer uses it |

**A and B do not share a database or code.** A stores invitations as full HTML in its own SQLite `invites` table and serves them itself. B reads a separate D1 database (`couples`, `guests`). Nothing writes into D1 yet; rows are created with SQL (`edge/seed.sql`) or `wrangler d1 execute`. Connecting the studio to D1 is future work.

## 3. Directory map

```
Invitation/
  index.html                  Public landing page (Tailwind CDN, inline JS). Plans, checkout modal, Google + dev sign-in; relative logo paths support GitHub Pages project sites; the hero phone previews the Royal design (`.rp-*` CSS, static copy of `templates/royal`)
  private/studio.html         The studio. NOT public; served by GET /studio after sign-in
  private/owner.html          Owner dashboard UI. NOT public; served only by GET /owner for the configured Google account
  URLovingly_Icon.jpg         Logo (served at /URLovingly_Icon.jpg)
  schema.sql                  SQLite schema for part A (loaded by server/db.py)
  run.py                      python run.py --dev  -> http://127.0.0.1:5000
  req.txt / req-dev.txt       Runtime deps (jinja2, flask, google-auth, requests) / + pytest
  generate.py                 LEGACY static generator (part C)
  templates/<name>/index.html 8 invitation designs used by the studio (placeholders like {{ guest_name }}, filled in the browser)
  server/                     Part A backend package (see 5)
  tests/                      pytest suite for part A + docs drift check
  docs/REQUIREMENTS.md        Software requirements specification with traceability matrix
  docs/raspberry-pi-free-hosting.txt  Step-by-step Raspberry Pi deployment using Gunicorn and Tailscale Funnel, with OAuth/payment limitations
  edge/                       Part B Cloudflare Worker project (see 6)
  .github/workflows/          Legacy GitHub Actions builder (part C)
  .github/skills/urlovingly-workspace/SKILL.md   THIS FILE
  AGENTS.md, .github/copilot-instructions.md      Tell AI models to read this file first
  data/                       Runtime SQLite DB + uploaded audio (git-ignored, created on first run)
```

## 4. Plans and entitlements (source of truth: `server/plans.py`)

| | Free Tier (Trial) | Standard Celebration | Grand Celebration |
|---|---|---|---|
| id | `free` | `standard` | `grand` |
| Price | ₹0 | ₹999 / event (99 900 paise) | ₹2,499 / event (249 900 paise) |
| Guest links | 5 | 100 | 500 |
| Hosting per link | 7 days | 180 days (6 months) | 365 days (1 year) |
| Features | none | `whatsapp_generator`, `rsvp_dashboard` | those two + `multi_day_routing`, `upi_shagun`, `custom_audio` |

Business rules: one free trial per Google account (even after upgrading it); one payment covers one **event**; features unlock only after payment is confirmed; hosting is counted per link from first publication (re-publishing does not extend it, upgrading recalculates it); re-publishing the same guest does not use quota; upgrade price = difference between plans, downgrade not allowed. Prices on `index.html` are static HTML and are checked against `plans.py` by a test, so **change both together**.

## 5. Part A: Flask customer app

### 5.1 Modules (`server/`)
| File | Responsibility |
|---|---|
| `server/__init__.py` | `create_app(overrides)`: config, DB init, blueprints, CSRF header check, security headers, JSON errors for `/api/`, production safety checks |
| `server/config.py` | `load_config()` reads environment variables (section 8) |
| `server/db.py` | SQLite connection per request (autocommit), `tx()` = `BEGIN IMMEDIATE` transaction helper, `init_db()` applies `schema.sql` and seeds plans |
| `server/plans.py` | Plan catalogue, feature labels, `seed_plans()` |
| `server/util.py` | `now()` (patched in tests), ISO helpers, `slugify()` (ASCII only, fallback `event`/`guest`) |
| `server/errors.py` | `api_error()` JSON error helper: `{"error": code, "message": text, ...}` |
| `server/auth.py` | Google ID-token login, Gmail-only rule, dev login, sessions (HttpOnly cookie `urlovingly_session`, SHA-256 hashed in DB, 7-day TTL), `login_required` |
| `server/models.py` | `event_dict()`, link counting, `upgrade_price()`, `invite_expiry()`, template discovery, `base_url()` |
| `server/payments.py` | `MockProvider`, `RazorpayProvider`, order creation, signature verify, webhook, idempotent `mark_paid()`, upgrades, payment history |
| `server/events.py` | Plans/config/me endpoints, create event (choose plan), publish/list invites, authenticated CSV/XLSX guest-import preview, WhatsApp generator, RSVP dashboard, UPI settings, audio upload/delete |
| `server/imports.py` | UTF-8 CSV and first-worksheet XLSX parsing; 2 MB file, 5 MB expanded XLSX, 64-entry and 500-guest limits; normalizes guest-name, phone and personal-note headers |
| `server/owner.py` | Private read-only owner dashboard API; exact configured email plus Google subject required; returns customer, event, link and stored-file metadata only |
| `server/pages.py` | Landing, logo, gated `/studio`, gated `/templates/<name>/index.html`, public guest page with feature-block injection, public RSVP endpoint (CORS `*`), audio streaming |

### 5.2 Database tables (`schema.sql`)
`plans`, `users` (customer details), `sessions`, `events` (one per celebration; `plan_id`, `status` = `pending_payment`|`active`, `is_trial`, `upi_id`, `upi_name`, `audio_file`), `payments`, `invites` (full HTML + slugs, `UNIQUE(couple_slug, guest_slug)`, `expires_at`), `rsvps` (one per invite). Foreign keys are ON.

### 5.3 HTTP routes
Public: `GET /`, `GET /api/config`, `GET /api/plans`, `POST /api/auth/google`, `POST /api/auth/dev-login` (dev only), `POST /api/auth/logout`, `GET /<couple>/to/<guest>/`, `POST|OPTIONS /api/rsvp/<invite_public_id>`, `GET /media/audio/<event_public_id>`, `POST /api/payments/razorpay/webhook`.
Session required: `GET /studio`, `GET /owner` (configured Google owner only), `GET /templates/<name>/index.html`, `GET /api/me`, `GET /api/owner/overview` (owner only; no-store metadata; excludes guest phone, personal notes and invitation HTML), `POST /api/events`, `GET /api/events/<id>`, `POST /api/payments/order`, `POST /api/events/<id>/upgrade`, `POST /api/payments/verify`, `POST /api/payments/mock-confirm` (mock only), `GET /api/payments`, `GET|POST /api/events/<id>/invites`, `POST /api/events/<id>/guest-import/preview` (multipart `file`; returns parsed rows and remaining quota, creates no links), `POST /api/events/<id>/whatsapp`, `GET /api/events/<id>/rsvps`, `PUT /api/events/<id>/settings`, `POST|DELETE /api/events/<id>/audio`.

Feature errors: 403 `feature_not_in_plan` (with `feature`, `required_plan`); 402 `event_not_active` for unpaid events; 403 `link_limit_reached`; 409 `slug_taken`, `trial_already_used`.

### 5.4 Security rules (do not weaken)
- Every state-changing `/api/` call needs header `X-Requested-With: urlovingly` (except public RSVP and the webhook). The studio/landing JS and the test `Api` helper send it.
- Entitlements are enforced **on the server**; hiding things in the UI is only cosmetic.
- Price/amount always comes from `plans.py`, never from the client.
- Customer-supplied invitation HTML is served with `Content-Security-Policy: sandbox allow-scripts …` and **without** `allow-same-origin`. Server-added blocks (RSVP, UPI, audio) escape customer data.
- Production (`URLOVINGLY_ENV` ≠ `development`) refuses to start with mock payments or dev login.
- `/owner` and `/api/owner/overview` require the exact configured `URLOVINGLY_OWNER_EMAIL` and a Google-authenticated account (`google_sub` present); developer-login sessions never qualify. Empty owner configuration disables access. Responses are private/no-store, noindex, non-framable and omit guest phone, personal notes and invitation HTML.
- Audio type is sniffed from file content (MP3/M4A/OGG), ≤3 MB, stored under server-generated names.
- Use parameterised SQL only.

### 5.5 Studio frontend (`private/studio.html`)
- Starts from the original single-page studio. All network calls use the local `api()` helper against the Flask API (no Cloudflare/GitHub calls remain).
- `bootStudio()` loads `/api/me`, keeps only active events, picks one (localStorage `urlovingly_active_event`), then `applyEventPlan()` toggles every `[data-feature="<feature_key>"]` block using `activeEvent.features`. New plan-gated blocks must carry `class="hidden"` plus `data-feature`.
- The invitation HTML is rendered **in the browser** from `/templates/<name>/index.html` (lowercase placeholders such as `{{ guest_name }}`, `{{ couple_names }}`) and posted as `rendered_html`. Routing (Grand) filters ceremonies client-side and sends `allowed_ceremonies`.
- The live preview does not include RSVP/UPI/audio blocks; the server adds them when serving the published page.
- Guest-list import accepts UTF-8 `.csv` and `.xlsx` (first worksheet), with a downloadable CSV header template. Required column: `Guest Name`; optional columns: `WhatsApp Number`, `Personal Note`. Preview validates the file; the studio checks remaining plan capacity and publishes each guest through the normal invite API, which remains the quota and ownership authority. Limits: 2 MB, 500 guest rows; XLSX expanded content ≤5 MB and ≤64 archive entries.
- The landing page (`index.html`) drives plan choice, sign-in and checkout with its own inline JS; `?upgrade=<event_id>`, `?choose=plan`, `?signin=1` are supported.
- Logo assets and the header home link are relative for GitHub Pages project subpaths. The Google Identity Services button is rendered when the visible login modal opens (with a public client ID fallback), but GitHub Pages has no `/api/config`, `/api/plans` or auth API: it can show marketing/pricing and the account chooser, while completing sign-in/checkout still requires the Flask backend. Register each deployed site origin in Google OAuth settings; paths are not included in authorized JavaScript origins. If Google rejects the origin (its iframe stays 0x0 after about 8 s), the modal shows a message naming the origin to authorize.

## 6. Part B: Edge hydration (`edge/`)

Goal: **no static file per guest**. One Worker looks the guest up in D1 and fills one template.

```
Request GET /:couple_slug/to/:guest_slug
  -> router.js   matches ^/([a-z0-9-]{1,100})/to/([a-z0-9-]{1,100})/?$  (lower-cased)
  -> db.js       D1 SELECT guests JOIN couples WHERE couple_slug=?1 AND guest_slug=?2  (bound params)
  -> not found   clean 404 HTML page
  -> template.js env.ASSETS.fetch("/templates/<template_id>.html"), fallback to base
  -> render.js   single-pass replace of {{PLACEHOLDER}} with HTML-escaped values
  -> 200 text/html
```

| File | Role |
|---|---|
| `edge/wrangler.toml` | Worker `urlovingly-invites`; bindings `DB` (D1 `urlovingly-invites`), `ASSETS` (`./public`, `run_worker_first = true`, `html_handling = "none"`) |
| `edge/worker.js` | **Single-file build of the whole Worker** for pasting into the Cloudflare dashboard editor (Workers & Pages > Edit code). Needs only a D1 binding named `DB`. Templates are embedded in its `TEMPLATES` map; `TEMPLATES.base` must stay identical to `edge/public/templates/base.html` (checked by `tests/test_skill_file.py`). Any logic change in `edge/src/` must be mirrored here |
| `edge/package.json` | Scripts: `dev`, `deploy`, `test`, `db:create`, `db:migrate:local|remote`, `db:seed:local|remote` |
| `edge/migrations/0001_create_invitations.sql` | D1 schema: `couples(couple_slug PK, couple_names, event_date, venue)`, `guests(couple_slug, guest_slug, guest_name, custom_note, template_id DEFAULT 'base')`, unique `(couple_slug, guest_slug)`, slug `CHECK`s |
| `edge/seed.sql` | Sample rows for local testing |
| `edge/public/templates/base.html` | The base Tailwind template (mobile-first). Placeholders: `{{GUEST_NAME}}`, `{{COUPLE_NAMES}}`, `{{CUSTOM_NOTE}}`, `{{EVENT_DATE}}`, `{{VENUE}}` (uppercase; unknown ones render empty) |
| `edge/src/index.js` | Worker entry: method check (GET/HEAD only), orchestration, error handling → 500 |
| `edge/src/router.js` | `matchInvitePath()` |
| `edge/src/db.js` | `findInvitation()` |
| `edge/src/template.js` | `loadTemplate()` with fallback to `base` |
| `edge/src/render.js` | `escapeHtml()`, `buildValues()` (defaults for empty note/date/venue), `hydrate()` |
| `edge/src/responses.js` | HTML/404/405/500 responses and shared security headers |
| `edge/test/worker.test.js` | `node --test` suite using fake D1 and fake assets (Node 20+, no dependencies) |
| `edge/test/single-file.test.js` | Smoke tests for `edge/worker.js` (fake D1 only) |

Rules for B: add new placeholders in three places (template, `buildValues`, this table); never put raw user data into HTML without `escapeHtml`; keep SQL parameterised; a new template is just `edge/public/templates/<id>.html` and a `template_id` value (`[a-z0-9-]`).

The `aarav-and-priya`, `rahul`, and `stranger` strings in Worker comments, tests and `edge/seed.sql` are example/test data only. The route extracts any valid couple and guest slugs and queries D1; no example slug is hard-coded into routing. `edge/seed.sql` is demo data, not a customer list. Each real link needs matching `couples` and `guests` rows in D1. **Part A currently writes to SQLite and does not synchronize invitations to D1**, so new studio customers will not appear on the Worker until an integration or data-population process is added. For Cloudflare dashboard deployment: create/bind D1 as `DB`, run `edge/migrations/0001_create_invitations.sql` once, paste/deploy `edge/worker.js`, and attach the Worker to an invitation-only hostname such as `invites.example.com/*`. Avoid routing the main site root to this Worker unless it also forwards non-invitation routes. Use authenticated app-to-D1 synchronization for production; D1 console inserts are suitable only for testing/manual records.

Deploy with wrangler: `cd edge`, `npm install`, `npx wrangler d1 create urlovingly-invites`, paste the id into `wrangler.toml` (`database_id`), `npm run db:migrate:remote`, optionally `npm run db:seed:remote`, `npm run deploy`. Deploy via the dashboard instead: paste `edge/worker.js` into the Worker editor, add a D1 binding named `DB`, and run `edge/migrations/0001_create_invitations.sql` in the D1 console. Local: `npm run db:migrate:local`, `npm run db:seed:local`, `npm run dev`, open `/aarav-and-priya/to/rahul-sharma-and-family`.

**Verification status:** the authoring environment had no Node/npm, so the Worker and its tests were written but **not executed** there. Run `npm test` and `npm run dev` in `edge/` before relying on them, then record the result in the change log.

## 7. Part C: legacy static pipeline
`generate.py` reads `GUEST_NAME`, `COUPLE_NAMES`, `RENDERED_HTML` from the environment and writes `<couple-slug>/to/<guest-slug>/index.html`. The GitHub workflow runs it on `repository_dispatch` (`generate_invite`). Existing sample output folders are kept as-is. Do not extend this path; use A or B.

## 8. Configuration (environment variables)
| Variable | Default | Meaning |
|---|---|---|
| `URLOVINGLY_ENV` | `production` | `development` enables mock payments and developer sign-in |
| `URLOVINGLY_DB` | `data/urlovingly.db` | SQLite file |
| `URLOVINGLY_MEDIA` | `data/media` | Uploaded audio folder |
| `GOOGLE_CLIENT_ID` | project client id in `config.py` | Google OAuth client. Change it in `GOOGLE_CLIENT_ID` (environment, preferred), `DEFAULT_GOOGLE_CLIENT_ID` in `server/config.py`, and the `google-client-id` meta tag in `index.html` (static fallback used when the Flask API is unreachable, e.g. GitHub Pages); keep all three identical. Its allowed JS origins must include the site origin; `localhost` is not allowed for the default id, so use dev sign-in locally) |
| `URLOVINGLY_ALLOWED_EMAIL_DOMAINS` | `gmail.com,googlemail.com` | Empty value removes the Gmail-only rule |
| `URLOVINGLY_DEV_LOGIN` | `1` in development, else `0` | Developer sign-in switch |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | empty | Enable the real payment provider (required in production) |
| `RAZORPAY_WEBHOOK_SECRET` | empty | Enables `/api/payments/razorpay/webhook` |
| `URLOVINGLY_PUBLIC_URL` | `https://invite-guests.urlovingly-comp.workers.dev` in `server/config.py` | Base URL used in generated links; production Flask deployments must override it with the Flask app's canonical HTTPS origin because the Worker is not synchronized with SQLite |
| `URLOVINGLY_OWNER_EMAIL` | empty | Exact Google account allowed into `/owner`; empty disables the owner dashboard |

## 9. Commands (Windows PowerShell; chain with `;`, not `&&`)
```
pip install -r req-dev.txt
python run.py --dev                 # run part A locally
python -m pytest -q                 # full Python suite (about 20 s, 160+ tests)
cd edge; npm install; npm test      # part B tests (needs Node 20+)
```
Test layout: `tests/conftest.py` (app factory fixture with temp DB, `Api` client that sends the CSRF header, `clock` fixture that patches `server.util.now`, helpers `create_event`, `publish`, `invite_payload`), `test_plans.py`, `test_auth.py`, `test_subscriptions.py` (events, payments, upgrades, Razorpay), `test_invites.py`, `test_imports.py` (CSV/XLSX parsing and authenticated preview), `test_owner.py` (owner-only dashboard and private metadata), `test_features.py` (plan-gated features), `test_pages_and_security.py`, `test_skill_file.py` (this file's drift check). Every feature or requirement needs a test; keep them green.

### Production hosting notes
- Serve the landing page and Flask APIs from the same HTTPS origin; GitHub Pages is static and cannot complete customer sign-in, payment or studio workflows.
- Production startup requires Razorpay key id/secret and developer login disabled. Use Razorpay test credentials for staging; keep mock payments and dev login local/private.
- Use a host with persistent storage for `data/urlovingly.db` and `data/media`, and outbound HTTPS access to Google's verification endpoints and `api.razorpay.com`. Confirm free-tier limits, sleep behavior and outbound rules with the provider; PythonAnywhere is only a candidate until checked.
- Set `URLOVINGLY_PUBLIC_URL` to the Flask site's canonical HTTPS origin, not the Cloudflare Worker. The Worker uses separate D1 and has no SQLite synchronization.
- Add that site's origin (scheme + host, no path) to Google OAuth Authorized JavaScript origins; configure the Razorpay webhook at `/api/payments/razorpay/webhook`.
- A local `python run.py --dev` cycle is free and uses mock payments/developer login, but must not be exposed as production.

### 9.1 Live browser testing and agent sign-in
Use the integrated browser to review UI changes (the `open_browser_page`, `navigate_page`, `read_page`, `screenshot_page` and `run_playwright_code` tools; load them with `tool_search` if they are deferred).

1. **Start the app once.** Run `python run.py --dev` from `Invitation/` as an async/background terminal and use `http://127.0.0.1:5000`. If the port is busy (the command exits with code 1) the server is already running: reuse it. Only `--dev` enables mock payments and developer sign-in.
2. **Reuse the shared page.** Prefer an already shared page id and `navigate_page`; open a new page only when none exists. Use `read_page` (accessibility snapshot) to find elements and `screenshot_page` for visual checks. `run_playwright_code` must go through `page` (no direct `document`/`window`; use `page.evaluate(() => ...)`) and needs `timeoutMs` above 5000 for navigations. `page.request` is not supported in this browser (`Storage.getCookies` error); call `fetch` inside `page.evaluate` instead, and add header `X-Requested-With: urlovingly` to state-changing `/api/` calls.
3. **Sign in with the developer login, not Google.** Agents cannot complete a Google account chooser, and on `127.0.0.1` the Google button is inert anyway (the default client id does not authorize that origin, so the `accounts.google.com/gsi/button` iframe returns 403 and stays 0×0). Steps:
   - Open `/?signin=1` (or click `#signInBtn`) and wait for `#devLoginForm` to lose the `hidden` class (it appears only when `/api/config` reports `dev_login: true`).
   - Fill `#devEmail` with any `@gmail.com` address (other domains get 403, invalid emails 400) and click the form's submit button. Use a fresh address such as `agent.<topic>@gmail.com` for a clean state; every address is a separate customer with its own free trial.
   - Success: the modal closes, or the browser goes to `/studio` when that account already has an active event. The session cookie `urlovingly_session` is HttpOnly, so verify with `fetch('/api/me')` (200 with `user.email`; 401 before sign-in is normal).
   - Sign out with `#signOutBtn` or `POST /api/auth/logout`.
4. **Plans and payment.** After sign-in, pick a plan on the landing page. `free` creates an active event at once (one trial per account, `trial_already_used` otherwise). Paid plans open the checkout modal; with the mock provider the Pay button confirms immediately and redirects to `/studio`.
5. **Not testable by agents:** real Google sign-in, Razorpay checkout and `/owner` (requires the configured owner email authenticated through Google; a developer-login session gets 403). Cover those with pytest. Never type real credentials or Google passwords into the browser.
6. **Diagnosing problems.** Register `page.on('console')`, `page.on('pageerror')`, `page.on('requestfailed')` and a `page.on('response')` filter for status >= 400 before `goto`/reload, then wait a few seconds. Check logos with `[...document.images].map(i => i.complete && i.naturalWidth > 0)`. Expected noise: the Tailwind CDN production warning and `GET /api/me` 401 when signed out. A 403 from `accounts.google.com/gsi/button` means the site origin must be added to the OAuth client's Authorized JavaScript origins in Google Cloud Console; it cannot be fixed in code.
7. Dev data lives in git-ignored `data/urlovingly.db`. Stop the server and ask the user before deleting `data/` to reset state.

## 10. Conventions and gotchas
- Python 3.12, Flask 2.3, plain `sqlite3`. Timestamps are ISO-8601 UTC strings produced by `server.util`; always call `util.now()` through the module so tests can patch it.
- Close SQLite connections explicitly (Windows file locks); `server/db.py` does it on app-context teardown.
- Multi-statement changes use `tx(db)`; quota checks and payment settlement rely on it.
- Do not edit files through terminal commands; use the editor tools. After a `multi_replace_string_in_file` with deep tab indentation, re-read the region (whitespace can be mangled). `private/studio.html` has a few whitespace-only/trailing-space lines, so match exact text when editing.
- Keep comments rare and short (only what the code cannot say). Do not create extra markdown files; update this file and `docs/REQUIREMENTS.md` instead.
- Never commit secrets. The Google client id is public; Razorpay keys come from the environment.
- `data/`, `__pycache__/`, `.pytest_cache/`, `node_modules/`, `.wrangler/` are git-ignored.

## 11. Decisions and assumptions (change deliberately)
Trial hosting is 7 days; Grand includes Standard's features; "6 months" = 180 days; one trial per account; every design and event type is on every plan; Gmail-only login; mock payments only in development; invitation HTML is rendered client-side and stored, then sandboxed when served; edge worker is read-only against D1; owner dashboard is disabled until `URLOVINGLY_OWNER_EMAIL` is configured and requires a Google subject.

## 12. Known limitations / future work
Studio preview omits RSVP/UPI/audio; Google Maps inside sandboxed guest pages logs a harmless console error; no refunds/invoices/GST; no deleting links to free quota; no rate limiting on sign-in/RSVP; SQLite is single-node; studio is not yet wired to D1 (edge service is populated by SQL only); QR code for UPI not implemented. Spreadsheet rows publish sequentially through the existing invite endpoint, so a transient error can leave earlier rows published; the studio reports the stopping row and refreshes link history. Owner dashboard data comes from Part A's SQLite and media directory only; it does not read Cloudflare D1.

## 13. Change log
Append newest last: `YYYY-MM-DD – what changed – tests run`.

- 2026-10-22 – Built part A (landing page, Gmail sign-in, plans, Razorpay/mock payments, plan-gated studio, guest-link hosting, RSVP, WhatsApp, UPI, audio), `docs/REQUIREMENTS.md`, 164 pytest tests passing; manual browser check of free → Grand upgrade and RSVP.
- 2026-10-22 – Added part B `edge/` (D1 migration, base template, modular Worker, node tests, wrangler config) and this skill file with AI-instruction pointers; Node was unavailable so edge tests were not run.
- 2026-10-22 – Added `edge/worker.js` (single-file Worker for the Cloudflare dashboard) and `edge/test/single-file.test.js`; added a test that `worker.js` embeds `base.html`; Node unavailable so JS tests not run.
- 2026-10-22 – Added CSV/XLSX guest-list parsing, authenticated import preview, a downloadable CSV template and plan-capacity-aware studio publishing; documented FR-ST-08 and added `tests/test_imports.py` (focused tests pass).
- 2026-10-22 – Added `/owner` and `/api/owner/overview`, exact Google owner-email gating, private metadata-only dashboard, `URLOVINGLY_OWNER_EMAIL` and owner authorization tests; clarified generic Worker routing and separate D1 population.
- 2026-10-22 – Fixed GitHub Pages project-path logo URLs and made Google account chooser initialization independent of backend startup; documented the static-host auth limitation and added landing regression coverage.
- 2026-10-22 – Documented live-browser testing and developer-login steps for agents (section 9.1), including the Google origin 403 finding on `127.0.0.1`; verified dev login to `/studio` in the integrated browser; documentation only.
- 2026-10-22 – Live site https://urlovingly.github.io/Invitation was found serving the old page (logo 404 at `/URLovingly_Icon.jpg`) until the relative-path fix is pushed; verified the fix under an `/Invitation/` subpath with a static server; added a visible message when Google rejects the page origin; landing tests updated.
- 2026-10-22 – Replaced the hero phone mockup with a Royal-template preview and documented where the Google client id is set; full pytest run.
- 2026-10-22 – Added hosting/deployment requirements for a low-cost complete backend cycle and corrected the documented `URLOVINGLY_PUBLIC_URL` default; full pytest run.
- 2026-10-22 – Added `docs/raspberry-pi-free-hosting.txt` with Raspberry Pi OS, Gunicorn/systemd, Tailscale Funnel, Google OAuth, Razorpay test mode, persistence and backup steps; checked current provider setup docs.
