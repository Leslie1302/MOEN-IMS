# MOEN-IMS Implementation Plan — Reports, Archive, Polish

**Date:** 2026-05-14
**Owner:** Leslie Adjetey
**Build session:** Continuing from 2026-05-08 plan

This plan captures the new requests received on 2026-05-14, ordered so the
production blocker (the stores hub crash) lands first and the bigger
re-design / report work fans out from there.

---

## Status Snapshot

### Already shipped this session (verification pending on user side)
- [x] Strict QR validation on legacy upload route (no more arbitrary PDF accepts)
- [x] OpenCV + PyMuPDF decoder; printed-code text fallback; pyzbar / poppler no longer required
- [x] Release-letter detail page redesign (stepper, document tabs, project-typed accents)
- [x] MP auto-populate by constituency/district/region
- [x] Transporter / ProjectConsultant `user` FK + Transporters group mirrors Consultants permissions
- [x] Migrations 0042 (FK additions) and 0043 (canonical groups refresh)
- [x] Weekly report send path switched to Microsoft Graph (M365)
- [x] Splash screens disabled + kill-switch CSS/JS
- [x] Duplicate table controls on the 5 known list pages (release letters, transporters, vehicles, transporter legend, material legend)

### Carried forward into this plan
- [ ] Plain-English "Executive" weekly report mode
- [ ] Weekly report correctly categorises features and bug fixes (not lumped into Migrations)
- [ ] Weekly report surfaces the new audit-trail entries
- [ ] Generator moved to admin-only; user-facing page is read-only "View weekly reports"
- [ ] Redesign of the View Weekly Reports list page to match the release-letter design language
- [ ] Material orders: split active vs archived
- [ ] Archived transport assignments: download-waybill link per row
- [ ] Stock dashboard: still has duplicate search bar + pager (different template than the 5 already fixed)
- [ ] Stores Operations Hub: `VariableDoesNotExist 'username' on None` — template crash

---

## Phase J — Production blocker fixes (FIRST)

**Goal:** Unblock the stores hub page and any other crash-on-render template
issues uncovered while testing.

**Tasks:**
- [ ] Fix `StoreOperationsHubView` template: locate the `{{ ?.username }}` reference that fires when the related object is None, and guard it with `{% if ... %}`
- [ ] Audit nearby store templates (`store_operations_hub.html`, partials it includes) for the same anti-pattern (`obj.user.username` without a None guard)
- [ ] Smoke test: load `/stores/hub/` as superuser AND as a non-storekeeper user; both must render without 500

**Deliverable:** `/stores/hub/` stops 500-ing.
**Effort:** 30 minutes.

---

## Phase K — Weekly reports overhaul

**Goal:** Add an "Executive (plain English)" report alongside the technical one,
correctly classify features vs bug fixes, surface the audit trail, and lock
generation to superusers via the admin.

### K.1 — Executive (plain English) report mode

- [ ] Add a `mode` choice on `WeeklyReport` model (`technical` / `executive`) — migration 0044
- [ ] Build `executive_renderer.py` that takes the same analyser output and produces:
  - **Executive Impact** — 3-sentence summary (counts of orders, releases, deliveries; "zero pending" callouts)
  - **Process Improvements** — translation table that maps technical change types to functional language:
    - `add_field` / `migration` → "Strengthened the digital authorization chain" etc., per the user-provided dictionary
    - `new_view` / `new_endpoint` → "Enabled specialized tracking for X"
    - `bug_fix` (from commit subject containing fix:|bug|hotfix) → "Resolved an issue where…"
  - **Operational Health** — % orders processed, notifications sent, audit-log volume
  - **Strategic Outlook** — pulls from a small admin-editable `weekly_outlook` text field (so the user can override it before sending)
- [ ] Add a toggle on the admin generate-report form: "Technical (engineering)" / "Executive (plain English)"
- [ ] The PDF and HTML email body both honour the selected mode
- [ ] Keep both modes available; the user picks per-send

### K.2 — Classify features and bug fixes correctly

- [ ] Today, all schema/code changes pile into a "Migrations" section. Audit `report_generator._categorize_commits` — it likely buckets anything with the word "migration" into one bucket
- [ ] New rules:
  - Commit subject matches `^feat:` / contains "add" / "implement" → **Features**
  - Commit subject matches `^fix:` / contains "fix", "bug", "hotfix" → **Bug Fixes**
  - Commit subject matches `^refactor:` / "refactor", "cleanup" → **Improvements**
  - Migration files alone don't trigger a Migrations section — they fold into Features (when the linked commit was a feat) or Improvements
- [ ] Also pull from the `audit_log` table: state transitions are reported as "Operational events", not code changes

### K.3 — Audit-trail section

- [ ] New report section "Audit highlights" listing top N audit-log entries by significance for the week:
  - Force-accepts (`release.legacy_force_accepted`, `release.scan_force_accepted`)
  - Two-person confirmations
  - Group/role changes
  - Bulk import summaries
- [ ] Show these in BOTH the technical and executive renderers, but with different wording per mode

### K.4 — Permission move + UI

- [ ] Remove the "Generate weekly report" entry from the Management dashboard
- [ ] `/weekly-reports/` becomes a strictly read-only list (already gated to Management; keep that)
- [ ] All generation flows live under `/admin/Inventory/weeklyreport/generate/` — already true; just remove the alternate entry point
- [ ] Add a small note on `/weekly-reports/` that says "Reports are generated from the admin portal by the team lead."

### K.5 — Visual redesign of the View Weekly Reports page

- [ ] Mirror the release-letter detail page's pattern (used in the user's attached image):
  - Stats strip at the top: Total Reports / Sent / Draft
  - Card-based table with status pills (Sent / Draft) and right-aligned action buttons (View, PDF)
  - Sender column showing `firstname.lastname@energymin.gov.gh`
- [ ] Use the same `rl-card` + `rl-pill` CSS tokens for visual consistency

**Effort:** ~1 day for the executive renderer, ~half a day for the redesign.

---

## Phase L — Material orders archive

**Goal:** `/material-orders/` shows only ongoing orders. Completed / cancelled
/ released orders move to a dedicated archive view.

**Tasks:**
- [ ] Decide active-vs-archived boundary. Default proposal:
  - **Active:** status in `Pending`, `Approved`, `Awaiting Storekeeper`, `Processing`, `Partially Fulfilled`, `Awaiting Transport`
  - **Archived:** status in `Completed`, `Released`, `Cancelled`, `Voided`, `Returned`
- [ ] Update `MaterialOrdersView.get_queryset` to filter to active by default
- [ ] Add `MaterialOrdersArchiveView` at `/material-orders/archive/`
- [ ] Both views share the same template via context flag `is_archive` so filters / search keep working
- [ ] Add nav link: Schedule dropdown → "Archived material orders"
- [ ] Schedule Officers / Management see archive; Store Officers see it through `/material-orders-officers/archive/` too if needed (confirm with user)

**Effort:** 2 hours.

---

## Phase M — Transport archive waybill links

**Goal:** The archived transport assignments page already lists past
deliveries but exposes no way to fetch the waybill PDF. Add the link.

**Tasks:**
- [ ] Find `transportation_archive.html` (or equivalent) — confirm the URL name `download_waybill_pdf` is wired
- [ ] Add a `<a href="{% url 'download_waybill_pdf' transport.id %}">` button per row
- [ ] If the transport has no waybill (e.g. very old assignments), show a disabled "No waybill" badge instead

**Effort:** 30 minutes.

---

## Phase N — Stock dashboard double-controls cleanup

**Goal:** The dashboard the user screenshotted (showing two search bars and
two pagers stacked) is NOT in the 5 templates already fixed in Phase 10.
Find it and apply the same opt-out.

**Tasks:**
- [ ] Trace the screenshot to a specific template (probably `bill_of_quantity.html`, `dashboard.html`, an inventory-list, or one of the stores templates)
- [ ] Audit it for `enhanced-table` + DataTables collision OR a custom toolbar duplicated above + below the table
- [ ] Strip the duplicate; add `data-no-enhanced` if the table is DataTables-managed
- [ ] Smoke test the page — only one search bar, one pager

**Effort:** 30 minutes once the template is identified.

---

## Critical Path

```
Phase J (production fix) — must complete first
        │
        ├──► Phase L (material orders archive) — small, independent
        │
        ├──► Phase M (transport archive waybill) — small, independent
        │
        ├──► Phase N (stock dashboard duplicates) — small, independent
        │
        └──► Phase K (weekly reports)
                    │
                    ├──► K.1 Executive mode
                    ├──► K.2 Classification fix
                    ├──► K.3 Audit-trail section
                    ├──► K.4 Permission move
                    └──► K.5 List page redesign
```

Wall-clock estimate: **2–3 focused days**.

---

## Definition of Done

- [ ] /stores/hub/ renders for both superuser and storekeeper accounts
- [ ] Weekly report has a working "Executive" toggle that produces plain-English output following the user-supplied prompt
- [ ] Features and bug fixes appear in their own report sections; nothing important hides under "Migrations"
- [ ] Report includes an "Audit highlights" section pulling from audit_log
- [ ] Generate-report entry point exists only under /admin/; non-admins see View only
- [ ] /weekly-reports/ list page matches the release-letter design language
- [ ] /material-orders/ shows only active orders; /material-orders/archive/ shows the rest
- [ ] Archived transport rows have a Download waybill button
- [ ] Stock dashboard table shows exactly one search bar and one pager

---

## Notes captured from this conversation

**Executive-report prompt (verbatim, for the renderer to follow):**

> Role: Act as a Senior Product Manager at the Ministry of Energy.
> Task: Transform technical development logs into a polished, non-technical Weekly Progress Report for the Chief Director.
>
> Formatting rules:
> 1. Avoid technical terms (no "migrations", "database schema", "views.py", "refactoring")
> 2. Focus on value — for every technical change, explain why it matters
> 3. The "So What?" test — if a task doesn't directly help the user or business process, frame it as "System Reliability & Security Improvements"
>
> Report structure:
> - Executive Impact (3-sentence summary)
> - Process Improvements (translate technical updates into functional ones)
>     - "streetlights project type" → "Enabled specialized tracking for Streetlight infrastructure projects"
>     - "updated signatory fields" → "Strengthened the digital authorization chain for material releases"
> - Operational Health — % processed, notifications sent
> - Strategic Outlook — "Finalizing administrative workflows and refining user communication"
>
> Why this works on the project's data:
> - Migrations 0031–0043 grouped as "Standardising user permissions and regional assignments to ensure data security"
> - "1 user logged in" reframed as a System Adoption metric
> - Developer-only notes filtered out
