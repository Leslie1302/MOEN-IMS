# MOEN-IMS — Pre-Pilot Runbook

**Status:** Code hardened and the full test suite passes locally (**184 tests, OK**). What remains is committing, deploying with the right infrastructure, and a short post-deploy checklist. Work the phases in order — a couple of steps will take the app down if done out of sequence (flagged ⚠️).

---

## Phase 0 — Done (in code, verified by tests)

- Auth gate (`UserRoleMiddleware`) tested; brute-force lockout (axes); 2FA enforcement tested.
- **Authorization / IDOR:** item edit/delete scoped to group; **waybill download** scoped to the owning transporter; **consultant dashboard** scoped to the consultant's region (fail-closed). Internal roles intentionally retain shared visibility.
- Removed the hardcoded **superuser-bootstrap email backdoor** → env var.
- **Rate limiting** on auth + heavy endpoints (and fixed the previously-inert OAuth throttle).
- **Media → Azure Blob** (uploads survive deploys); static via WhiteNoise.
- KPI dashboard caching; dead code, naive-datetime, and CI guard cleanups.
- ~45 new tests; CI runs `pip-audit` + `ruff` + the suite as a blocking gate.

---

## Phase 1 — Commit (do now)

```bash
rm IMS/Inventory_management_system/Inventory_management_system/testes.py   # if not already deleted
python manage.py test          # confirm: OK
git add -A && git commit -m "Harden: authz scoping, rate limits, media→Blob, CSP, cleanups"
```

---

## Phase 2 — Infrastructure & env (admin — see AZURE_ADMIN_ENV_SETUP.md)

Set in **Azure App Service → Environment variables**:

- ⚠️ `DATABASE_URL` = the **PostgreSQL** connection string. **Must be set before the new build deploys**, or the app fails fast and won't boot.
- `DJANGO_SECRET_KEY` = the rotated key.
- `MS_CLIENT_SECRET` = the newly rotated Entra secret (delete the old one once verified).
- `TRUSTED_ADMIN_EMAILS` = the recovery admin email(s).
- `CSP_ENFORCE` — leave **unset** for now (enable in Phase 4).
- Confirm the Blob vars (`AZURE_ACCOUNT_NAME/KEY/CONTAINER`) are present and the container exists.

(`DJANGO_DEBUG` is not required — the app defaults it off on Azure.)

---

## Phase 3 — Deploy & verify

1. Deploy (push to `main` → Oryx builds, runs `migrate`).
2. App boots, home page loads (no 500).
3. Microsoft 365 sign-in works (validates the new `MS_CLIENT_SECRET`).
4. Recovery admin (`TRUSTED_ADMIN_EMAILS`) can sign in and reach the dashboard.
5. **Blob smoke test:** upload a profile picture → confirm it appears in the Blob container and displays back in the app.
6. Confirm the app is on Postgres (data persists across a restart).

---

## Phase 4 — Post-deploy hardening

- **Enable CSP enforcement:** set `CSP_ENFORCE=1`, then click through dashboard, maps, charts (Plotly), and PDF download to confirm nothing is blocked. If something breaks, unset it (instant, no redeploy) and report which page.
- **Backup + restore drill:** confirm Azure Postgres automated backups are on, then actually restore one to a throwaway DB and note the recovery time. "We have backups" isn't real until a restore has been tested.

---

## Phase 5 — Repo hygiene (coordinate; rewrites history)

Scrub the old `.env` (rotated secrets) and committed SQLite DBs from git history — see the runbook in chat / `HARDENING_PLAN.md`. Back up a mirror first, force-push, everyone re-clones. Do after the MS secret rotation is confirmed.

---

## Optional follow-ups (post-pilot, not blockers)

- Per-view consultant **reachability audit** — confirm consultants can't reach internal map/site views with `?region=`; apply the region helper if they can.
- Refactor the signature-stamp / logo **raw `MEDIA_ROOT` paths** to the storage API so they also live on Blob.
- Decompose the two god-functions (`download_waybill_pdf`, `management_dashboard`) under their characterization tests.
- Move to **nonce-based CSP** to drop `'unsafe-inline'` (the real XSS lockdown).
- Add a dedicated inventory **transaction ledger** (stock movements are currently point-in-time).

---

## Sign-off criteria for "production-ready"

- [ ] Running on Azure PostgreSQL; SQLite cannot be selected.
- [ ] Uploads served from Blob (smoke-tested).
- [ ] All secrets rotated; none in source; old secrets scrubbed from history.
- [ ] CSP enforcing; login/heavy endpoints rate-limited; account lockout active.
- [ ] External partners (transporters, consultants) scoped to their own data.
- [ ] CI green and gating deploys; full test suite passing.
- [ ] Backups with a **completed, timed restore drill**.
