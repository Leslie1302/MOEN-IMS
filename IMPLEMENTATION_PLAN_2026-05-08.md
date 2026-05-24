# MOEN-IMS Implementation Plan — Multi-Project + Document Workflow

**Date:** 2026-05-08
**Owner:** Leslie Adjetey
**Build session:** This afternoon

This plan consolidates every decision made across the incident-response and design conversation into a single executable roadmap. Phases are listed in execution order with dependencies. Tick boxes as you go.

---

## Status Snapshot (as of plan-write time)

### Already drafted in code, ready to push (Phase 0)
- [x] Persistent SQLite at `/home/site/data/db.sqlite3` on Azure (`settings.py`)
- [x] WSGI-level auto-migrate on container start (`wsgi.py`)
- [x] Trusted-admin bootstrap auto-promoting `leslie.adjetey@energymin.gov.gh` to superuser on Microsoft OAuth login (`accounts/views.py`)
- [x] Migration `0031_create_canonical_groups` creating Store Officers, Stores Management, Schedule Officers, Management, Consultants
- [x] DEBUG auto-defaults to False on Azure (`settings.py`)
- [x] `ALLOW_SQLITE_IN_PROD` auto-defaults to True on Azure (`settings.py`)
- [x] Local `.env` populated with M365 dev credentials (gitignored)
- [ ] **Commit and push the Phase 0 changes** (verification ticks below auto-tick on successful push)

### Settled decisions
- [x] Discriminator pattern (one MaterialOrder model with `project_type` field), not segregated per-project models
- [x] Project type list: `SHEP`, `Cost Sharing`, `Streetlights` (legacy types pruned unless still in active use — to confirm)
- [x] `ProjectType` will be a **model**, not an enum — extensible without code changes
- [x] Memo + release letter linked by code format `RE-{year}-{seq}` (e.g. `RE-2026-0142`), printed on both documents in human-readable form, encoded into QR on the release letter
- [x] QR validates document↔request match on scan upload (rejects wrong-scan / random-PDF uploads); does NOT verify signature authenticity
- [x] Two-person upload review pattern (uploader + confirmer)
- [x] Scan is the legal record of approval; "approved" status flag is workflow convenience only
- [x] Audit log writes wired into every state transition (Phase G)
- [x] Backup + DR before the system becomes load-bearing (Phase H)
- [x] Three bulk-import templates (one per project type) with downloadable per-row error CSV
- [x] Mockup at top of session is the agreed UI spec
- [x] Local-dev login uses Django admin (`/admin/login/`) via `python manage.py createsuperuser` — zero code change

### Open questions (defaults assumed where unanswered, override anytime)
- [ ] **Bulk import UX:** unified page with project-type selector, or three separate per-project import pages? *Default assumed: unified, with project selector at top.*
- [ ] **Letterhead asset:** do you have a digital Ministry letterhead? *Default assumed: leave header space blank; pre-printed paper handles letterhead until you provide an asset.*
- [ ] **Multi-material releases:** does one release letter ever cover multiple materials? *Default assumed: yes — Phase F will introduce a materials table; existing single-material flow remains supported.*
- [ ] **Legacy project types** (`Turnkey`, `China Water`, `Other Electrification`): keep, archive, or delete? *Default assumed: archive (`active=False` on `ProjectType`) so legacy data survives but new requests cannot select them. Override if any are still operationally active.*
- [ ] **MP↔Constituency mapping data:** *Default assumed: manual entry — admins create `MemberOfParliament` records and assign to communities by region/district. Bulk import of MP-constituency data can come later if a master spreadsheet exists.*
- [ ] **Letter signatory policy:** *Default assumed: Chief Director "FOR: HON. MINISTER" is the standard sign-off. Make signatory configurable per `ReleaseEvent` so exceptions are possible.*

---

## Phase 0 — Emergency Stabilization (DO FIRST)

**Goal:** Push the in-flight fixes to production so the database stops getting wiped, security cookies activate, and the foundation for the rest of the work is stable.

**Prerequisites:** None — code already drafted in the repo.

**Tasks:**
- [ ] `git add` the four modified files: `settings.py`, `wsgi.py`, `accounts/views.py`, `Inventory/migrations/0031_create_canonical_groups.py`
- [ ] Commit: `Emergency fixes: persistent SQLite, auto-migrate, trusted admin, group recreation, DEBUG auto-off`
- [ ] `git push`
- [ ] Watch Azure App Service log stream for `Created auth groups: …` and `Auto-promoted trusted admin email …` messages to confirm migrations and bootstrap fire correctly
- [ ] Test login via Microsoft OAuth on production; confirm dashboard renders without `no such table` errors
- [ ] Visit production once and trigger a 500 (e.g. an unmapped URL); confirm the *generic* Django 500 page renders, NOT the settings-leak debug page

**Deliverables:** Stable production. Database persists across deploys. You're a superuser. No more secret-leaking debug pages on errors.

**Effort:** 30 minutes including verification.

---

## Phase A — Foundation: Model Alignment

**Goal:** Reconcile the two disagreeing project_type enums (`Project` vs `MaterialOrder`) into one canonical source. Introduce `ProjectType`, `MemberOfParliament`, and `Consultant` as proper models so the consignee-routing rules live in data, not scattered string checks.

**Prerequisites:** Phase 0 deployed.

**Tasks:**
- [x] Decide canonical project type list — defaulted to active: SHEP, Cost Sharing, Streetlights; archived (active=False): Turnkey, China Water, Other Electrification, Special / Other
- [x] Create `Inventory/models/project_type.py` with `ProjectType` model
- [x] Create `Inventory/models/people.py` with `MemberOfParliament` and `ProjectConsultant` models
- [x] Data migration to seed `ProjectType` rows (migration `0033_project_type_people_and_seed`)
- [ ] Replace `Project.project_type` CharField with FK to `ProjectType` — **deferred to Phase B/C** because the form/view/template/admin/test cascade is tightly coupled with that work; doing it in isolation would leave callers broken
- [ ] Replace `MaterialOrder.project_type` CharField with FK to `ProjectType` — **deferred to Phase C** for the same reason
- [x] Create constants module `Inventory/constants.py` with `get_project_type(code)` and `active_project_types()` helpers, plus `LEGACY_PROJECT_TYPE_MAP` for the deferred FK migration
- [x] Add `Inventory/services/consignee_resolver.py` with `resolve_consignee(project_type, community, project)` — pure function returning a `ResolvedConsignee` dataclass (kind, name, detail, display_label, render method, reason on failure)
- [x] Update `setup_groups.py` management command to use plural names matching migration 0031, plus added `Stores Management` and `Transport Officers` for full coverage
- [x] **Bonus:** Migration `0032_materialtransport_waybill_download_count` closes the long-standing `waybill_download_count` state-vs-schema drift via `SeparateDatabaseAndState` (this was a security-audit Phase-3 item)

**Deliverables shipped:**
- New tables: `Inventory_projecttype`, `Inventory_memberofparliament`, `Inventory_projectconsultant`
- 7 ProjectType rows seeded (3 active, 4 archived)
- Consignee resolver returns ResolvedConsignee for SHEP→consultant, Cost Sharing→MP, Streetlights→MP, with graceful fallback to region-level MP lookup when constituency mapping isn't yet populated
- All callers can now `from Inventory.constants import PROJECT_TYPE_SHEP, ...` and `from Inventory.services.consignee_resolver import resolve_consignee`

**Deferred work** (will land in Phases B + C):
- Project.project_type CharField → FK conversion (alongside Phase B's community refactor)
- MaterialOrder.project_type CharField → FK conversion (alongside Phase C's request flow)
- These are bundled with the views/forms/templates that read those fields, so all moves together

**Effort actually used:** 1 session (foundation only; FK conversion + caller updates rolled into B/C).

---

## Phase B — Community Refactor

**Goal:** Rename "Add SHEP Community" → "Add Community"; make Community model project-agnostic; add per-project bulk-import templates.

**Prerequisites:** Phase A complete.

### Phase B.1 — Model rename + project_type FK (DONE this session)
- [x] Rename `SHEPCommunity` → `Community` via `migrations.RenameModel` (DB table `Inventory_shepcommunity` → `Inventory_community`)
- [x] Add `project_type` FK from `Community` to `ProjectType` (nullable initially with backfill — keep nullable for safety until all callers are migrated, tighten in Phase B.2)
- [x] Add `member_of_parliament` FK (nullable, optional explicit consignee binding) and `constituency` CharField (used by the resolver fallback chain)
- [x] Make `package_number` field optional (`blank=True`); form-level validation will require it when project_type is SHEP (added in Phase B.2)
- [x] Backfill existing Community rows to SHEP project_type via RunPython (idempotent)
- [x] Keep `SHEPCommunity` as a backward-compat alias for `Community` in `Inventory/models/__init__.py` so existing imports (views, forms, admin, templates) keep working
- [x] Update admin.py: rename `SHEPCommunityAdmin` → `CommunityAdmin`, add fieldsets for project_type / MP / constituency. Register `ProjectType`, `MemberOfParliament`, `ProjectConsultant` in admin so superusers can manage them
- [x] Migration `0034_rename_shep_to_community` — RenameModel + AlterModelOptions + AlterField + 3 AddFields + RunPython

### Phase B.2 — Form / URL / template label updates (DONE this session)
- [x] Rename `SHEPCommunityForm` → `CommunityForm`; add required `project_type` ModelChoiceField (queryset = active project types only); add `member_of_parliament` (optional FK) and `constituency` (optional CharField) fields; render `package_number` conditionally via JS when project_type name == 'SHEP'; show MP / constituency fieldset only for project types whose name is 'Cost Sharing' or 'Streetlights'. Form-level `clean()` validates package_number requirement for SHEP and silently clears it for non-SHEP types
- [x] Keep `SHEPCommunityForm` as an alias for `CommunityForm` so existing imports keep working
- [x] Add new URL paths under `/communities/` with names `community_list`, `community_create`, `community_update`, `community_delete`
- [x] Keep `shep_community_*` URL names alive (point to the same views at the same new paths) so existing templates keep resolving
- [x] Add 301 redirects from `/shep-communities/...` to the new paths for external bookmarks
- [x] Update template labels: page titles ("SHEP Community" → "Community"), headings, navigation dropdown header, list table now shows a Project column and a Constituency / MP column
- [x] Update `shep_community_form.html` to render the new fields with conditional JS toggling
- [x] Update `shep_community_confirm_delete.html` to show project type, MP, constituency in the confirm details
- [x] Update navigation: "SHEP Community Management" → "Community management"; "SHEP Communities" → "Communities"; "Add SHEP Community" → "Add community"
- [x] Update abbreviation legend "Back to communities" link
- [ ] **Deferred to Phase B.3:** rename view classes (`SHEPCommunityCreateView` → `CommunityCreateView`), rename file (`shep_community_views.py` → `community_views.py`), drop the `SHEPCommunity` model alias and `SHEPCommunityForm` form alias, rename templates on disk. These are pure renames with no UX impact and bundle naturally with B.3 cleanup.

### Phase B.3 — Bulk import infrastructure (DONE this session)
- [x] Generic bulk-import service module (`Inventory/services/bulk_import.py`) with `BulkImportResult`, `RowError`, `normalize_cell`, `require_columns` helpers; results render as downloadable error CSV
- [x] Three project-aware community templates served by a single view (`download_community_template?project=shep|cost_sharing|streetlights`) — SHEP includes package_number column; Cost Sharing / Streetlights omit it; constituency + mp_name optional on all three; project-specific theme color and example row
- [x] MP roster template (`download_mp_template`) with required name/constituency/region columns, optional title (defaults to 'Hon.') / district / email / phone
- [x] Project-aware community upload view (`upload_communities`) — validates per-row, looks up MPs by exact name, skips duplicates against (region, district, community, package_number, project_type), commits successful rows in `transaction.atomic`, returns error CSV for failed rows
- [x] MP bulk upload view (`upload_members_of_parliament`) with same error-CSV pattern
- [x] Permission gate: superuser or Management group only
- [x] URL routes wired: `/download-community-template/`, `/upload-communities/`, `/download-mp-template/`, `/upload-mps/`. Old SHEP-specific URLs preserved for backward compatibility.
- [x] Bulk-upload UI on the Community list page: Step 1 download (3 buttons per project), Step 2 upload (project selector + file). Separate MP roster section below. Navigation updated to point at the bulk landing area.
- [x] **Bug fix 1:** Consignee resolver now checks `Community.member_of_parliament` FK first before falling back to constituency/district/region string match (Phase A oversight)
- [x] **Bug fix 2:** Community uniqueness now includes `project_type` so the same physical community can be served under multiple project types (migration `0035_community_unique_per_project`)
- [x] Migration 0034 patched to preserve `base_manager_name='prefetch_manager'` in AlterModelOptions (no-op drift fix)
- [x] Verified: 5 files compile clean, 0035 applies cleanly, MP-override priority works, multi-project uniqueness works, bulk-import service produces valid error CSVs

**Files touched in B.3 + bug fixes:**
- `Inventory/services/bulk_import.py` (NEW, ~95 lines)
- `Inventory/services/consignee_resolver.py` (MP override priority)
- `Inventory/models/shep.py` (unique_together)
- `Inventory/migrations/0034_rename_shep_to_community.py` (base_manager_name preserved)
- `Inventory/migrations/0035_community_unique_per_project.py` (NEW)
- `Inventory/shep_community_views.py` (4 new views, ~280 lines added)
- `Inventory/urls.py` (4 new routes)
- `Inventory/templates/Inventory/shep_community_list.html` (per-project bulk upload UI + MP section)
- `Inventory/templates/Inventory/navigation.html` (label refresh)

**Deliverables:** Communities are first-class across all project types. Bulk imports work for all three project types. Old SHEP URL redirects so existing bookmarks survive.

**Effort:** 2 days (B.1 done; B.2 + B.3 next session).

---

## Phase H — Backup and Disaster Recovery (RUN IN PARALLEL WITH B)

**Goal:** Before any meaningful workflow weight rests on the system, ensure that data loss is recoverable. This phase runs alongside Phase B — neither blocks the other.

**Prerequisites:** Phase 0 deployed (so SQLite is at the persistent path).

**Tasks:**
- [ ] Create Azure Storage account in a *different* region from the App Service (e.g. North Europe if the app is in UK South). Generate SAS token or use managed identity for write access
- [ ] Add management command `Inventory/management/commands/backup_db.py`: copies `/home/site/data/db.sqlite3` to Blob Storage, named `backup-{timestamp}.sqlite3`, with 30-day retention
- [ ] Schedule the command to run nightly. On Azure App Service, options are: (a) WebJob with cron schedule; (b) GitHub Actions cron triggering a remote command; (c) external scheduler hitting an authenticated webhook. Pick whichever you can configure without portal access if needed today
- [ ] Add management command `Inventory/management/commands/export_documents.py`: zips all uploaded scans + generated memos + generated release letters and uploads to Blob Storage as a monthly snapshot
- [ ] Add a superuser-only "Download backup" view in Django admin → uploads the most recent backup to a temp location and serves as download
- [ ] Document the recovery procedure in `docs/DISASTER_RECOVERY.md`: how to spin up a new App Service from scratch, restore from the latest backup blob, and verify the system works
- [ ] Schedule a quarterly DR drill (calendar reminder). First drill should happen within 30 days of Phase H landing
- [ ] Until two successful drills are complete, paper files remain ground truth — document this as policy

**Deliverables:** Daily off-region backup. Tested recovery procedure. The system is no longer a single point of failure.

**Effort:** 1–2 days plus quarterly drill maintenance.

---

## Phase C — Material Request Flow (Project-Aware)

**Goal:** Two-step request flow: project selector → project-specific form. Auto-resolved consignee. Project-aware MaterialOrder records.

**Prerequisites:** Phase A complete (ProjectType + Consignee resolver exist).

### Phase C.1 — Two-step flow MVP (DONE this session)
- [x] Added `'STREET'` to `MaterialOrder.PROJECT_TYPE_CHOICES` so Streetlights orders can save (migration `0036_add_streetlights_project_type`)
- [x] `Inventory/constants.py` — `project_type_to_charfield()` mapper translates `ProjectType.code` (lowercase: `shep` / `cost_sharing` / `streetlights` / `special_other`) → existing CharField values (`SHEP` / `COST` / `STREET` / `SPEC`)
- [x] `Inventory/forms/request_flow.py` (NEW) — `ProjectSelectorForm` + `BaseProjectRequestForm` + 3 subclasses (`SHEPRequestForm`, `CostSharingRequestForm`, `StreetlightsRequestForm`) + form registry (`FORM_BY_PROJECT_CODE`) + `form_class_for_project()` helper
- [x] `Inventory/views/request_flow_views.py` (NEW) — `SelectProjectView` (Step 1) + `RequestMaterialForProjectView` (Step 2) + `resolve_consignee_for_community` (AJAX endpoint for live consignee preview)
- [x] Step 1 template `request_select_project.html` — three project-type cards (SHEP green / Cost Sharing teal / Streetlights amber), selectable, with consignee role hint per card
- [x] Step 2 template `request_material_v2.html` — material + quantity + warehouse + community fields plus project-specific section that renders only the relevant fields per project. Live consignee preview block updates via AJAX when community is chosen
- [x] On submit: form `save()` writes to `MaterialOrder` with `project_type` CharField mapped via constants, populates location fields from the chosen Community, auto-resolves consignee and writes to `consultant` or `contractor` field per role, captures project-specific extras into the `notes` field
- [x] URL routes: `/request-material/select/`, `/request-material/start/<project_code>/`, `/api/resolve-consignee/`
- [x] Navigation: Schedule dropdown's "Request material" now points at the new flow with a `new` badge; legacy single-page form preserved as a `↳ Legacy single-page form` link below

**Phase C.1 region-based consultant binding (DONE this session):**
- [x] Added `region` and `district` fields to `ProjectConsultant` model — drives SHEP consignee auto-resolution by region (mirroring the MP-by-constituency pattern)
- [x] Added `project_consultant` FK to `Community` for explicit consultant override (parallel to `member_of_parliament` FK)
- [x] Migration `0038_consultant_region_binding`
- [x] Updated `_resolve_consultant` in `consignee_resolver.py` with full fallback chain: explicit Community.project_consultant FK → district match → region match → legacy Project consultant → unresolved with clear reason
- [x] `ProjectConsultantAdmin` updated: region/district in list_display, list_filter, search_fields; new "Coverage" fieldset
- [x] `CommunityAdmin` updated: `project_consultant` in list_display + autocomplete_fields + Consignee Override fieldset
- [x] `CommunityForm` (`forms/admin.py`) updated: `project_consultant` field added with active-only queryset
- [x] Community form template: new "Consignee binding (SHEP)" fieldset shown only when SHEP is selected (JS toggle handles MP vs consultant section)
- [x] SHEP community bulk template now includes `consultant_name` column instead of `mp_name`/`constituency`; upload view validates and binds consultants by name
- [x] **New consultant bulk upload:** `download_consultant_template` + `upload_project_consultants` views with downloadable error CSV. URL routes `/download-consultant-template/` + `/upload-consultants/`
- [x] Bulk upload card added on community list page below MP section (green-themed to indicate SHEP affinity)

**Phase C.1 follow-ups DONE earlier this session:**
- [x] **Replaced the legacy `/request-material/` URL** with the two-step `SelectProjectView`. The `request_material` URL name now points to the new flow, so all `{% url 'request_material' %}` references across the codebase land on the project picker without template edits. Legacy single-page form preserved at `/request-material/legacy/` (named `request_material_legacy`) as an emergency fallback for one stable production cycle.
- [x] Removed the "Legacy single-page form" link from the Schedule navigation dropdown.
- [x] **Bulk uploads for material requests** added: `download_request_template?project=shep|cost_sharing|streetlights` generates per-project Excel templates with theme colors and instructions, including project-specific extra columns (package_number for SHEP, beneficiary_contribution for Cost Sharing, pole_height_m + lumen_rating + pole_type for Streetlights). `upload_requests` view validates per-row, looks up community within the chosen project, auto-resolves consignee, creates MaterialOrder rows in `transaction.atomic`, returns downloadable error CSV on failures.
- [x] Step 1 page (`/request-material/`) now has a **Bulk request material** card below the project selector — same Step 1 download / Step 2 upload pattern as community bulk imports.

**Deferred to Phase C.2 (later):**
- [ ] `MaterialOrderProfile` 1:1 sub-models per project type — currently project-specific fields are captured in `notes` rather than dedicated columns. Sub-models give cleaner reporting but aren't blocking the user-visible flow.
- [ ] Convert `MaterialOrder.project_type` from CharField → FK to `ProjectType`. Currently the new flow writes to the legacy CharField via the mapper, so the parallel old/new flows share storage. FK conversion is a clean-up later.
- [ ] Update existing list/detail views (`material_orders.html`, etc.) to show project-specific consignee label and the new pill badge.
- [ ] Tests for end-to-end flow per project type.

### Phase C.3 — Unify ProjectConsultant ↔ User (small follow-up)

**Goal:** Link the `ProjectConsultant` entity (the consignee on a release) to the Django `User` (the human who logs into the system) so consultants get notified at *request* time rather than only at *material assignment* time. Eliminates the parallel-rosters drift that would otherwise grow.

**Prerequisites:** Phase C.1 region-based consultant binding (done).

**Tasks:**
- [ ] Add `ProjectConsultant.user` nullable FK to `auth.User` — soft link, not a forced relationship
- [ ] Migration `0039_projectconsultant_user`
- [ ] Update `ProjectConsultantAdmin` to surface the user link via autocomplete; show in list_display so unlinked entries are visible
- [ ] Hook into `Inventory/signals.py`: when a SHEP `MaterialOrder` is created (post_save), if the resolved consignee has a linked user, create a `Notification` row addressed to that user (uses the existing `create_notification` helper)
- [ ] Surface notifications in the consultant's existing notification dashboard widget — already wired via `Inventory/context_processors.py` so no template change needed
- [ ] Update the consultant bulk-upload template + view to optionally accept a `username` column that auto-links to an existing User (skip if blank)
- [ ] Optional: management command `link_consultants_to_users` that auto-matches existing `Consultants`-group users to `ProjectConsultant` entries by name (case-insensitive), with a `--dry-run` flag to preview matches before committing

**Deliverables:**
- Consultant with a linked user → gets a notification at request time
- Consultant without a linked user → still resolvable as a paper-only consignee (Phase C.1 behaviour unchanged)
- One-off backfill to wire existing consultant-users to consultant entries

**Asymmetry note:** This unification is SHEP-only. MPs are external (Hon. Members of Parliament don't log into the IMS), so `MemberOfParliament` stays without a user link. Different real-world relationship, different model shape.

**Effort:** half a day. Slot it after Phase F lands so the notification work coexists with the rest of the audit-log/notification refactor in Phase G, OR ship it standalone as a small win if the request-time notifications are urgent.

**Deliverables shipped in C.1:**
- `/request-material/select/` lands on a clean three-card project picker
- Picking a card and continuing renders a tailored form with the right project-specific fields visible
- Live consignee preview block updates as soon as a community is selected
- Submit creates a real MaterialOrder with project_type stamped and consignee auto-populated
- Schedule dropdown surfaces the new flow as the primary action with the legacy form preserved as a fallback

**Files touched in C.1:**
- `Inventory/models/orders.py` (added STREET choice)
- `Inventory/migrations/0036_add_streetlights_project_type.py` (NEW)
- `Inventory/constants.py` (project_type_to_charfield + mapping table)
- `Inventory/forms/request_flow.py` (NEW, ~210 lines)
- `Inventory/views/request_flow_views.py` (NEW, ~120 lines)
- `Inventory/templates/Inventory/request_select_project.html` (NEW)
- `Inventory/templates/Inventory/request_material_v2.html` (NEW)
- `Inventory/urls.py` (3 new routes)
- `Inventory/templates/Inventory/includes/nav_schedule.html` (link updates)

**Effort actually used in C.1:** 1 session (MVP flow only; Profile sub-models and FK conversion deferred to C.2).

---

## Phase D — Release Letter Project-Awareness (DONE this session)

**Goal:** Release letters know what project they're for. Consignee renders correctly per project. Reporting can split by project type.

**Prerequisites:** Phase C complete.

**Tasks:**
- [x] Added `project_type` CharField to `ReleaseLetter` (mirrors MaterialOrder.PROJECT_TYPE_CHOICES, nullable for legacy rows). Future cleanup will convert this to FK alongside Phase C.2's MaterialOrder FK conversion.
- [x] Migration `0037_releaseletter_project_type` adds the field and backfills existing rows from their underlying MaterialOrders (NULL when orders span multiple project types — manually reviewable via admin filter).
- [x] `ReleaseLetterUploadView` POST now refuses to create a release letter when the underlying MaterialOrders span multiple project types — returns a clear validation error explaining the user should split into per-project batches.
- [x] On successful upload, `project_type` is stamped from the orders' shared project_type value.
- [x] `release_letter_detail.html` updated: project_type pill in the header (color-coded per project), consignee block below the status badge with the right label per project ("Consultant" for SHEP, "Hon. Member of Parliament" for Cost Sharing / Streetlights), pulling the value from the linked MaterialOrder's consultant or contractor field.
- [ ] List/filter UI for release letters by project type — deferred to Phase C.2 cleanup (along with material order list updates).

**Files touched in Phase D:**
- `Inventory/models/orders.py` (project_type field on ReleaseLetter)
- `Inventory/migrations/0037_releaseletter_project_type.py` (NEW)
- `Inventory/views/release_letter_views.py` (uniformity guard + stamp)
- `Inventory/templates/Inventory/release_letter_detail.html` (pill + consignee block)

**Effort actually used:** ~30 minutes (small phase as estimated).

**Original task list (kept here for context — all items above):**
- [x] ~~Add `project_type` FK to `ReleaseLetter` (derived from underlying MaterialOrders on creation)~~ → done as CharField for now; FK conversion in Phase C.2 cleanup
- [x] ~~Add `clean()` validation on `ReleaseLetter` rejecting cases where component MaterialOrders span different project_types~~ → done in the upload view rather than model.clean() because it's enforced at letter-creation time, not on every save
- [x] ~~Update `ReleaseLetterUploadView` to detect project_type from the request_code's MaterialOrders and stamp it on the new ReleaseLetter~~
- [ ] Update `release_letter_detail.html`: consignee label flips based on `release_letter.project_type.consignee_role`. Pill/badge in the header shows project type
- [ ] Add filter dropdowns to release-letter list view: filter by project type
- [ ] Update dashboard widgets to show release counts/values broken down by project type

**Deliverables:** Release letters carry their project context. Templates render the right consignee label. Reports can split.

**Effort:** 1 day.

---

## Phase F — Document Workflow (Generated Memo + Release Letter + Status Tracking)

**Goal:** System generates the approval memo and release letter as PDFs, linked by a `RE-yyyy-NNNN` code. Tracks status from draft through signed-and-released. Replaces the manual typing currently done.

**Prerequisites:** Phase D complete (release letter knows its project type, which drives memo language).

**Tasks:**
- [ ] Create `ReleaseEvent` model (or extend `ReleaseLetter`):
  - `code` (unique, format `RE-{year}-{4-digit-sequence}`)
  - `status` (choices: `draft`, `memo_generated`, `awaiting_signature`, `awaiting_scan_upload`, `approved`, `released`, `voided`, `reissued`)
  - `material_orders` (M2M back to MaterialOrder)
  - `memo_pdf` (FileField — generated)
  - `release_letter_pdf` (FileField — generated)
  - `signed_scan` (FileField — uploaded)
  - `scan_uploaded_by`, `scan_uploaded_at`, `scan_confirmed_by`, `scan_confirmed_at` (two-person review)
  - `created_at`, `updated_at`
- [ ] Sequence-allocator service that mints next `RE-yyyy-NNNN` atomically (handle concurrent allocation safely)
- [ ] PDF generator service `Inventory/services/pdf_generator.py`:
  - `generate_memo_pdf(release_event)` — produces memo matching the uploaded template structure: TO/FROM/DATE/SUBJECT block + 6 prose paragraphs + signature block. Pulls TO from policy ("Chief Director"), FROM from current user's role, DATE from now, SUBJECT from release_event subject_line. Body paragraphs templated per project type. Code `RE-2026-0142` printed in header right and footer right
  - `generate_release_letter_pdf(release_event)` — produces letter matching the uploaded template structure: addressee block (always MMU manager, Kpone-Tema) + bold subject line + 3 prose paragraphs + signature ("FOR: HON. MINISTER") + cc list. Body language varies by project type (SHEP refers to "stock of SHEP materials/equipment", Cost Sharing differs, Streetlights differs). Code `RE-2026-0142` printed prominently AND embedded in QR code in fixed corner
- [ ] If letterhead asset is available, render it on page 1; otherwise leave header space blank for pre-printed letterhead
- [ ] CC-list policy table per project type — make it a model, not hardcoded, so policy changes don't require code:
  - SHEP CC defaults: Hon. Minister, Hon. Deputy Minister, Director Power, Director Internal Audit, MD NEDCo (or ECG depending on region), Area Manager, beneficiary head
  - Cost Sharing CC defaults: Hon. Minister, Director Power, MP, beneficiary
  - Streetlights CC defaults: Hon. Minister, Director Power, MP, MMDCE, beneficiary
- [ ] State-machine view `Inventory/views/release_event_views.py`:
  - `generate_documents` → status `draft` → `memo_generated` (creates both PDFs)
  - `mark_sent_for_signature` → `memo_generated` → `awaiting_signature` (placeholder, real CD office is offline)
  - `upload_signed_scan` → `awaiting_signature` → `awaiting_scan_upload` (intermediate state if memo says "approved" verbally but scan delayed) OR straight to `awaiting_confirmation`
  - `confirm_scan` (second person) → `approved` (only if uploader ≠ confirmer)
  - `mark_released` → `released` (when materials physically leave MMU)
  - `void` and `reissue` flows for corrections
- [ ] Email reminder system: scheduled task scanning for events stuck in `awaiting_signature` or `awaiting_scan_upload`; sends reminder at 24h, 48h, 72h via M365
- [ ] Dashboard widget: "In-flight releases" — counts and oldest-age per stuck status
- [ ] QR validation on scan upload: extract QR from uploaded image (PyMuPDF or Pillow + pyzbar), decode payload, match against expected `RE-yyyy-NNNN`. Reject with clear error on mismatch
- [ ] OCR fallback for scans that don't have a clear QR (PyMuPDF + Tesseract): scan for the printed code text and match
- [ ] Tests: PDF generation produces non-empty bytes for each project type; QR encodes/decodes round-trip; state transitions enforce two-person rule; reminder cron fires

**Deliverables:** End-to-end document workflow. Memos and release letters generated automatically. Status tracked. Scans validated against the document they claim to belong to. Reminders chase stuck approvals.

**Effort:** 5–7 days. The biggest phase. Recommend breaking into sub-milestones (PDF generation done → status state-machine done → upload+QR validation done → reminders done).

---

## Phase G — Audit Log Integration (Done Concurrently With Phase F)

**Goal:** Every state transition writes an audit-log entry. Retroactively wire on existing privileged actions.

**Prerequisites:** None — but most useful when Phase F's state transitions exist to be logged.

**Tasks:**
- [ ] Audit `audit_log` app's actual schema (we know the model exists; need to confirm the field names so calls type-check). Look at `Inventory/views/dashboard_views.py:467-470` and `user_views.py:322-326` for the existing query patterns
- [ ] Add `AuditLog.objects.create(...)` calls on:
  - Phase F state transitions (every status change on `ReleaseEvent`)
  - Superuser auto-promotion in `accounts/views.py:ms_callback`
  - Group membership changes (admin actions)
  - MaterialOrder creation, approval, processing
  - ReleaseLetter generation (Phase F handles this)
  - BOQ over-issuance approvals
  - User deactivation
  - Bulk imports (one summary log per import + line-level errors written separately)
- [ ] Add a "Recent activity" admin view filtered by user / by object — useful for incident review
- [ ] Document the audit-log retention policy (probably 7 years for government procurement, but check with PPA)
- [ ] Tests: each privileged action produces exactly one log row with correct actor, action, target

**Deliverables:** Forensic trail exists. Phase-2 finding from the security audit closed.

**Effort:** 2 days woven through Phase F.

---

## Phase F — Release-side Document Workflow

### Phase F.1 — Signatory model + system-generated memo + release letter PDFs (DONE this session)
- [x] `Signatory` model (NEW, `Inventory/models/signatory.py`): name, title, active, default-for-release-memo / release-letter / payment-memo flags, optional `signs_for` (used for "FOR: HON. MINISTER" line). Class-methods `for_release_memo()`, `for_release_letter()`, `for_payment_memo()` return the right active row at render time.
- [x] Seeded with Ing. Sulemana Abubakari (Ag. Director, Power — defaults for release-memo + payment-memo) and Solomon Adjetey Sowah (Chief Director — defaults for release-letter, signs FOR: HON. MINISTER).
- [x] Added workflow fields to `ReleaseLetter`: `code` (RE-yyyy-NNNN, unique, auto-allocated by `next_release_code` service), `workflow_status` (state-machine with 8 states), `memo_pdf` + `letter_pdf` (FileFields for the generated PDFs, separate from `pdf_file` which remains the legacy signed-scan target), `documents_generated_at/by`, `scan_uploaded_at`, `scan_confirmed_by/at` (two-person review hooks for Phase F.2).
- [x] Migration `0039_signatory_and_release_workflow_fields` creates the table, seeds signatories, and adds the ReleaseLetter fields. All ReleaseLetter additions are nullable — no breakage to existing rows.
- [x] `Inventory/services/release_code.py` — atomic release-code allocator (`next_release_code()`). Year-rolling sequence. Postgres-ready (uses `SELECT FOR UPDATE` where supported); SQLite gets the same guarantee via the `transaction.atomic` wrapper since SQLite serializes writes.
- [x] `Inventory/services/pdf_generator.py` — `generate_release_memo()` and `generate_release_letter()` using ReportLab. Memo mirrors the structure of REQUEST FOR A REPLACEMENT OF TRANSFORMER (TO/FROM/DATE/SUBJECT block + body + signature). Letter mirrors the MINISTRY OF EDUCATION format (addressee block + bold subject + body + signature block with FOR: HON. MINISTER + cc list). QR code top-right on the letter encoding the release code so scan uploads can be matched. Letterhead area is reserved as plain text for pre-printed paper; can swap to drawImage() when an asset is available.
- [x] `Inventory/views/release_document_views.py` — `ReleaseLetterDetailView` (a missing piece — the template existed but the URL was never wired) + `GenerateReleaseDocumentsView` (POST endpoint that allocates code, generates both PDFs, advances workflow_status). Gated to Schedule Officers / Management / superusers.
- [x] URL routes: `/release-letters/<pk>/` (detail) + `/release-letters/<pk>/generate-documents/` (generate action).
- [x] Detail template updated: project pill + RE code badge + workflow status badge in the header; **Generate memo & letter** / **Regenerate documents** button surfacing the action; download links for the generated memo, generated letter, and uploaded signed scan as separate buttons so users know which is which.
- [x] Admin: `SignatoryAdmin` registered so leadership changes are a database edit, not a code deploy.

**Deliverables shipped:**
- One-click generation of approval memo PDF + release letter PDF from a ReleaseLetter row
- RE-yyyy-NNNN code prominently displayed and embedded in the letter's QR
- Workflow status advances to `memo_generated` on first generation
- Idempotent: regenerating doesn't re-mint the code, just refreshes the PDFs

### Phase F.2 — Scan upload + two-person confirmation + status state machine (DONE this session)
- [x] **QR code now also embedded in the memo PDF** (was previously letter-only), so both documents carry the validation payload
- [x] **`UploadSignedScanView`** — POST endpoint that saves the uploaded scan to `pdf_file`, decodes any QR via `pyzbar` (+ `pdf2image` for PDF rasterisation), compares against `release_letter.code`, advances workflow to `awaiting_scan_upload`. Mismatches/missing QRs are reported as warnings rather than fatal errors so users can still progress with imperfect scans
- [x] **`ConfirmSignedScanView`** — POST endpoint that enforces two-person review (`uploaded_by_id != request.user.id` for non-superusers), advances workflow to `approved`, stamps `scan_confirmed_by/at`
- [x] **`MarkReleasedView`** — POST endpoint for the terminal state transition when materials physically leave MMU
- [x] **Workflow Actions card on the detail page** — surfaces the next-step UI based on `workflow_status`: upload form when `memo_generated`, confirm button when `awaiting_scan_upload` (gated to non-uploader), mark-released when `approved`
- [x] **Re-upload flow** for cases where the wrong scan was uploaded or QR decode failed
- [x] **URL routes:** `/release-letters/<pk>/upload-scan/`, `/release-letters/<pk>/confirm-scan/`, `/release-letters/<pk>/mark-released/`
- [x] **`requirements.txt`** updated with `pyzbar` + `pdf2image` for QR decode; `azure-storage-blob` for Phase H; fixed the long-standing `pandas==3.0.0` typo to `pandas==2.2.3`

**Still deferred (Phase F.3, lower priority):**
- [ ] Email reminders at 24h / 48h / 72h on stuck workflow states
- [ ] Dashboard widget for in-flight releases by status with age
- [ ] OCR fallback when QR decode fails (Tesseract → printed-code text match)
- [ ] Void / reissue flows for corrections

---

## Phase F.5 — Mandatory transport on Complete (DONE this session)

**Goal:** Close the notification gap — when a Storekeeper marks a MaterialOrder as Completed, auto-create a placeholder `MaterialTransport` row in `Awaiting Transporter` status. Transport Officers / Management get notified via the existing transport-creation notification path.

- [x] Added `Awaiting Transporter` to `MaterialTransport.STATUS_CHOICES` (migration `0040_transport_awaiting_choice`)
- [x] Signal `auto_create_transport_on_complete` in `Inventory/signals.py` — fires on `MaterialOrder.post_save` when `_status_changed` is True and new status is `Completed`. Skips if a transport row already exists for the order (idempotent).
- [x] Notes captured on the auto-created row: "Auto-created on order completion. Awaiting Transport Officer to assign transporter + vehicle."

---

## Phase G partial — Audit log writes on document workflow transitions (DONE this session)

**Goal:** Wire the dormant `audit_log` app into the new Phase F flows so there's a real forensic trail.

- [x] `Inventory/services/audit.py` (NEW) — single-call `audit(user, target, action, message)` helper. Failures swallowed and logged so audit writes never break user-facing transactions.
- [x] Audit calls added on: `release.documents_generated`, `release.scan_uploaded`, `release.scan_confirmed`, `release.marked_released`, `release.letter_created`, `auth.superuser_auto_promoted`
- [x] Verified writing: smoke test confirms audit_log row count increments correctly

**Deferred:** retroactive audit calls on legacy actions (group changes, material order approvals, BOQ over-issuance approvals, bulk imports, user deactivation). Bundle with Phase G full sweep later.

---

## Phase H — Backups + DR (DONE this session)

- [x] **`backup_db` management command** (`Inventory/management/commands/backup_db.py`) — copies `/home/site/data/db.sqlite3` to Azure Blob Storage in a configurable container, prunes blobs older than retention. No-op (logs warning, exits 0) when `AZURE_BACKUP_CONNECTION_STRING` is not set, so it can be scheduled before credentials are configured.
- [x] **`DISASTER_RECOVERY.md`** at the repo root — one-time setup guide (different-region storage account, env vars, scheduling options) + soft-restore procedure + hard-restore procedure + quarterly drill log table + caveats around media files / M365 tokens / replication lag
- [x] **`azure-storage-blob>=12.19.0`** added to requirements.txt

**Pending operational setup (requires Azure portal access):**
- [ ] Provision storage account in North Europe with `moen-ims-backups` container
- [ ] Set `AZURE_BACKUP_CONNECTION_STRING` in App Service Application Settings
- [ ] Schedule daily `manage.py backup_db` via WebJob or GitHub Actions cron
- [ ] Run first DR drill within 30 days of go-live

**Files touched in F.1:**
- `Inventory/models/signatory.py` (NEW)
- `Inventory/models/__init__.py` (exports Signatory)
- `Inventory/models/orders.py` (ReleaseLetter workflow fields)
- `Inventory/migrations/0039_signatory_and_release_workflow_fields.py` (NEW)
- `Inventory/services/release_code.py` (NEW)
- `Inventory/services/pdf_generator.py` (NEW, ~330 lines)
- `Inventory/views/release_document_views.py` (NEW)
- `Inventory/urls.py` (2 new routes)
- `Inventory/templates/Inventory/release_letter_detail.html` (RE code + workflow badges, generation button, separate download links)
- `Inventory/admin.py` (SignatoryAdmin)

**Effort actually used:** 1 session (F.1 only; F.2 scan/two-person/reminders/dashboard is the next round).

---

## Phase I — Supply / Invoicing Workflow (NEW)

**Goal:** Mirror Phase F's release-side document workflow on the supply side. Storekeepers log deliveries with photo proof, contract balances auto-decrement, stock auto-increments, schedule officers process supplier invoices semi-automatically, system generates payment-approval memos with reconciliation tables, scanned signed memos confirm completion. Replaces the current tally-card + Excel manual reconciliation workflow.

**Prerequisites:** Phase F's PDF generator + QR code + status state-machine + scan upload infrastructure. Phase G's audit log writes wired in concurrently.

**Models to add or extend:**
- `SupplyDelivery` (new) — links to a SupplyContract, captures: item, quantity, arrival date, supplier name, supplier-issued invoice number, supplier-issued invoice date, supplier cover-letter date (when paperwork was officially submitted), recorded_by (Storekeeper), photos (FK to gallery), notes. Logging a delivery atomically (a) decrements `SupplyContract.outstanding_quantity` for that item, (b) increments `InventoryItem.quantity` by the delivered amount.
- `SupplyDeliveryPhoto` (new) — FK to SupplyDelivery, FileField for image, uploaded_at, uploaded_by. Hard gate: at least one photo OR a non-empty `no_photo_reason` on the parent delivery.
- `SupplierInvoice` (existing — extend) — add: `internal_code` (`INV-yyyy-NNNN` format, system-generated, unique), `supplier_invoice_no` (CharField, supplier-provided), `supplier_invoice_date`, `cover_letter_date`, `withholding_tax_percent`, `withholding_tax_amount`, `amount_payable_net`, `amount_in_words`, `lc_bank`, `lc_reference`, `lc_amount`, `sra_reference` (Stores Receipt Advice ref), `acceptance_certificate_reference`, `status` (workflow state), `prepared_by`, `checked_by`, `approved_by`, `approval_signed_at`, `approval_scan` (FileField).
- `PaymentApprovalEvent` (new, parallel to release-side `ReleaseEvent`) — links to a SupplierInvoice, carries the workflow state machine (`draft → memo_generated → awaiting_signature → awaiting_scan_upload → approved → paid → voided/reissued`), generated memo PDF, signed scan upload, two-person review (uploader ≠ confirmer), audit log per state transition.
- `Signatory` (new) — small lookup table for `name`, `title`, `role` (e.g. "Ag. Director, Power"), `is_default_for_release_memo`, `is_default_for_payment_memo`, `active`. Pre-seeded with Ing. Sulemana Abubakari as the default for both release and payment memos. Configurable via admin so the next leadership change is a database update, not a code deploy.

**Workflow:**
1. **Schedule Officer creates SupplyContract.** Existing model. Captures supplier, items, agreed quantities, unit prices, period.
2. **Storekeeper logs SupplyDelivery on truck arrival.** Selects contract, item, enters delivered quantity, attaches at least one photo (or fills "no photo reason" override). On save, contract balance decrements, inventory increments.
3. **System creates a SupplierInvoice** automatically when the delivery is logged (1:1 cardinality per your answer). Internal code `INV-yyyy-NNNN` allocated.
4. **Schedule Officer reviews and finalizes the invoice.** Adds withholding tax %, LC details, SRA reference, Acceptance Certificate reference, amount in words. Marks ready for payment approval.
5. **System generates the payment-approval memo.** Replicates the structure of `PROMAN INVOICE.docx`: MEMORANDUM header, TO/THRU'/FROM/SUBJECT/DATE block, body paragraphs referencing contract details, single-row item table (S/N, Description, Unit, Q'ty, Unit Price, Total Price), withholding tax row, Amount Payable row, amount in words, LC clause citation, signatory line for Ing. Sulemana Abubakari (Ag. Director, Power). Plus an attached **reconciliation/tracker table** as a second page showing all deliveries against the contract with running totals and balance, with three signature blocks: Prepared by / Checked by / Approved by.
6. **System enforces three-way separation** on the tracker: the user who Prepared cannot also be the Approver. Checker can be either.
7. **Memo is QR-coded** with `INV-yyyy-NNNN`. Same validation flow as releases.
8. **Print → wet signature by Ag. Director Power → scan upload → status = approved.** Two-person upload (uploader ≠ confirmer).
9. **Status transitions to `paid`** when finance confirms (manual flag — out of system scope; we just record the timestamp and who flagged it).
10. **Audit log writes on every transition.** Phase G covers this.

**Schedule Officer permission set:**
- Create SupplyContract (gated to Schedule Officers + above)
- View deliveries (read-only across all contracts they manage)
- Generate payment-approval memo + tracker
- Upload signed scan + confirm approval (with two-person separation)
- Mark invoice as paid

**Storekeeper permission set:**
- Log SupplyDelivery (the only mutation they need)
- View their own delivery history

**Tasks:**
- [ ] Wait on user confirmation of recommended approach (this section)
- [ ] Add `Signatory` model with seed data: Ing. Sulemana Abubakari, Ag. Director, Power
- [ ] Add `SupplyDelivery` and `SupplyDeliveryPhoto` models with stock auto-increment + contract balance auto-decrement on save (transactionally)
- [ ] Extend `SupplierInvoice` with the additional fields listed above; data migration for existing rows
- [ ] Add `PaymentApprovalEvent` model + state machine
- [ ] Implement the storekeeper SupplyDelivery form (with photo upload, optional override reason)
- [ ] Implement the Schedule Officer SupplierInvoice review form
- [ ] Implement the payment-approval memo PDF generator following PROMAN INVOICE.docx structure
- [ ] Implement the reconciliation tracker page (second page of the memo PDF, with three signature blocks)
- [ ] QR encode + scan upload + two-person review (reuse Phase F infrastructure)
- [ ] Dashboard widgets: deliveries by storekeeper, invoices by status, contracts approaching balance zero, photo-missing flag
- [ ] Audit log writes (Phase G)
- [ ] Tests: stock atomicity under concurrent deliveries, three-way separation enforcement, PDF round-trip

**Effort:** 5–7 days, after Phase F lands. Reuses Phase F's PDF/QR/scan infrastructure heavily so the marginal cost is mostly the new models, the tracker page, and the storekeeper photo flow.

**Open items still needed from user:**
- MP roster for bulk import (deferred — user will provide later)
- Confirmation that the photo hard-gate-with-override approach is acceptable (defaulting to yes unless told otherwise)

---

## Phase E — Per-Project Permissions (Deferred / Optional)

**Goal:** Different users can be restricted to specific project types (e.g. a "SHEP Officer" can't view Streetlights releases).

**Prerequisites:** All previous phases.

**Tasks:**
- [ ] Decide if this is actually wanted. Today the existing groups (Store Officers, Stores Management, etc.) are role-based, not project-based. Adding project-based restrictions roughly doubles the group count and requires permission logic refactoring
- [ ] If yes: add `accessible_project_types` M2M from User to ProjectType. Update middleware to gate views accordingly
- [ ] If no: skip this phase

**Deliverables:** Conditional. Skip unless you have a stated need.

**Effort:** 2 days if pursued. Recommend skipping for v1.

---

## Critical Path & Dependencies

```
Phase 0 (push existing fixes) — must complete first
        │
        ├──► Phase A (foundation)              [DONE — code complete]
        │           │
        │           ├──► Phase B (community refactor)    [B.1, B.2 DONE; B.3 pending]
        │           │
        │           └──► Phase C (request flow)
        │                       │
        │                       └──► Phase D (release letter project-aware)
        │                                   │
        │                                   ├──► Phase F (release-side doc workflow)
        │                                   │           + Phase G (audit log) concurrent
        │                                   │
        │                                   └──► Phase I (supply / invoicing)  ← NEW
        │                                               (reuses F's PDF/QR/scan infra,
        │                                                + audit log via G)
        │
        └──► Phase H (backup + DR) — runs in parallel with B, must finish before F/I go live
```

Total wall-clock estimate if executed end-to-end without parallelism: **3.5–4 weeks** of focused work (Phase I adds ~5–7 days on top of the original plan).
With parallelism: **~3 weeks** to end of Phases F + I.
Phase E (per-project permissions): deferred indefinitely unless the need is concrete.

---

## What Will Be Done When Phases 0–H Are Complete

A complete checklist of capability you'll have at the end (use this as the acceptance criteria for "done"):

- [ ] No more data loss on deploy; SQLite persists across pushes
- [ ] Migrations run automatically on container startup (with the option to switch to a proper startup command later)
- [ ] DEBUG is False in production; security cookies, HSTS, SSL redirect all active
- [ ] Daily off-region backups proven via at least one DR drill
- [ ] One canonical `ProjectType` model; legacy enum mismatches resolved
- [ ] `MemberOfParliament` and `ProjectConsultant` are real entities, not free-text fields
- [ ] Communities are project-agnostic; "Add Community" replaces "Add SHEP Community"
- [ ] Three bulk-import templates (SHEP, Cost Sharing, Streetlights) with downloadable per-row error report
- [ ] Material requests start with a project selector; fields adapt per project
- [ ] Consignee is auto-resolved (Consultant for SHEP, MP for Cost Sharing & Streetlights), no longer free text
- [ ] Release letters know their project type; templates render the right consignee label
- [ ] Approval memo and release letter generated automatically as PDFs from MaterialOrder data
- [ ] Both documents share a code (`RE-yyyy-NNNN`) printed prominently; release letter has matching QR
- [ ] Scan upload validates against the QR / printed code; wrong-document uploads rejected
- [ ] Two-person review on scan upload (uploader + confirmer must differ)
- [ ] Status workflow tracks each release through draft → generated → awaiting signature → awaiting scan → approved → released
- [ ] Email reminders fire at 24/48/72h on stuck approvals
- [ ] Dashboard widget shows in-flight releases by status with age
- [ ] Audit log writes on every privileged action; security audit Phase-2 finding closed
- [ ] Paper files retained as ground truth until at least two successful DR drills
- [ ] No regression in existing flows (test_security.py and existing test suite still pass)

---

## Things Still Outside This Plan (Track Separately)

- Postgres migration (Phase 2 of security audit) — schedule after portal access returns
- Sentry DSN setup (Phase 1 of security audit) — quick win, do during Phase 0 push
- M365 client secret rotation (Phase 1 of security audit) — do during Phase 0 push
- `pip-audit` GitHub Actions workflow (Phase 2 of security audit) — quick win
- File-upload MIME validation (Phase 2 of security audit) — bundle with Phase B's bulk-import work
- Rate limiting on auth and uploads (Phase 2 of security audit) — bundle with Phase B
- Signature verification via ML (deferred — too high a false-negative rate for current scale)
- Per-project permissions (Phase E) — deferred unless explicitly needed
- Refactor of god-files `order_views.py`, `dashboard_views.py`, `data_views.py` (Phase 3 of security audit)

---

## Document Trail for This Plan

- Security audit document: `SECURITY_AUDIT_2026-05-07.md`
- Mockup spec: rendered inline in chat session 2026-05-08
- Memo template reference: `REQUEST FOR A REPLACEMENT OF TRANSFORMER THE HEAD OF STATE AWARD SCHEME.docx`
- Release letter template reference: `RELEASE LETTER MINISTRY OF EDUCATION.docx`
