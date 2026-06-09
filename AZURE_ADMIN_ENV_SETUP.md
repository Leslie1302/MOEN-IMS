# MOEN-IMS — Azure App Service Configuration Request

**To:** Azure / App Service Administrator
**From:** MOEN-IMS development
**App Service:** `moen-ims` (Production slot)
**Purpose:** Set up the environment variables required by the hardened application build, and point the app at a real database. Please read the **two warnings** below before changing anything — one of them can take the site down if the steps are done out of order.

---

## ⚠️ Read first — two things that can cause an outage

1. **The new build refuses to start without a database connection string.**
   The updated code intentionally fails fast: if it is running in production with **no `DATABASE_URL` set**, it raises an error and the app will **not boot**. The site currently runs only because it's an older build that silently used a local SQLite file. So: **set `DATABASE_URL` (or the temporary `ALLOW_SQLITE_IN_PROD` flag below) *before* the new code is deployed.**

2. **A new/empty database starts empty.**
   Pointing the app at a freshly provisioned database gives it an **empty** database — the existing data in the current SQLite file is **not** copied automatically. The data migration must be done as a coordinated cutover with the dev team (export current data → load into the new database → validate), ideally in a maintenance window. **Do not treat "set `DATABASE_URL`" as the whole job.**

---

## Where to make these changes

Azure Portal → **App Service `moen-ims`** → **Settings** → **Environment variables** → **App settings** tab.
Use **+ Add** for new variables, click a name to **edit** an existing one, then **Apply** (the app restarts automatically).

> 🔒 **Security:** the secret *values* are **not** in this document on purpose. They will be sent to you separately through a secure channel. Never paste secrets into email/chat/tickets.

---

## A. Variables to add or change

| Variable | Action | Value | Why |
|---|---|---|---|
| `DATABASE_URL` | **ADD** | connection string for the production DB (see Section B) | The single most important change. Without it the new build won't start. |
| `DJANGO_SECRET_KEY` | **UPDATE value** | new rotated key (sent separately) | The previous key was exposed and must be replaced. Updating it logs all users out once — expected. |
| `MS_CLIENT_SECRET` | **ROTATE + UPDATE** | new client secret (see Section C, step 2) | The previous Microsoft OAuth secret was exposed and must be invalidated in Entra, not just replaced. |
| `TRUSTED_ADMIN_EMAILS` | **ADD** | the recovery admin email(s), comma-separated | Restores the "first superuser" recovery path after a hardcoded admin email was removed from the source code. |

**You do NOT need to add `DJANGO_DEBUG`.** On Azure the app already defaults debug **off** automatically. (Setting `DJANGO_DEBUG=false` explicitly is harmless if you prefer it documented.)

Everything else already present (`MS_CLIENT_ID`, `MS_TENANT_ID`, `MS_REDIRECT_URI`, `TOKEN_ENCRYPTION_KEY`, `CANONICAL_HOST`, `DJANGO_CSRF_TRUSTED_ORIGINS`, the `AZURE_ACCOUNT_*`/`AZURE_CONTAINER` storage settings) can stay as-is.

---

## B. The database decision (needed before `DATABASE_URL`)

The app needs a real, managed database instead of the local SQLite file. **Please confirm which database has been provisioned** and provide its connection string. The choice affects whether a code change is needed first:

- **PostgreSQL (recommended — works immediately).**
  The application already ships the PostgreSQL driver. Format:
  `DATABASE_URL=postgres://USER:PASSWORD@HOST:5432/DBNAME`
  TLS to the database is required by default and is already handled in code.

- **MySQL (needs a one-line code change first — coordinate with dev before setting the URL).**
  The current build does **not** include a MySQL driver, so setting a `mysql://` URL will crash the app until the dev team adds the driver and adjusts the SSL settings. If MySQL is the intended database, **tell the dev team first** so the driver is added in the same release. Format (once supported):
  `DATABASE_URL=mysql://USER:PASSWORD@HOST:3306/DBNAME`

If a managed database isn't ready yet but the hardened build must be deployed, set **`ALLOW_SQLITE_IN_PROD=1`** as an explicit, temporary measure so the app still boots on SQLite — then remove it once the real database is live. (SQLite must not be the long-term production database: it serialises writes and will cause "database is locked" errors and lost writes under concurrent use.)

---

## C. Step-by-step (in this order)

1. **Provision / confirm the managed database** (Section B) and have its connection string ready. If MySQL, confirm with the dev team that the driver has been added in the build being deployed.
2. **Rotate the Microsoft client secret:**
   Azure Portal → **Microsoft Entra ID** → **App registrations** → the MOEN-IMS app (client ID `cc515f40-d90a-4684-bda6-1612844c84a9`) → **Certificates & secrets** → **New client secret** → set an expiry → **Add** → **copy the value immediately** (Entra shows it only once).
3. **In App Service → Environment variables, set:**
   - `DATABASE_URL` = the connection string from step 1
   - `DJANGO_SECRET_KEY` = the new key (sent separately)
   - `MS_CLIENT_SECRET` = the new value from step 2
   - `TRUSTED_ADMIN_EMAILS` = the recovery admin email(s)
4. **Apply.** The app restarts. (If deploying new code at the same time, coordinate so the env vars are in place before/with the deploy.)
5. **After confirming the app is healthy, delete the OLD Microsoft client secret** in the same Entra "Certificates & secrets" screen. This is what actually closes the leak.
6. **Coordinate the data migration** (existing SQLite data → the new database) with the dev team — see Warning #2.

---

## D. Verify after applying

- [ ] The app starts and the home page loads (no 500 / startup error).
- [ ] Microsoft 365 sign-in works (confirms the new `MS_CLIENT_SECRET` is correct).
- [ ] The recovery admin (in `TRUSTED_ADMIN_EMAILS`) can sign in and reach the dashboard (not the "awaiting authorization" page).
- [ ] The live domain loads without a `400 Bad Request` (confirms `CANONICAL_HOST` / allowed hosts cover it — `DEBUG=false` enforces this strictly).
- [ ] The application is reading the new database (data appears as expected after the migration).
- [ ] The old Microsoft client secret has been deleted in Entra.

---

## Questions back to the dev team

- Which database was provisioned — **PostgreSQL or MySQL**? (Determines whether a code change is needed first.)
- Please share the `DATABASE_URL` **scheme** (the first word — `postgres://` vs `mysql://`) so the build can be confirmed compatible.

*Reference: see `HARDENING_PLAN.md` (items P0-1 "database migration" and §1d) in the application repository for background.*
