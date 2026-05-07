# MOEN-IMS Security & Production-Readiness Audit

**Date:** 2026-05-07
**Auditor:** Senior software engineer / application security specialist (model-assisted)
**Audit Scope:** Full Audit (all 11 dimensions)
**Methodology:** Direct file review of files referenced during prior incident-response session, plus targeted code-graph search across the repo. Coverage is broad but not exhaustive — see "Coverage Caveats" at the end of this document.

---

## Context (assumed from prior session)

| Field | Value |
|---|---|
| Application Name | MOEN-IMS (Ministry of Energy Inventory Management System) |
| Primary Tech Stack | Django 5.1.5, Python 3.14, Gunicorn 25.0.3, WhiteNoise 6.11 |
| Hosting / Deployment | Azure App Service Linux (UK South), gunicorn behind App Service front-end |
| Database | SQLite (currently — emergency persistent path now `/home/site/data/db.sqlite3`) |
| Auth Mechanism | Microsoft 365 OAuth via MSAL + Django session auth + django-otp 2FA |
| User Roles | Store Officers, Stores Management, Schedule Officers, Management, Consultants, Transport Officer, Superuser |
| Public-facing? | Yes — `moen-ims.org` and `*.azurewebsites.net` |
| Approx. user count | ~50 internal Ghana government staff (inferred) |
| Data sensitivity | Government procurement / inventory / supplier data, BOQs, signatures |
| Third-party services | Microsoft Graph (mail), Azure App Service, Sentry (configured, DSN empty) |
| Known incidents | DEBUG=True in production leaked configuration on debug page; SQLite database wiped on every deploy due to BASE_DIR resolving under `/tmp/<deploy-hash>/`; admin role data lost; localhost OAuth blocked by missing redirect URI registration |

---

## 1. Executive Summary

MOEN-IMS is a competently-structured Django app that has been catastrophically let down by its deployment story. The application code itself shows real care — OAuth-only authentication, 2FA wired in, Django auto-escaping respected, no `mark_safe`/raw SQL/`eval` surfaces, CSRF tokens in 59 templates, dedicated `test_security.py` file, audit_log app installed. But the production posture is a textbook "vibe-coded shipping" failure: `DEBUG=True` leaking the entire settings page on every error, ephemeral SQLite at `/tmp/<hash>/` losing all data on every push, no real DB provisioned, no rate limiting, no startup migration command, audit-log infrastructure that never actually writes a record. The recent audit fixes correctly externalised secrets to env vars, but the deployment environment never received them, which is how a single mistake compounded into a production-wide outage and probable irrecoverable data loss.

**Vibe Code Risk Rating:** *Earnest builder, brittle runway — application logic is more careful than typical vibe-coded work, but deployment hygiene is a Phase-1 emergency. After Phase 1 fixes (most of which are already drafted in code in this branch) the app reaches a "safe for ~50 internal users" tier; reaching "general production readiness" requires Phase 2.*

---

## 2. Critical & High Findings

| # | Finding | Location | Risk | CWE / OWASP | Effort | Recommended Fix |
|---|---|---|---|---|---|---|
| 1 | `DEBUG=True` in production exposes full settings, env vars, file paths, masked secrets, app structure on every 500 error | `settings.py:54`; observed live on production debug page | **Critical** | CWE-209 / A05:2021 | Low | Set `DJANGO_DEBUG=False` in App Service Application Settings; rotate any secret that appeared on the debug page (M365 client secret, Django SECRET_KEY) |
| 2 | SQLite on App Service `/tmp/<deploy-hash>/` lost all data on every deploy, including admin/role memberships | `settings.py:235` (pre-fix); now patched in this branch via `/home/site/data/db.sqlite3` | **Critical** | CWE-664 | Low (patched, awaiting push); **Medium** to migrate to Postgres | Push the in-progress fix; provision Azure Database for PostgreSQL Flexible Server; set `DATABASE_URL`; run dumpdata/loaddata |
| 3 | M365 client secret and Django `SECRET_KEY` were exposed (debug page, then this chat transcript) | Transcripts and prior debug page renders | **Critical** | CWE-200, CWE-798 | Low | Rotate `MS_CLIENT_SECRET` in Azure AD app; rotate `DJANGO_SECRET_KEY`; redeploy; force-logout existing sessions |
| 4 | No rate limiting anywhere — auth endpoints, file uploads, bulk operations all unthrottled | Whole app — no `django-ratelimit`, no DRF throttle, no Nginx-level limits | **High** | CWE-770 / A04:2021 | Medium | Add `django-ratelimit` decorator to `/auth/login/`, file upload views, bulk-import endpoints; limit credentials-failure attempts; consider Azure WAF in front |
| 5 | File upload paths trust pandas/openpyxl with no MIME or magic-byte validation, no per-user size cap beyond global `FILE_UPLOAD_MAX_MEMORY_SIZE` | `transporter_views.py:773-776`, `views/data_views.py:45-47, 109-111, 524-526`, `shep_community_views.py:500` | **High** | CWE-434 / A05:2021 | Medium | Validate via `python-magic` after upload; reject non-xlsx/xls; bound per-file size; never write to media dir without sanitised filename |
| 6 | `audit_log` app installed and rendered on dashboards, but never written to anywhere — no actual audit trail of role changes, deletes, exports, releases | Searched the whole repo — zero `AuditLog.objects.create(...)` calls in views | **High** | CWE-778 / A09:2021 | Medium | Add `audit_log` writes on: superuser promotion, group changes, MaterialOrder/ReleaseLetter approvals, user deactivations, bulk imports, BOQ over-issuance approvals |
| 7 | `pandas==3.0.0` in `requirements.txt` is not a real pandas release | `requirements.txt:11` | **High** (deploy will fail or pull a yanked/unexpected version) | CWE-1104 | Low | Pin a real version, e.g. `pandas==2.2.3` |
| 8 | Hardcoded admin email in source (`leslie.adjetey@energymin.gov.gh`) auto-promoted to superuser on OAuth login | `accounts/views.py:31` (added during incident response) | **High** (intentional, but transitional) | CWE-798 | Low (after portal access) | Switch to `TRUSTED_ADMIN_EMAILS` env var; remove hardcoded list once env var is set |
| 9 | `TOKEN_ENCRYPTION_KEY` dev-fallback hardcoded in `settings.py` | `settings.py:107` | **High** if reused in prod | CWE-321 | Low | Already gated to `DEBUG-only`; remove fallback when DEBUG drops, require env var unconditionally; rotate key once set |
| 10 | No CI/CD security checks: no pip-audit / safety / bandit / Dependabot / pre-commit hooks visible | Repo root | **High** for a system with PII and government data | CWE-1395 | Medium | Add a GitHub Actions workflow running `pip-audit`, `bandit`, and tests on every PR; enable Dependabot |
| 11 | No structured logging or active monitoring — Sentry SDK configured but `SENTRY_DSN` empty in prod settings dump | `settings.py:25-39` | **High** (observability blind spot) | CWE-778 | Low | Provision a Sentry project, set `SENTRY_DSN` in App Service config |
| 12 | God-files in `Inventory/views/` — `order_views.py` 44k LOC, `dashboard_views.py` 36k LOC, `data_views.py` 34k LOC | Inventory/views/ | High (maintainability, security review tractability) | n/a | High | Refactor by feature into smaller modules; introduce service-layer functions for cross-view logic |
| 13 | View functions accept Excel files and `pd.read_excel()` directly with no schema validation prior to DB writes | `views/data_views.py`, `transporter_views.py:773` | **High** | CWE-20 | Medium | Add `pandera` or pydantic-based schema validation; reject malformed rows with explicit errors; never trust DataFrame columns by position |

---

## 3. ⚡ Quick Wins (≤1 day effort, highest security yield)

1. **Set `DJANGO_DEBUG=False` + `ALLOW_SQLITE_IN_PROD=1` in App Service Application Settings.** The moment portal access returns. Stops the production debug-page secret leak immediately. The `ALLOW_SQLITE_IN_PROD` flag (added in this branch) prevents the app from refusing to boot before Postgres is provisioned.
2. **Rotate `MS_CLIENT_SECRET` and `DJANGO_SECRET_KEY`.** Both leaked on the debug page and the client secret again in our chat transcript. Update Azure AD app registration → Certificates & secrets, update App Service config, and your local `.env`. Rotation also force-invalidates any sessions an attacker might have.
3. **Fix `pandas==3.0.0` typo to `pandas==2.2.3`.** Single-line PR; without it, Azure's clean-build deploys will fail or pull a non-existent/yanked version with unpredictable behaviour.
4. **Add `pip-audit` to GitHub Actions.** A 15-line workflow that runs on every PR. Surfaces CVEs in your locked dependency set. Free, easy, immediate dependency-supply-chain visibility.
5. **Wire the existing `audit_log` to actually write entries** for the highest-risk actions — superuser auto-promotion, group membership changes, approval/release workflows, bulk imports. The infrastructure is there; you're just missing the calls. Single-day effort. Without this, you have no forensic trail when something goes wrong.

---

## 4. Dimension-by-Dimension Breakdown

### 4.1 Authentication & Authorisation

**Findings.** Authentication is exclusively Microsoft 365 OAuth via MSAL — there is no local-password attack surface, which is a strong default. `accounts/views.py:ms_callback` exchanges authorization codes server-side (confidential client flow), validates `state` against a server-side session value to prevent CSRF on the OAuth callback, and enforces `redirect_uri` matching at Microsoft's end. 2FA via `django-otp` is enforced through `UserRoleMiddleware` (`Inventory/middleware.py:115-120`) for users who have a confirmed TOTP device. Authorisation is a hybrid of group-name string checks (in views and templates) and `is_superuser` shortcut in the middleware.

**Concerns.**
- The middleware lets *any* authenticated user with at least one group through (`middleware.py:128`), without checking that the group is actually one of the intended ones. A user assigned to a misnamed group (`Storekeepers` rather than `Store Officers`) gets through but sees no menus — a confusing failure mode rather than a security one, but worth fixing.
- Group-name checks are scattered across views and templates with both singular and plural variants (`Store Officer` vs `Store Officers`, `Consultant` vs `Consultants`), which is a documented inconsistency and a future source of authorisation drift.
- No IDOR protection on most resource detail views: a user with the right group can typically open any object by primary key. Object-level permission checks (e.g., "can this user see *this* MaterialOrder?") are not visible in the audit sample. This is acceptable for a 50-user trusted internal system but would be flagged hard in a public-facing app.
- `accounts/views.py` auto-promotes hardcoded emails to `is_superuser=True` on login. Intentional bootstrap, but a dangerous code path to leave around — anyone who can submit a PR can promote themselves.
- 2FA enforcement only triggers if the user already has a TOTP device. Users without 2FA setup never see the verify page; there's no policy that all-staff-must-enable-2FA-within-N-days. Reasonable for low-stakes, weak for government data.

**Risk Level:** Medium — strong primitives, weak fine-grained authorisation.
**Effort to Fix:** Medium.
**Benchmark.** A Keycloak/Auth0 setup would normally externalise role and permission management entirely, with row-level access policies enforced at the gateway. Django-Guardian provides per-object permissions in-process. Compared to either, this app sits at "RBAC by string-matching group names" — fine for ~50 users, brittle as it scales.
**Remediation.** (a) Centralise group constants in `Inventory/constants.py` and import everywhere; (b) replace string comparisons with a `has_group(user, *groups)` helper; (c) add object-level permission checks on detail views via `django-guardian` or hand-written `get_object()` overrides; (d) make 2FA mandatory for all non-Consultant groups via a policy in middleware; (e) move the trusted-admin bootstrap to env-var-only and remove the hardcoded list.

### 4.2 Input Validation & Injection

**Findings.** Excellent in code but weak at the upload layer.
- **SQL injection:** No raw `cursor.execute()` with user input found. The four `cursor.execute` occurrences are all hardcoded queries in management commands or migrations (`check_db.py`, `0030_fix_waybill_download_count_column.py`).
- **XSS:** Django auto-escaping is on; no `mark_safe()`, `|safe` filter, or `format_html()` usages found in app code (the only `safe` hit was a comment in `models/users.py:105`).
- **CSRF:** Built-in middleware enabled; 59 templates contain `{% csrf_token %}`. No `@csrf_exempt` decorators anywhere in app code.
- **File upload:** Multiple endpoints accept Excel files into `pandas.read_excel()` with no MIME or magic-byte check. Form classes do basic validation but no content sniffing. `request.FILES['file']` flows directly to pandas in `transporter_views.py:773-776`; corrupt or maliciously-crafted Excel files trigger pandas/openpyxl parsing — pandas has had CVEs (e.g., CVE-2024-9036) and openpyxl is a complex parser.

**Risk Level:** Medium-to-High (driven by upload validation gap).
**Effort to Fix:** Medium.
**Benchmark.** OWASP File Upload Cheat Sheet recommends magic-byte validation, separate storage with no execution, virus scanning (ClamAV or Microsoft Defender for Storage), and processing in a sandboxed worker. This app does none of these.
**Remediation.** Add `python-magic` content-type check after upload; reject unless `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`; cap individual file size lower than `FILE_UPLOAD_MAX_MEMORY_SIZE`; if budget allows, route uploads to Azure Blob Storage and process via a Function with Defender scanning.

### 4.3 API Security

**Findings.** This is a server-rendered Django app, not a REST/JSON API. There is no DRF, no token-based API surface. The HTTP method enforcement is partial — `@require_POST` appears ~15 times, mostly on notification, report, and stores-management mutations, but is not pervasive. Error pages in production currently leak stack traces because of `DEBUG=True`.

**Risk Level:** High while DEBUG=True; Medium once it's off.
**Effort to Fix:** Low.
**Benchmark.** A standard server-rendered Django app following Two Scoops of Django sets `DEBUG=False`, configures a custom 500/403/404 template, and uses Sentry for stack traces. This app has the foundation (Sentry SDK imports gated on `SENTRY_DSN`) but the DSN isn't set.
**Remediation.** Same as #1 in the findings table; ensure all state-changing views have an HTTP-method decorator; provision Sentry and set DSN.

### 4.4 Frontend & Client-Side Security

**Findings.** Limited inspection — I didn't audit the static JS/CSS bundle. From settings:
- `X_FRAME_OPTIONS = 'DENY'` ✓
- `SECURE_CONTENT_TYPE_NOSNIFF = True` ✓
- `SECURE_REFERRER_POLICY = 'same-origin'` ✓
- `SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'` ✓
- `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE='Lax'` — *but only when `DEBUG=False`*. Currently in prod they're all False because DEBUG is True.
- No Content-Security-Policy header configured anywhere. `django-csp` is not in requirements.
- HSTS is configured in the `if not DEBUG` block (`SECURE_HSTS_SECONDS=31536000`, preload + subdomains) — also disabled in prod right now.

**Risk Level:** High while DEBUG=True; Medium-to-Low after fix (still missing CSP).
**Effort to Fix:** Low for cookies/HSTS (just turn off DEBUG); Medium to add a sensible CSP without breaking existing inline JS.
**Benchmark.** Mozilla Observatory grade for a hardened Django site is A+. With DEBUG=True the current site would score F. Once flipped, with HSTS and the existing security headers it would score B. Adding CSP and `Permissions-Policy` would push to A.
**Remediation.** Beyond turning DEBUG off: install `django-csp`, start in report-only mode, iterate to enforcing.

### 4.5 Secrets & Configuration Management

**Findings.** The audit fix correctly externalised all production secrets to environment variables (`MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_TENANT_ID`, `DJANGO_SECRET_KEY`, `TOKEN_ENCRYPTION_KEY`). `.env.example` exists; `.env` is gitignored. `python-dotenv` loads local-dev values.

**Concerns.** `TOKEN_ENCRYPTION_KEY` has a hardcoded dev fallback in `settings.py:107` — fine while `DEBUG=True`, but if `DEBUG` is somehow True in prod (which it currently is), the dev key gets used to encrypt M365 refresh tokens, and anyone with the source code can decrypt them. The hardcoded admin email in `accounts/views.py` is another configuration-in-code violation; should be env-var-only once portal access is back.

**Risk Level:** High while DEBUG=True; Low after.
**Effort to Fix:** Low.
**Benchmark.** Azure Key Vault is the appropriate next step — App Service can pull secrets from Key Vault via reference syntax (`@Microsoft.KeyVault(...)`) and rotate without redeploys. A small system can stay on App Service Application Settings, which is what this app currently uses (correctly, modulo DEBUG).
**Remediation.** Adopt Key Vault references for `MS_CLIENT_SECRET`, `DJANGO_SECRET_KEY`, `TOKEN_ENCRYPTION_KEY` once portal access is back; remove dev fallbacks for `TOKEN_ENCRYPTION_KEY`.

### 4.6 Third-Party Services & Supply Chain

**Findings.** Microsoft Graph integration is server-side-only (`accounts/notifications.py:52` posts to a hardcoded Graph endpoint). No API keys exposed to the frontend. Webhook signature validation is N/A — no inbound webhooks observed. The dependency set is reasonable but unaudited.

**Concerns.**
- `pandas==3.0.0` does not exist; this is either a typo or some kind of stub. Will break clean builds.
- No `pip-audit` / `safety` / Dependabot in CI.
- Python 3.14 is bleeding-edge (was on the production traceback) — fine, but means many wheels will be source-built and some packages may not have official 3.14 support.
- `cryptography>=44.0.0` — unpinned upper bound. Azure may pull anything 44+.
- `requests>=2.32.3` — same issue.

**Risk Level:** High.
**Effort to Fix:** Low.
**Benchmark.** Snyk / Dependabot / pip-audit integration is now table stakes for any internet-facing app handling PII. Even a `pip-audit` Action workflow takes 15 minutes to add.
**Remediation.** (a) Fix the pandas pin; (b) tighten `cryptography` and `requests` to compatible-release ranges (`~=44.0`); (c) add Dependabot for the `pip` ecosystem; (d) add a GitHub Action running `pip-audit -r requirements.txt` on every PR; (e) consider downgrading to Python 3.12 LTS for stability.

### 4.7 Data Protection

**Findings.**
- **In transit:** Azure App Service terminates TLS at the front door; `SECURE_SSL_REDIRECT=True` is configured behind `not DEBUG`. HSTS max-age=1 year with preload (also gated on `not DEBUG`). Currently both disabled in prod because DEBUG=True.
- **At rest:** Azure-managed disks are encrypted by default. SQLite file inherits that. No application-level field encryption for PII in models (e.g. supplier banking details, signatures), apart from M365 OAuth tokens which are encrypted with `TOKEN_ENCRYPTION_KEY`.
- **Passwords:** N/A (OAuth-only) — eliminates a whole class of risk.
- **Database access:** Currently SQLite — no separate DB process, no network exposure. After Postgres migration, ensure `sslmode=require` in `DATABASE_URL`.
- **PII handling:** No data minimisation or retention policies visible in code.

**Risk Level:** Medium.
**Effort to Fix:** Medium.
**Benchmark.** A government-data Django app would normally use Azure Database for PostgreSQL with `sslmode=require`, application-level encryption for sensitive fields via `django-cryptography` or `django-fernet-fields`, and a documented retention policy with automated purges. This app is not there yet.
**Remediation.** Migrate to Postgres with TLS-required connections; identify PII fields (emails, phone numbers, signatures, supplier banking) and encrypt at field level; document retention policy.

### 4.8 Error Handling, Logging & Observability

**Findings.**
- Default Django logging configured (`settings.py:LOGGING`) with console handler at DEBUG level. Adequate for development, noisy and not retained centrally on App Service Linux beyond the rolling log stream.
- Sentry SDK imported and gated on `SENTRY_DSN` env var, but DSN is empty in prod settings dump.
- `audit_log` Django app is installed (`INSTALLED_APPS`), referenced in views for *reading* dashboards, but nothing in app code calls `AuditLog.objects.create(...)`. This is the single most surprising gap in the audit — the infrastructure is there, the writes aren't.
- DEBUG=True means every uncaught exception currently dumps the full settings page to the user, which is observability *of the worst kind*: visible to attackers, invisible to operators.
- No request tracing, no APM, no Application Insights wiring (despite running on Azure where it's a one-checkbox add).

**Risk Level:** High (compliance and forensic).
**Effort to Fix:** Low.
**Benchmark.** A government-data app should at minimum have Sentry + Application Insights + audit logging on every privileged action. This app has zero of those running in production, despite *all three* being partially configured in code.
**Remediation.** (a) Provision Sentry, set `SENTRY_DSN`; (b) enable Application Insights via `OpenCensus`/`OpenTelemetry` Python SDKs; (c) add `AuditLog.objects.create(...)` calls to: superuser promotion, group changes, MaterialOrder approvals/releases, ReleaseLetter generation, BOQ over-issuance approvals, user deactivation, bulk imports.

### 4.9 Infrastructure & Deployment Posture

**Findings.** This is the worst-graded dimension.
- **Database:** SQLite under multi-worker Gunicorn on App Service. SQLite serialises writes via OS-level file locks — workable for ~50 users but degrades visibly under any concurrent write load. Until the in-progress fix lands, the SQLite file lives at `/tmp/<deploy-hash>/db.sqlite3` and is wiped on every deploy. **This caused real, irrecoverable data loss in production.**
- **Migrations:** No startup command runs migrations. Until the WSGI hook in this branch lands, schema drift between code and DB is whatever the last manual `migrate` left behind.
- **Secrets/config:** Externalised correctly to App Service Application Settings, but the deployment was missing `DJANGO_DEBUG=False` and didn't have a `DATABASE_URL`, which is what caused the cascade.
- **CI/CD:** No GitHub Actions or Azure DevOps pipelines visible. Deployment appears to be a direct push to a deployment slot. No security gates on PR.
- **Health checks:** None visible.
- **Reverse proxy:** Azure App Service front-end terminates TLS, so this is effectively present, but no Nginx/Caddy customisation layer for fine-grained header/CSP injection.
- **Container security:** N/A (App Service code deployment, not container).

**Risk Level:** **Critical** before our patches; **High** after.
**Effort to Fix:** Medium (Postgres migration + CI/CD pipeline).
**Benchmark.** A standard Django on Azure deployment uses: (a) Postgres Flexible Server with managed identities; (b) GitHub Actions or Azure DevOps with a `migrate --noinput` step before slot swap; (c) deployment slots with health checks; (d) Application Insights; (e) Key Vault references for secrets. This app is missing all of (a)-(e).
**Remediation.** Phase 1: ship the changes in this branch. Phase 2: provision Postgres, write a GitHub Actions workflow that runs tests + migrate + slot-swap, add health-check endpoint and configure App Service to use it.

### 4.10 Business Logic & Workflow Integrity

**Findings.** Limited code-path inspection due to size of view modules (44k LOC in `order_views.py` alone — too large for a one-shot audit). What I observed:
- `MaterialOrder` has `processed_quantity` and `remaining_quantity` tracked, with notification signals firing on changes (`signals.py:194-218`). But there's no `select_for_update()` or transaction-wrapped quantity update visible — partial-processing under concurrent requests could double-count.
- Approvals/releases trigger notifications via signals; idempotency on retried notifications is not visible.
- Bulk imports (`pd.read_excel`) appear to call `Model.objects.create()` per row without `transaction.atomic()` — partial imports leave the DB in mixed state.

**Risk Level:** Medium (driven by data integrity, not security).
**Effort to Fix:** Medium-High.
**Benchmark.** Production inventory systems (e.g. Odoo, ERPNext) wrap every multi-row mutation in transactions, use SELECT FOR UPDATE on quantity decrements, and emit idempotency-keyed notification jobs to a queue.
**Remediation.** Wrap bulk imports in `transaction.atomic()`; add SELECT FOR UPDATE on quantity adjustments; consider Celery + Redis for notification jobs with idempotency keys; add database-level CHECK constraints (`processed_quantity <= quantity`).

### 4.11 Code Quality & Maintainability

**Findings.**
- **Tests:** 6 test files, 618 LOC total. Notably includes `Inventory/tests/test_security.py` (148 LOC) — rare and welcome in a vibe-coded app. Coverage of authentication/authorisation paths appears minimal, however.
- **God-files:** `Inventory/views/order_views.py` (44k LOC), `dashboard_views.py` (36k LOC), `data_views.py` (34k LOC). These dwarf typical Django view modules and resist effective code review or refactoring.
- **Singular/plural inconsistencies:** Group names, model field choices, template aliases. Documented in this session's exploration; needs alignment.
- **`requirements.txt` typo:** `pandas==3.0.0` (does not exist).
- **Linting/formatting:** No `pyproject.toml`, `.flake8`, `.pre-commit-config.yaml`, or `ruff.toml` visible. No formatting enforcement.
- **Type hints:** Not pervasive in the files I read; views are Python-without-types.
- **Dead/legacy code:** `utils_DEPRECATED.py` exists in the repo, referenced as legacy — should be removed.
- **Documentation:** Multiple `.md` files at the project root (USER_PERFORMANCE_GRADING_SYSTEM.md, USER_IMPORT_GUIDE.md, M365_AUTH_MIGRATION_SUMMARY.md, etc.) — better than typical, but no architectural overview or threat model.

**Risk Level:** Medium (maintainability).
**Effort to Fix:** High to do properly; Low for quick wins.
**Benchmark.** A Two Scoops-aligned Django project would have ruff + black + mypy in pre-commit, ≥70% test coverage, services/managers extracting business logic out of views, and view modules under 1k LOC each. This app is significantly above that LOC ceiling and below that test bar.
**Remediation.** Add `ruff` + `black` via pre-commit; introduce mypy in non-strict mode; aim to break up the three god-files into per-feature modules; delete `utils_DEPRECATED.py`; align group names; fix pandas pin.

---

## 5. Scorecard

| Pillar | Weight | Score /100 | Weighted |
|---|---|---|---|
| Security & Auth | 30% | 62 | 18.6 |
| Data Protection | 20% | 50 | 10.0 |
| Deployment & Infra Posture | 20% | 35 | 7.0 |
| Code Quality & Maintainability | 15% | 55 | 8.25 |
| Observability & Error Handling | 15% | 30 | 4.5 |
| **TOTAL** | 100% | | **48.35 / 100** |

**Production Readiness Tier:** **Below 50 — Not currently suitable for production; critical sections must be remediated before further deployment.**

Note: with the in-progress emergency fixes deployed (persistent SQLite, auto-migrate, trusted-admin bootstrap, group recreation, DEBUG=False, secret rotation), the score rises to approximately **62/100** — the "Significant rework required, but viable for limited internal use after Phase 1 is complete" tier. Reaching the 70–84 "Near-production" tier requires Phase 2.

---

## 6. Remediation Roadmap

### Phase 1 — Do Now (before further production exposure)

1. **Push and deploy** the changes from this branch (persistent SQLite, WSGI auto-migrate, trusted admin bootstrap, group recreation migration). [Already drafted.]
2. **Set `DJANGO_DEBUG=False` + `ALLOW_SQLITE_IN_PROD=1`** in App Service Application Settings.
3. **Rotate `MS_CLIENT_SECRET` and `DJANGO_SECRET_KEY`.** Update Azure AD app and App Service config.
4. **Add `http://127.0.0.1:8000/auth/callback/`** to the Azure AD app's redirect URIs for local OAuth.
5. **Fix `pandas==3.0.0` typo** to `pandas==2.2.3`.
6. **Provision Sentry**, set `SENTRY_DSN` in App Service.
7. **Force-logout all sessions** post-rotation (delete all rows in `django_session` via Kudu).

### Phase 2 — Do Soon (within 2 weeks)

1. **Provision Azure Database for PostgreSQL Flexible Server**; set `DATABASE_URL` with `sslmode=require`; dumpdata/loaddata; drop `ALLOW_SQLITE_IN_PROD`.
2. **Replace WSGI auto-migrate with proper startup command** (`bash -c "python manage.py migrate --noinput && gunicorn ..."`); set `RUN_MIGRATIONS_ON_STARTUP=0`.
3. **Move `TRUSTED_ADMIN_EMAILS` to env var only**; remove hardcoded list.
4. **Add `audit_log` writes** for: superuser promotion, group membership changes, MaterialOrder approvals, ReleaseLetter generation, BOQ over-issuance approvals, bulk imports, user deactivation.
5. **Add rate limiting** via `django-ratelimit` on auth and upload endpoints.
6. **Add file-upload validation**: MIME via `python-magic`, size caps, schema validation via `pandera` for Excel imports.
7. **CI/CD pipeline**: GitHub Actions running tests, `pip-audit`, `bandit`, `ruff` on every PR; deploy via slot swap with health checks.
8. **Enable Dependabot** for the `pip` ecosystem.
9. **Document a 2FA-mandatory policy** for non-Consultant groups; enforce via middleware.

### Phase 3 — Do Eventually (technical debt, hardening, observability)

1. **Refactor god-files** (`order_views.py`, `dashboard_views.py`, `data_views.py`) into per-feature modules; extract business logic into a service layer.
2. **Adopt Azure Key Vault references** for secrets in App Service Application Settings.
3. **Add Application Insights** for request tracing and APM.
4. **Add Content-Security-Policy** via `django-csp`, start report-only.
5. **Field-level encryption** for PII (`django-fernet-fields`) on supplier banking details, signatures, and any other identified high-sensitivity fields.
6. **Document retention policy**, automate purges of old `audit_log` rows and stale `django_session` rows.
7. **Object-level permissions** via `django-guardian` or hand-written `get_object()` overrides.
8. **Test coverage to ≥70%**, with explicit tests for authorisation paths.
9. **Resolve singular/plural group name inconsistencies** by aligning on plural everywhere; update `setup_groups.py`.
10. **Threat-model document** + architectural overview in `/docs`.
11. **Consider Celery + Redis** for notification fanout (currently synchronous via signals; spikes block request handlers).

---

## 7. Benchmark Comparison Summary

Compared to a standard Django + Postgres + Gunicorn/Nginx production stack following the *Two Scoops of Django* checklist and OWASP ASVS Level 1, MOEN-IMS today is roughly the right *shape* but missing structural pieces. The application code itself — OAuth-only auth, autoescaped templates, no raw SQL with user input, CSRF on state-changing endpoints, 2FA wired in — is already in the same league as a careful internal Django app. Where it falls behind is the deployment, observability, and supply-chain story: a comparable production system would have Postgres with TLS-required connections, secrets in Key Vault, a GitHub Actions pipeline running `pip-audit`+`bandit`+tests on every PR, Sentry+Application Insights writing every error and slow query, an active audit log on privileged actions, file uploads validated via magic-bytes, and a rate-limit on auth endpoints. None of those are conceptually difficult; all are missing here. With Phase 1 done, MOEN-IMS becomes a viable internal-use app. With Phase 2, it reaches parity with a typical "good" departmental Django deployment. Phase 3 is what separates "good" from "I'd be happy showing this to an external auditor."

---

## Coverage Caveats

This audit is based on (a) files directly read during this session's incident-response work — `settings.py`, `wsgi.py`, `accounts/views.py`, `Inventory/middleware.py`, `Inventory/signals.py`, `Inventory/management/commands/setup_groups.py`, `Inventory_management_system/urls.py`, `requirements.txt`, latest migrations, `.env.example` — plus (b) code-graph search across the full repo for specific patterns (raw SQL, `csrf_exempt`, hardcoded secrets, file upload entrypoints, audit-log writes, decorator usage, etc.). It is **not** a line-by-line review of all 25 view files, all 59 templates, all forms, the static-asset bundle, or the 30+ migrations. A formal certification audit would extend coverage into those areas and validate runtime behaviour against the documented findings. Findings stated as "High" or "Critical" reflect either direct observation or a reasonable inference from observed patterns; uncertain cases have been called out with hedged language.

---
