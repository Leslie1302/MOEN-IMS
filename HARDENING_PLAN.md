# MOEN-IMS — Production Hardening & Readiness Plan

**Status:** Draft for review
**Date:** 2026-06-06
**Target environment:** Azure App Service (Linux, Oryx build) + Azure Blob (backups)
**Scope:** Make the system safe, reliable, and maintainable for multi-user production use at the Ministry of Energy.

---

## 0. How to read this plan

Work is grouped into three priority tiers. **Do them in order.** P0 items are the ones most likely to cause data loss, outages, or a breach, and several are quick. Each item lists the problem, the evidence (real file references in this repo), the fix, and a rough effort estimate.

| Tier | Meaning | Target window |
|------|---------|---------------|
| **P0 — Critical** | Can cause data loss, outage, or breach. Blocks "production-ready" sign-off. | Week 1–2 |
| **P1 — High** | Real reliability/security/maintainability risk; fix before scaling users. | Week 3–5 |
| **P2 — Medium** | Hardening, quality, and operational maturity. | Week 6–8 |

Effort key: **S** = <½ day, **M** = ½–2 days, **L** = 3+ days.

---

## 1. Executive summary

MOEN-IMS is a substantial, security-aware Django 5.1 application (~40,000 lines) with genuine strengths: env-driven secrets, secure cookies, HSTS, 2FA, M365 SSO, transactional writes, and query-optimisation awareness. It is well past prototype quality.

It is **not yet production-grade** for a multi-user ministry system, for three principal reasons:

1. **It runs on SQLite in production.** SQLite serialises all writes, so concurrent officers will hit `database is locked` errors and risk lost writes exactly as usage grows. This is the single highest-impact issue.
2. **Real data sits in version control.** Three SQLite backup copies are committed and live in git history.
3. **The login surface is unthrottled.** There is no brute-force / rate-limiting protection on authentication, despite the app being internet-facing.

The plan below resolves these first, then addresses operational maturity (backups you can restore from, CI that actually blocks bad code, observability) and maintainability debt (oversized modules, error-swallowing, documentation sprawl).

---

## 1b. Implementation status — 2026-06-06

A first hardening pass has been **implemented in the repo** (verified by config tests). Items below are done in code; infrastructure/destructive steps remain for you.

**Done in code (this pass):**

- **Silent SQLite-in-prod fallback removed.** `settings.py` now fails fast in production unless `DATABASE_URL` is set, with Postgres connection pooling (`CONN_MAX_AGE`, health checks) and `ssl_require`. SQLite in prod requires an explicit `ALLOW_SQLITE_IN_PROD=1`. *(Verified: no-DB → raises; Postgres URL → pooled; explicit flag → SQLite.)*
- **Brute-force protection** via `django-axes` (lockout after 5 failures/username+IP, proxy-aware IP).
- **Rate limiting** via `django-ratelimit` on `ms_login` (15/min/IP) and `ms_callback` (30/min/IP).
- **Content-Security-Policy** via `django-csp`, shipped in **report-only** mode (won't break the UI; flip with `CSP_ENFORCE=1` after reviewing reports).
- **Caching/scalability layer** added (Redis via `REDIS_URL`, local-memory fallback) — see §1c.
- **Hardcoded dev encryption key removed** from `settings.py` (now ephemeral per-process in dev).
- **Sentry**: confirmed already wired in `settings.py`; added `sentry-sdk` to requirements so it activates when `SENTRY_DSN` is set.
- **Secrets in git**: 3 tracked SQLite backups and all tracked `.pyc`/`__pycache__` removed from the index; `.gitignore` extended (`*.sqlite3.*`, `*.bak*`, `*.dump`, `*.sql`).
- **CI**: `pip-audit` is now **blocking** (removed `|| true`); new `ci.yml` runs `check --deploy`, missing-migration check, and tests.
- **`.env.example`** added documenting every variable.

**Done in code (second pass — code quality):**

- **All 13 bare `except:` blocks** narrowed to specific exceptions with logging (signature tags, transporter/dashboard views, user model, project import).
- **All 7 stray `print()` calls** replaced with proper logging — notably, the 2FA view no longer prints the **entered TOTP code** to logs (it was leaking a secret).
- **Core money-path tests added** — `Inventory/tests/test_release_accounting.py`, 12 tests covering release-letter drawdown/fulfilment accounting, the over-drawdown rejection guard, and the `Fulfilled`-status regression. All pass; full suite stays green (53 tests).
- **Ruff linting wired into CI** (`ruff.toml`), blocking on real-bug rules. Running it surfaced and I fixed **3 latent crash bugs**: missing `redirect` import in `shep_community_views.py` (7 code paths), `HttpResponse` referenced before import in `order_views.py`, and `audit_text_block` undefined in the report fallback path.

**Still required from you (not safe to do automatically):**

- **Provision Azure PostgreSQL + set `DATABASE_URL`** (P0-1). ⚠️ Before deploying this change, set `ALLOW_SQLITE_IN_PROD=1` in App Service settings to avoid an outage, then migrate to Postgres and remove the flag.
- **Scrub git history** of the previously-committed databases (P0-2) — rewrites history + force-push; needs coordination.
- **Triage these in-source items** found during the pass:
  - ✅ **(FIXED 2026-06-08)** `accounts/views.py` had a **hardcoded superuser-bootstrap email** (`_HARDCODED_TRUSTED_ADMIN_EMAILS`) that auto-promoted to superuser on OAuth login — a privilege backdoor. The literal is removed; trusted admins now come **only** from the `TRUSTED_ADMIN_EMAILS` env var (documented in `.env.example`). ⚠️ **Action required:** set `TRUSTED_ADMIN_EMAILS` in Azure App Service **before deploying this change** to preserve the superuser-recovery path (existing superusers are unaffected — promotion only adds). Note: the email still exists in **git history**; the P0-2 history scrub removes it there.
  - `requirements.txt` deps must be installed before the app boots (the new security apps are mandatory): `pip install -r requirements.txt`.

## 1c. Scalability (was missing from the original plan)

The first draft of this plan had **no scalability layer** — a real gap for a system meant to grow. Added:

- **Shared cache (Redis).** `CACHES` now uses `REDIS_URL` when set, falling back to local memory. A shared cache is a prerequisite for running more than one App Service instance and backs the rate limiter/lockout state.
- **Database connection pooling.** `CONN_MAX_AGE` + health checks reduce per-request connect overhead under load.
- **Remaining scalability work:** cache hot dashboard/report queries (these are the heaviest endpoints); enable App Service autoscale rules once on Postgres; move sessions to the cache backend if session DB load becomes hot; run the load test (P2-6) to size the plan and DB tier. Horizontal scale-out is only safe **after** media moves off local disk (P1-2) and Postgres replaces SQLite (P0-1).

---

## 1d. Implementation status — 2026-06-08 (graph-driven hardening pass)

A third pass, driven by a structural **code knowledge graph** of the repo (parsed with graphify: 268 first-party files, ~2,000 nodes). The graph was used to find the highest-blast-radius, least-tested code, and several fixes target exactly those hotspots. Everything below is implemented in code and verified by the test suite (33 new tests across 4 files, all green).

**Done in code (this pass):**

- **Repo hygiene — vendored virtualenv untracked.** `venv_pdf/` (880 files of reportlab/PIL/pip) was committed despite being in `.gitignore`. Removed from the index (`git rm -r --cached venv_pdf`). This was a supply-chain liability (a frozen venv can drift from `requirements.txt`, and `pip-audit` only checks the latter) and it was also swamping all static analysis — first-party code is only ~46k lines / 564 files.
- **Object-level authorization on item edit/delete (IDOR fix).** `EditItem`/`DeleteItem` (`item_views.py`) gated only on `is_staff`, using the default `InventoryItem.objects.all()` queryset — so any staff user could edit or delete **another group's** stock by changing the URL `pk`. Added `get_queryset()` scoping to the user's own group(s) (superusers/Management exempt), mirroring the existing convention in `views/order_views.py`. Out-of-scope items now 404 (not 403, to avoid leaking existence). *Tests: `tests/test_item_authz.py` (7).*
- **Per-user rate limiting on the heavy endpoints (resource-exhaustion / Denial-of-Wallet defence).** Throttled the three CPU/IO-heavy authenticated endpoints the graph flagged as large + untested: `download_waybill_pdf` (10/min, the 1,085-line PDF generator), `upload_requests` (6/min POST, bulk Excel→DB), and the legacy `RequestMaterialView` POST (6/min, owns `handle_bulk_request`). Keyed on `user` (not IP) so shared ministry NAT doesn't lock everyone out; enforced across instances via the shared Redis cache. *Tests: `tests/test_rate_limits.py` (3).*
- **Fixed an inert OAuth rate limit (latent bug in the 2026-06-06 pass).** `ms_login`/`ms_callback` used `@ratelimit(method='ALL')` — but `'ALL'` as a *string* is interpreted by django-ratelimit as a literal HTTP method named "ALL", so it never matched a real GET request and the throttle was **silently disabled**. Switched to the imported `ALL` sentinel. Those endpoints are now genuinely throttled for the first time.
- **Characterization tests around the four largest untested view functions** before any future decomposition: `download_waybill_pdf` (1085 lines), `management_dashboard` (545), `upload_requests` (284), `handle_bulk_request` (258). Pins auth boundary, permission gating, method handling, and input rejection. *Tests: `tests/test_hub_characterization.py` (14).*
- **Tests for `UserRoleMiddleware`** — the central default-deny auth gate that *every* view depends on (the app has no per-view `@login_required` in whole modules; auth is enforced here). Covers anonymous redirect, allowlist, no-group→awaiting, grouped/superuser pass-through, and 2FA enforcement. *Tests: `tests/test_middleware_auth.py` (9).*

**Findings surfaced for triage:**

- ✅ **Dead code (FIXED).** Removed the unreachable `elif path == awaiting: redirect('dashboard')` branch in `UserRoleMiddleware.process_view` (the allowlist short-circuits it) and the now-unused `reverse` import. Simplified the no-group redirect.
- ✅ **Naive datetimes with `USE_TZ=True` (FIXED).** `views/dashboard_views.py` now uses `timezone.localdate()`/`timezone.now()` and `timezone.make_aware(...)`, and filters `date_delivered__date=today` instead of comparing a DateTimeField to a bare date. Clears the `RuntimeWarning`s and removes a latent off-by-one-day boundary risk.
- ✅ **String `method='ALL'` footgun (FIXED).** Added a blocking CI step (`ci.yml`) that greps for `method='ALL'` in `@ratelimit` decorators and fails the build, so the inert-throttle bug can't recur.
- ✅ **Signal file I/O under tests (FIXED).** The digital-stamp `post_save` PNG generation is now skipped when `TESTING` is set (the cheap DB text stamp is kept). Stops the suite writing files to `media/digital signatures/`.

**Remaining backlog (prioritised):**

1. **App-level caching + N+1 cleanup** (the open scalability item from §1c). Cache `management_dashboard` / KPI / project-dashboard outputs in Redis; add `select_related`/`prefetch_related` to the loop-heavy paths in `order_views.py`.
2. **Flip CSP to enforce** (`CSP_ENFORCE=1`) after reviewing report-only output (P2-5).
3. **Decompose the god-functions** now that they have characterization nets — `download_waybill_pdf`, `management_dashboard` (P2-1).
4. **Minor cleanups (all done):** ✅ dead middleware branch removed; ✅ naive datetimes fixed; ✅ `method='ALL'` CI guard added; ✅ per-endpoint rate limits env-tunable (`RATELIMIT_WAYBILL_PDF` / `_BULK_UPLOAD` / `_BULK_REQUEST`, documented in `.env.example`); ✅ digital-stamp PNG generation skipped under `TESTING`.

---

## 2. P0 — Critical (do first)

### P0-1 — Migrate the production database from SQLite to PostgreSQL
**Problem.** Production can run on SQLite. SQLite uses a single writer lock for the whole database; under concurrent writes (multiple officers creating orders/release letters at once) requests will fail with `database is locked` and, worse, can lose writes. It also has no real concurrent backup story.

**Evidence.**
- `IMS/Inventory_management_system/Inventory_management_system/settings.py` — `DATABASES` defaults to `django.db.backends.sqlite3` (line ~273), and an `ALLOW_SQLITE_IN_PROD` escape hatch (lines ~282–298) **auto-enables SQLite in production on Azure App Service**.
- `psycopg2-binary` and `dj-database-url` are already in `requirements.txt`, so the path is half-built.

**Fix.**
1. Provision **Azure Database for PostgreSQL – Flexible Server** (same region as the App Service; start Burstable B1ms/B2s, enable automated backups + point-in-time restore).
2. Set `DATABASE_URL` in App Service application settings; confirm `dj_database_url.config()` is consumed (it already is when `DATABASE_URL` is present).
3. **Remove the SQLite-in-prod escape hatch** so production can never silently fall back: delete/neutralise the `ALLOW_SQLITE_IN_PROD` / `ON_AZURE_APP_SERVICE` auto-allow branch and make a missing `DATABASE_URL` in prod a hard failure.
4. Export current SQLite data and load into Postgres. Recommended path: `python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission > data.json`, run migrations on the empty Postgres DB, then `loaddata data.json`. Validate row counts per table against the SQLite source.
5. Run the full test suite and a manual smoke test of the order → release → fulfilment path against Postgres before cutover.

**Effort:** L. **This is the gating item for production sign-off.**

---

### P0-2 — Purge committed database backups from the repo and git history
**Problem.** Live data (and its historical states) is in version control. Anyone with repo access — now or via a leaked clone — has the ministry's data. `.gitignore` was fixed to ignore `*.sqlite3`, but the backup copies don't match that pattern and remain tracked.

**Evidence.** `git ls-files` shows tracked:
- `IMS/Inventory_management_system/db.sqlite3.bak-20260604-214259`
- `IMS/Inventory_management_system/db.sqlite3.prephase1-071916`
- `IMS/Inventory_management_system/db.sqlite3.preseed-215742`

**Fix.**
1. `git rm --cached` the three backup files and commit.
2. Extend `.gitignore` to cover `*.sqlite3.*`, `*.bak`, `*.bak-*`, `db.sqlite3.*`.
3. **Scrub git history** (these files are still in every past commit). Use `git filter-repo --path-glob 'IMS/Inventory_management_system/db.sqlite3*' --invert-paths`, then force-push and have all collaborators re-clone. Treat any data in those snapshots as potentially exposed.
4. Document the backup procedure so backups go to Azure Blob (see P1-2), never the repo.

**Effort:** M (S for the removal, M including history scrub + coordination).

---

### P0-3 — Add authentication brute-force protection / rate limiting
**Problem.** There is no throttling on login or other sensitive endpoints. An attacker can attempt unlimited password guesses. 2FA helps, but credential-stuffing, account lockout abuse, and DoS on auth remain open.

**Evidence.** No `django-axes`, `django-ratelimit`, or throttling middleware appears in `settings.py` `MIDDLEWARE` or `INSTALLED_APPS`; grep for `ratelimit|throttle|axes` returns nothing in app code.

**Fix.**
1. Add **`django-axes`** for login lockout (e.g. lock after N failed attempts per username+IP, cool-down window, admin reset). Wire its backend into `AUTHENTICATION_BACKENDS` and middleware.
2. Add **`django-ratelimit`** (or App Service / front-door rate rules) on high-value POST endpoints: login, password reset, 2FA verify, bulk upload.
3. Ensure rate-limit and lockout events are logged (ties into P1-3 observability).

**Effort:** M.

---

### P0-4 — Make CI actually block bad code
**Problem.** CI exists but cannot fail. The dependency scan runs `pip-audit -l || true` (the `|| true` swallows every finding), `safety` only runs "if command exists" (it isn't installed, so it's skipped), and **no workflow runs the test suite, `manage.py check --deploy`, or migrations**. Deploy ships whatever is on `main`.

**Evidence.**
- `.github/workflows/dependency-scan.yml` — `pip-audit -l || true`; `safety` guarded by `command -v`.
- `.github/workflows/main_moen-ims.yml` — build → upload artifact → deploy; no test/lint/check step.
- Python version drift: dependency-scan uses `3.11`, deploy uses `3.14`, repo `.python-version`/`runtime.txt` differ. Pick one.

**Fix.**
1. Add a **test + checks job** that must pass before deploy: `pip install -r requirements.txt`, `python manage.py check --deploy --fail-level WARNING`, `python manage.py makemigrations --check --dry-run`, and `python manage.py test`.
2. Make `pip-audit` blocking on high-severity findings (drop `|| true`; allowlist with justification where needed).
3. Pin one Python version everywhere (recommend matching the Azure runtime; confirm 3.14 is actually supported on the App Service plan, otherwise use 3.12).
4. Gate the deploy workflow on the test job (`needs:`), and ideally require it as a branch-protection check on `main`.

**Effort:** M.

---

## 3. P1 — High (before scaling users)

### P1-1 — Verifiable backup AND restore drill
**Problem.** A backup you have never restored is not a backup. Backups must move to Postgres + Blob and be restore-tested.

**Fix.** Use Azure PostgreSQL automated backups + PITR (from P0-1). Keep the existing Blob backup command for any file/media assets. Then perform a **documented restore drill** into a scratch database and record RPO/RTO actuals. Schedule the drill quarterly. Update `DISASTER_RECOVERY.md` with the real procedure.
**Effort:** M.

### P1-2 — Media file storage off the local disk
**Problem.** Uploaded PDFs, signed scans, release letters, profile pics, weekly reports are written to local `media/`. On Azure App Service the local filesystem is ephemeral/per-instance — files can vanish on restart/scale and won't be shared across instances.

**Evidence.** `MEDIA_ROOT` on local disk; `media/` subfolders (`release_letters/`, `site_receipts/`, `digital signatures/`, etc.) present in repo working tree.

**Fix.** Move media to **Azure Blob Storage** via `django-storages`. Migrate existing files. Keep `whitenoise` for static only.
**Effort:** M.

> ✅ **(DONE in code, 2026-06-08)** `django-storages[azure]` added; `settings.py` migrated to the Django 5.1 `STORAGES` API — `default` routes user uploads to **Azure Blob** when `AZURE_ACCOUNT_NAME/KEY/CONTAINER` are set (private container → expiring SAS URLs), local disk otherwise; `staticfiles` stays on WhiteNoise. All 11 `FileField`/`ImageField` uploads move automatically. **No data migration needed (pre-pilot, empty system).** Must be deployed/tested with `collectstatic` (re-activates WhiteNoise manifest storage). **Remaining follow-up:** the digital-signature PNGs and PDF logos in `transporter_views.py` use raw `MEDIA_ROOT` filesystem paths and still hit local disk — refactor to the storage API (the stamps regenerate from DB data, logos can be bundled as static assets).

### P1-3 — Observability: error tracking + structured logging
**Problem.** Failures are largely invisible in production. There are 7 stray `print()` calls and logging is minimal.

**Fix.** Add **Sentry** (or Azure Application Insights) for exception capture with release tagging. Route Django logging to stdout (App Service log stream) with request IDs. Replace `print()` with the logger. Add an uptime/health check ping on a lightweight endpoint.
**Effort:** M.

### P1-4 — Replace bare `except:` blocks
**Problem.** 13 bare `except:` blocks swallow all exceptions (including `KeyboardInterrupt`/`SystemExit`) and hide real bugs.

**Evidence.** `grep -rn 'except:' Inventory --include='*.py'` → 13 hits (excluding migrations).

**Fix.** Narrow each to the specific exception(s), log the error, and re-raise where the operation should not silently continue. Prioritise any in the order/release/fulfilment money-path.
**Effort:** M.

### P1-5 — Test coverage on the core money-path
**Problem.** ~1,700 lines of tests against a ~40,000-line app, weighted toward geospatial/security rather than the core order → release letter → drawdown → fulfilment logic — exactly where a `KNOWN_ISSUES.md` history shows past `Critical`/`High` bugs (invalid status values, name-based lookups, `MultipleObjectsReturned`).

**Fix.** Add tests covering: release-letter quantity accounting (requested vs authorised vs delivered), status transitions, multi-warehouse material lookup, and bulk Excel upload. Add a coverage gate in CI (start at current %, ratchet up). Aim for meaningful coverage of `models/orders.py`, `views/order_views.py`, release/transport flows.
**Effort:** L.

### P1-6 — Secrets and key management review
**Problem.** Confirm no secrets land in code or logs and that key rotation is possible. `SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`, M365 client secret, mail creds, Blob keys must all come from App Service settings / Key Vault.

**Fix.** Audit `settings.py` and `example_email_settings.py` for hardcoded values; move all secrets to **Azure Key Vault** (referenced from App Service settings). Document a rotation procedure. Confirm `DEBUG=False` is enforced in prod (it defaults safe — keep it that way) and that the insecure dev `SECRET_KEY` fallback can never be reached in prod (it already raises without `DEBUG`; add a test).
**Effort:** M.

---

## 4. P2 — Medium (quality & operational maturity)

### P2-1 — Break up oversized modules
Several files are large enough to be change-risky and hard to review: `Inventory/transporter_views.py` (2,512 lines), `Inventory/shep_community_views.py` (1,575), `Inventory/admin.py` (1,305), `Inventory/views/order_views.py` (1,286), `Inventory/signals.py` (1,151), `Inventory/models/orders.py` (1,151). Split by responsibility, extract service functions, and add focused tests as you go. **Effort:** L (incremental).

### P2-2 — Add linting/formatting to CI
Adopt `ruff` (lint + format) and run it in the CI checks job. Fix the backlog in passes. Removes whole classes of small bugs and standardises style across contributors. **Effort:** M.

### P2-3 — Consolidate documentation
There are 91 markdown files plus ~12 one-off scripts (`fix_rl_quantities.py`, `inspect_rl_12.py`, etc.) scattered at repo roots, with multiple overlapping/contradictory "IMPLEMENTATION_PLAN"/"SUMMARY" docs. Establish a single `docs/` source of truth: one current `ARCHITECTURE.md`, one `OPERATIONS.md`/runbook, one `CHANGELOG.md`. Archive the rest under `docs/archive/`. Move ad-hoc scripts into `Inventory/management/commands/` or delete. **Effort:** M.

### P2-4 — Dependency hygiene
Pin and regularly update dependencies; resolve `pip-audit` findings from P0-4. Note `djangorestframework==3.14.0` is older — verify compatibility with Django 5.1 and update if needed. Set up Dependabot. **Effort:** M.

### P2-5 — Content Security Policy & security headers review
HSTS, secure cookies, and X-Frame-Options are in place. Add a **Content-Security-Policy** (via `django-csp`) and review `Referrer-Policy` / `Permissions-Policy`. Run the deployed site through Mozilla Observatory and close gaps. **Effort:** M.

### P2-6 — Load & concurrency test
After the Postgres migration, run a realistic concurrency test (e.g. Locust) simulating peak simultaneous officers creating releases, to validate the database/app handles real load and to size the App Service plan and Postgres tier. **Effort:** M.

---

## 5. Suggested execution sequence

```
Week 1   P0-2 (purge data from git)        ← fast, stops the bleeding
         P0-3 (brute-force protection)
         P0-4 (CI gates)
Week 2   P0-1 (Postgres migration + cutover)  ← the big one
Week 3   P1-1 backups/restore drill, P1-2 media to Blob
Week 4   P1-3 observability, P1-6 secrets/Key Vault
Week 5   P1-4 bare excepts, P1-5 core-path tests
Week 6-8 P2 items (module splits, linting, docs, CSP, load test)
```

Rationale: P0-2/3/4 are fast and reduce immediate exposure; they also make the riskier Postgres cutover (P0-1) safer because CI and backups are in place first.

---

## 6. Definition of "production-ready" (sign-off checklist)

- [ ] Production runs on Azure PostgreSQL; SQLite cannot be selected in prod.
- [ ] No database files or secrets in the repo or git history.
- [ ] Login and sensitive endpoints are rate-limited; account lockout active.
- [ ] CI runs `check --deploy`, migration check, full test suite, and a blocking dependency audit; deploy is gated on it.
- [ ] Automated DB backups with a **completed, documented restore drill** (known RPO/RTO).
- [ ] Uploaded media served from Blob, not local disk.
- [ ] Error tracking live; no `print()` in production code; no bare `except:` on the core path.
- [ ] Core order → release → fulfilment logic covered by tests; coverage gate in CI.
- [ ] All secrets in Key Vault with a documented rotation procedure.
- [ ] Single, current source-of-truth documentation set.

---

## 7. Risks & notes

- **P0-1 cutover is the highest-risk change.** Do it in a maintenance window, take a verified export first, validate row counts and the core workflow on Postgres in staging before pointing production at it, and keep the SQLite export until you've run on Postgres cleanly for a defined period.
- **History scrub (P0-2) is disruptive** — it rewrites commit hashes and requires every collaborator to re-clone. Schedule and communicate it.
- This plan deliberately **does not change business logic**; P1-5 adds tests around it first precisely so later refactors (P2-1) are safe.
