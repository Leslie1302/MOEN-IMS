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

## Phase 3 — One processing path, one status machine (1–2 days)

Root cause under three separate bugs this month.

1. **Extract `process_quantity(order, qty, user)`** into `services/order_flow.py`; both `order_views` (~L845 block) and `stores_management_views.process_order_partial` call it. The signed-letter guard moves inside — currently the Store Hub path skips it and can draw down stock without countersigned paperwork.
2. **Defuse `MaterialOrder.save()`:** stop recomputing `status` on every save (it silently reverts transitions — the In-Transit-vs-Completed fight). Status changes happen only in the service function. Keep request-code generation.
3. **Tests:** guard applies on both endpoints; a status set explicitly survives an unrelated `save()`.

**Done when:** grep finds one place that mutates `processed_quantity`, and `save()` no longer touches `status`.

## Phase 4 — Feed the map (1 day)

The map only shows hand-registered sites, joined to deliveries by string-matching community names.

1. **Auto-create sites:** BoQ upload does `ProjectSite.objects.get_or_create` (community+project) for each new community; one management command backfills from existing BoQ rows.
2. **Mismatch report:** panel on the release-letter tracking dashboard listing BoQ communities with no matching ProjectSite (and vice versa) — makes silent string-match failures visible instead of zero-ing the map. <!-- ponytail: report first; SHEPCommunity FKs only if typos keep hurting after this -->

**Done when:** uploading a BoQ for a new community makes it appear on the map with no manual step; the mismatch panel is empty on seeded data.

## Phase 5 — State-machine and role cleanup (1 day)

1. **Dead statuses:** nothing ever sets `'Pending'` or `'Ready for Pickup'`, and `'Fulfilled'` is filtered on but isn't a valid choice. Decide: delete the choices (recommended) or wire a real Draft→Pending submit step. Default: delete.
2. **Merge store groups:** data migration folds `Store Officer` / `Store Officers` / `Storekeeper` members into one group; all checks route through `Inventory.utils.Roles`. Kills the "assignable but can't see their queue" trap.

**Done when:** every status in `STATUS_CHOICES` is reachable, and `grep "name='Store"` outside utils returns nothing.

## Phase 6 — Parked decisions (no code until decided)

| Item | Options | Default recommendation |
|---|---|---|
| `Project.status` never rolls up | derive from sites / drop from dashboards | derive as a read-only property |
| Three progress signals (BoQ, consultant %, meters) | pick one / show divergence | show all three on site drill-down; divergence = data-quality alarm |
| Unused meter formula (`compute_access_rate`) | wire it / delete it | delete; git remembers, EC decision can resurrect it |
| Waybill PDF code (~1,100 lines in a views file) | move to `services/` | move during next waybill change, not before |
| Seed commands (1,133 lines, unreferenced) | keep one / delete | keep `seed_demo_data`, delete `seed_simulation` |

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
