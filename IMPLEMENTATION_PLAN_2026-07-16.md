# Gap-Closure Implementation Plan
**Date:** 2026-07-16 (v2 — replaces the restructure plan; no app splits, prod is already Postgres)
**Goal:** Close the workflow and analytics gaps found in the E2E review + audit. Deletion and small diffs over rearchitecture.
**Gate for every phase:** `python manage.py test Inventory` green, including `test_end_to_end_workflow`.

---

## Phase 0 — Dead weight (DONE 2026-07-16)

Deleted: `report_utils/` duplicate package (796 lines), 3 debug endpoints (~200 lines, one created DB rows on GET), hot-path `cache.clear()` + debug logging (~45 lines), duplicate import, 57 stale root docs. `transporter_views.py` 2,549 → 2,364 lines.

Still open from the audit, folded into phases below: one processing path (Ph 3), `save()` status machine (Ph 3), waybill PDF relocation (Ph 6), seed commands (Ph 6).

---

## Phase 1 — Unblock the delivery loop (DONE 2026-07-16)

The back half of the workflow is broken in prod: receipts are superuser-only and there's a "Delivered" back door that skips the books. Everything downstream (BoQ drawdown, map completion, material-delivery rate) starves on these two.

1. **Let consultants log receipts.** Add `test_func` (consultant group or superuser) to `ConsultantDeliveriesView` and `SiteReceiptCreateView` — they currently inherit `SuperuserOnlyMixin`'s 404. `[views/consultant_views.py:15,33]`
2. **Close the Delivered back door.** `update_transport_status` stops accepting `'Delivered'` — a SiteReceipt becomes the only path to Delivered, so BoQ posting can't be skipped. Keep 'In Transit', 'Loading', etc. `[transporter_views.py]`
3. **Tests:** extend the E2E test — consultant logs the receipt over HTTP (not model-level); posting `'Delivered'` to the status endpoint returns an error.

**Done when:** a consultant account can complete Stage 6 in the browser; no transport reaches Delivered without a receipt row.

## Phase 2 — Guard the headline number (DONE 2026-07-17, + tests.yml CI gate)

`site_progress_edit` is `@login_required` only: any account can set any site to Commissioned/100% and move the national access rate.

1. `user_passes_test`: consultants + management + superuser. `[views/site_progress_views.py:170]`
2. One test: storekeeper POST → 403/404.

**Done when:** only consultant/management accounts can write progress.

## Phase 3 — One processing path, one status machine (DONE 2026-07-17)

Root cause under three separate bugs this month.

1. **Extract `process_quantity(order, qty, user)`** into `services/order_flow.py`; both `order_views` (~L845 block) and `stores_management_views.process_order_partial` call it. The signed-letter guard moves inside — currently the Store Hub path skips it and can draw down stock without countersigned paperwork.
2. **Defuse `MaterialOrder.save()`:** stop recomputing `status` on every save (it silently reverts transitions — the In-Transit-vs-Completed fight). Status changes happen only in the service function. Keep request-code generation.
3. **Tests:** guard applies on both endpoints; a status set explicitly survives an unrelated `save()`.

**Done when:** grep finds one place that mutates `processed_quantity`, and `save()` no longer touches `status`.

## Phase 4 — Feed the map from the community registry (DONE 2026-07-17)

Revised per direction: the map populates via the community progress page's
spine (the Community registry), not via BoQ uploads.

1. **Community → site sync** (`services/map_sync.py` + post_save signal):
   every active Community gets a ProjectSite under an umbrella programme
   Project (PRG-SHEP, …). Existing sites are reused, never duplicated.
   Completion then flows: consultant records progress (Site Progress page)
   → community progress page shows it → Ghana map access rate moves;
   deliveries flip the same site via the existing BoQ sync.
2. **Backfill:** `python manage.py sync_community_sites` (run once on prod).
3. **Mismatch panel** on the community progress page: BoQ communities
   missing from the registry — the silent string-match failures.
   <!-- ponytail: report first; Community FKs only if typos keep hurting -->

**Done when:** registering a community makes it appear on the map with no
manual step; the mismatch panel is empty on clean data.

## Phase 5 — Role cleanup (DONE 2026-07-17; status-choice removal → Phase 6)

1. **Groups merged:** migration `0068_merge_role_group_aliases` folds all
   store-officer aliases into 'Store Officers' and 'Consultant' into
   'Consultants'. The singular/plural checks in code now accept all aliases
   (`Roles.STORE_OPERATION_ALIASES`; `is_consultant` takes both). Deleted
   unimported `utils_DEPRECATED.py`.
2. **Dead status strings** removed from the transporter filter
   ('Ready for Pickup', 'Fulfilled'). Removing them from
   `MaterialOrder.STATUS_CHOICES` needs a `makemigrations` pass — moved to
   the Phase 6 table alongside the 'Pending' decision.

## Phase 6 — Decisions made & implemented (2026-07-17, NOT yet test-run)

All six answered by the user and coded — see `HANDOFF_2026-07-17.md` for
run instructions and risk notes.

| # | Decision | Implementation |
|---|---|---|
| 1 | Delete dead statuses ('Pending', 'Ready for Pickup') | model + migration 0069 |
| 2 | Project status derives from sites | `Project.derived_status` + templates |
| 3 | Meter formula is the real methodology — wired as map headline | `map_views` uses `compute_access_rate()`, consultant fallback if no config |
| 4 | Show all three progress signals | headline + `consultant_rate_pct` + material rate in payload |
| 5 | Off-inventory releases warn-but-allow, surfaced in UI | `order.processing_warning` in both endpoints' responses |
| 6 | Waybill PDF → `services/waybill_pdf.py`; seed_simulation deleted | done, urls unchanged via re-export |

---

## Order & effort

| Phase | Effort | Closes |
|---|---|---|
| 1 — delivery loop | ½ day | workflow #1, #2 (data starvation) |
| 2 — progress guard | 1–2 h | analytics #3 (headline integrity) |
| 3 — one path | 1–2 days | workflow #3, #6 / audit #5, #11 (bug factory) |
| 4 — feed the map | 1 day | analytics #1, #2 (empty map) |
| 5 — statuses & roles | 1 day | workflow #4, #5 |
| 6 — decisions | — | analytics #4, #5 + audit leftovers |

**Total: ~4–5 working days**, each phase deployable alone, in impact order — Phase 1 alone un-starves the map without touching the map code.
