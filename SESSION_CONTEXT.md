# MOEN-IMS — Context & Handoff Document

*Generated from the hardening session of 2026-06-08 → 06-10. Read this first to pick up the project cold.*

---

## 1. What this system is

**MOEN-IMS** — the Ministry of Energy & Green Transition (Ghana) Inventory Management System. A Django 5.1 web app that tracks the flow of electrification materials: material **orders** → **release letters** → **transport/waybills** → **site receipts**, against **Bills of Quantity** and **project sites**, with external **transporters** and **consultants** as partners.

- **Stack:** Django 5.1.15 · Python 3.14 (Azure) / 3.12 (CI) · ~46k lines first-party code.
- **Hosting:** Azure App Service (Linux, Oryx build, auto-deploy on push to `main`).
- **Auth:** Microsoft 365 SSO (`msal`) + 2FA (`django-otp`).
- **Security/infra libs:** `django-axes` (brute-force), `django-ratelimit`, `django-csp`, `whitenoise` (static), `django-storages[azure]` (media→Blob), `redis` (cache), `sentry-sdk`.
- **Status right now:** code hardened, committed, CI green — but the live deploy is **Blocked** (see §6).

---

## 2. The codebase map

Built with a structural code-graph (graphify). First-party code only (vendored venv excluded): **~268 files, ~2,080 nodes**.

```
IMS/Inventory_management_system/
├── manage.py
├── Inventory_management_system/
│   ├── settings.py          ← all config + security gates (DEBUG, DB fail-fast, CSP, STORAGES, rate limits)
│   ├── urls.py / wsgi.py
├── Inventory/               ← the main app
│   ├── models/              inventory · orders · transport · people · projects · suppliers · users · geography
│   ├── views/               order_views · dashboard_views · request_flow_views · map_views · geospatial_views · user_views …
│   ├── item_views.py        AddItem / EditItem / DeleteItem  (CBVs)
│   ├── transporter_views.py download_waybill_pdf + transport admin  (~2,500 lines)
│   ├── services/            kpi · audit · bulk_import · release_code · scan_validation · executive_renderer …
│   ├── forms/  serializers/
│   ├── middleware.py        UserRoleMiddleware  ← the central auth gate
│   ├── signals.py           post_save side-effects (notifications, stock reservation, stamps)
│   ├── urls.py
│   └── tests/               the real test package (184 tests)
├── accounts/                M365 OAuth (ms_login / ms_callback), trusted-admin bootstrap
└── audit_log/
```

**Layered flow (e.g. item create/update):** URL → CBV (`item_views`) → `ModelForm` (`forms/`) → model (`models/`) → `post_save` signal. Note: the basic item path has **no service layer** — business logic lives in form `clean()` + signals. Richer flows (material order → release → transport) do route through `services/`.

**Highest-blast-radius functions (the risk hotspots the graph flagged — untested before this session):**

| Function | File | Size |
|---|---|---|
| `download_waybill_pdf` | `transporter_views.py` | 1,085 lines |
| `management_dashboard` | `views/dashboard_views.py` | 545 lines |
| `upload_requests` | `views/request_flow_views.py` | 284 lines |
| `handle_bulk_request` | `views/order_views.py` | 258 lines |

**Critical architectural fact:** authentication is enforced **centrally** by `UserRoleMiddleware` (a default-deny allowlist in `process_view`), **not** by per-view `@login_required`. Whole view modules have no decorator — they're protected only because that one middleware redirects unauthenticated/unassigned users. It is now under test (`test_middleware_auth.py`).

---

## 3. The access / role model map

Roles (canonical groups, seeded by migration `0031`): **Store Officers, Stores Management, Schedule Officers, Management, Consultants, Transporters**.

| Who | Should see | Enforcement |
|---|---|---|
| Superuser / **Management** | Everything | bypass all scoping |
| Internal officers (Store / Schedule / Stores Mgmt) | All operational data — **by design** (they collaborate; a Schedule Officer must see others' orders to schedule transport) | not row-scoped, intentionally |
| **Transporters** (external) | Only their own shipments | `MaterialTransport.transporter.user` — scoped on `download_waybill_pdf` ✅ |
| **Consultants** (external) | Only their own region | `ProjectConsultant.region` (FK `user`) — scoped on `consultant_dash` ✅ |

**Key insight:** the "users see other teams' orders" finding in the old `CODE_QUALITY_ASSESSMENT.md` is real but mostly *by design* for internal roles. The genuine confidentiality risk was **external partners** seeing beyond their company/region — that's what was fixed this session (waybills, consultant dashboard). A fully exhaustive per-view consultant-reachability audit is still open (see §7).

---

## 4. What was done this session

A graph-driven hardening pass on top of an earlier (2026-06-06) pass. All tracked in `HARDENING_PLAN.md §1d`. Highlights:

**Security / authorization**
- **IDOR fixes (object-level scoping + tests):** item edit/delete (`EditItem`/`DeleteItem`), waybill download (external transporters → own only), consultant dashboard (external consultants → own region, fail-closed).
- **Removed a hardcoded superuser-bootstrap email backdoor** → now env-only (`TRUSTED_ADMIN_EMAILS`).
- **Fixed an inert OAuth rate limit:** `ms_login`/`ms_callback` used `method='ALL'` (a string), which `django-ratelimit` silently ignores — the throttle was doing nothing. Now uses the `ALL` sentinel.
- **Per-user rate limiting** added to the heavy endpoints (waybill PDF, bulk upload, bulk request), env-tunable.

**Reliability / scaling**
- **Media → Azure Blob** via `django-storages` (uploads were on ephemeral local disk); migrated static config to Django 5.1 `STORAGES`.
- **KPI dashboard caching** (`get_management_dashboard_summary`, short-TTL Redis).
- **Postgres fail-fast** (from the earlier pass) — the app refuses to boot in prod without `DATABASE_URL`.

**Hygiene / CI**
- Untracked the vendored virtualenv (`venv_pdf`, 880 files); deleted stray root-level debug scripts that broke test discovery (`testes.py`, `test_config_url.py`, `test_totp.py`, `test_user_import.py`).
- Dead code removed, naive-datetime bugs fixed, CI guard banning `method='ALL'`.
- **Dependency CVE bumps** (pip-audit gate): Django 5.1.5→5.1.15, cryptography→48, DRF→3.15.2, Pillow→12.2.0, python-dotenv→1.2.2, msal→1.37 (pin relaxed to clear a cryptography conflict).
- **~45 new tests** across 7 files; full suite **184 passing**; CI (`pip-audit` + `ruff` + tests) green.

---

## 5. Key files

**New test files:** `test_item_authz.py`, `test_waybill_authz.py`, `test_consultant_region_authz.py`, `test_hub_characterization.py`, `test_rate_limits.py`, `test_middleware_auth.py`, `test_kpi_cache.py` (all in `Inventory/tests/`).

**Edited:** `settings.py`, `item_views.py`, `transporter_views.py`, `views/dashboard_views.py`, `views/request_flow_views.py`, `views/order_views.py`, `services/kpi.py`, `signals.py`, `middleware.py`, `accounts/views.py`, `requirements.txt` (+ root), `.env.example`, `.github/workflows/ci.yml`.

**Companion docs:** `HARDENING_PLAN.md` (full plan + §1d this pass) · `PRE_PILOT_CHECKLIST.md` (sequenced deploy runbook) · `AZURE_ADMIN_ENV_SETUP.md` (env-var request for the admin) · this file.

---

## 6. Current state & the active blocker

The hardened build auto-deployed to Azure and is **Blocked — `ContainerTimeout` (container did not start within 230s)**.

**Cause:** the new build's fail-fast. With `DEBUG` off (Azure default) and **`DATABASE_URL` + `DJANGO_SECRET_KEY` not set/correct** in Azure App Settings, `settings.py` raises on startup and the container never boots. The *old* build ran because it silently fell back to SQLite; the new one refuses to, by design. **This is the expected ordering trap** — env vars must be set *before* the hardened build deploys.

**Complication:** the developer's Azure Contributor access was removed, so they currently **cannot set the env vars themselves** and are waiting on an unresponsive admin (with management pressure).

**To unblock — minimum to restore service (no Postgres needed):**
```
DJANGO_SECRET_KEY    = <rotated key>
ALLOW_SQLITE_IN_PROD = 1          # temporary; boots on SQLite, fine pre-pilot (no real data). Remove once Postgres is live.
```
**Proper fix:** set `DATABASE_URL=postgres://…` instead of the SQLite flag.

**Fastest org fix:** restore the developer's **Contributor role** on the App Service — then they do all of this themselves in minutes.

**Break-glass (no admin needed):** a temporary `settings.py` change can let the app boot without those env vars (ephemeral SECRET_KEY at startup — no secret in repo; allow SQLite on Azure when `DATABASE_URL` absent). Push auto-deploys it. Must be reverted once env vars are set. *Not yet implemented — available on request.*

---

## 7. Outstanding work (prioritised)

**Blocking the live site (operational, needs Azure access):**
1. Set `DJANGO_SECRET_KEY` + (`DATABASE_URL` **or** `ALLOW_SQLITE_IN_PROD=1`) → unblock container.
2. Provision **Azure Database for PostgreSQL**, set `DATABASE_URL` (this is the real P0-1). Postgres chosen — driver already present, no code change needed. (MySQL would need a driver add first.)
3. Rotate **`MS_CLIENT_SECRET`** in Entra and update it; delete the old one.
4. Add **`TRUSTED_ADMIN_EMAILS`** (recovery admin) — superuser bootstrap after the backdoor removal.

**Post-deploy hardening:**
5. **Blob smoke test** (upload a file, confirm it lands in the container + serves via SAS URL) and confirm the app is on Postgres.
6. Flip **`CSP_ENFORCE=1`** (currently report-only) and click through dashboards/maps/charts/PDF.
7. **Backup + tested restore drill** on Postgres.
8. **Git history scrub** — old `.env` (rotated secrets) + committed SQLite DBs are still in history; `.git` ~290 MB. Runbook in chat/`HARDENING_PLAN.md`. Do after MS secret rotation.

**Code follow-ups (post-pilot, not blockers):**
9. Per-view consultant **region-reachability** audit (map/geo views take `?region=` without enforcing the binding — confirm consultants can't reach them).
10. Refactor **raw `MEDIA_ROOT`** paths (signature stamps, logos in `transporter_views.py`) to the storage API so they also use Blob.
11. Decompose the **god-functions** (`download_waybill_pdf`, `management_dashboard`) under their characterization tests.
12. Move to **nonce-based CSP** (drop `'unsafe-inline'`) — the real XSS lockdown.
13. Add an **inventory transaction ledger** (`InventoryItem.quantity` is point-in-time only).

---

## 8. Azure App Service — required environment variables

| Variable | Purpose | State |
|---|---|---|
| `DATABASE_URL` | Postgres connection string | ❌ **missing — blocking** |
| `DJANGO_SECRET_KEY` | session/CSRF signing (rotated) | ⚠️ needs the new value |
| `ALLOW_SQLITE_IN_PROD` | temporary SQLite escape hatch | set to `1` only as stopgap |
| `MS_CLIENT_ID` / `MS_TENANT_ID` / `MS_REDIRECT_URI` | M365 OAuth | ✅ present |
| `MS_CLIENT_SECRET` | M365 OAuth secret | ⚠️ rotate in Entra |
| `TRUSTED_ADMIN_EMAILS` | superuser bootstrap | ➕ add |
| `TOKEN_ENCRYPTION_KEY` | token encryption | ✅ present |
| `AZURE_ACCOUNT_NAME` / `_KEY` / `AZURE_CONTAINER` | Blob media storage | ✅ present |
| `CANONICAL_HOST` / `DJANGO_CSRF_TRUSTED_ORIGINS` | host/CSRF | ✅ present |
| `CSP_ENFORCE` | flip CSP to enforcing | leave unset until post-deploy review |
| `DJANGO_DEBUG` | not required — defaults off on Azure | — |

*`DEBUG` is intentionally not required: the code defaults it to `False` whenever `WEBSITE_SITE_NAME` is set (i.e. on Azure).*
