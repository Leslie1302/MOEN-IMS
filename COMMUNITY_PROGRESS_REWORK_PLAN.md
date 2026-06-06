# Community Progress & Status Rework — Implementation Plan

_MOEN-IMS, June 2026. Owner: Leslie Nii Adjei._

## Problem

1. **Site progress is too coarse.** `ProjectSite` stores a single `poles_erected`, one `conductor_laid_m`, and transformer/meter counts. It cannot express HT vs LV, nor the pole lifecycle (erected → dressed → strung), so the community breakdown *relabels* coarse fields (e.g. `transformers_installed` shown as "Transformers **dressed**") and carries a footnote admitting poles/conductor are "recorded combined (not split by HT/LV)".
2. **Community progress is not live.** The **Expand** action is a full-page `<a href>`; and the community list's completion bar is computed purely from BoQ (`quantity_received / contract_quantity`), so updating a consultant's site progress never moves it.

## Decisions (locked)

- **Granularity:** capture HT *and/or* LV poles **erected**, **dressed**, **strung**; conductor used for stringing (per class); transformers installed & commissioned; meters 1-phase & 3-phase.
- **Completion model:** **5 stages × 20%**, sequential — **HT → LV → Transformer → Meters → Commissioning** — each = recorded works ÷ planned target (Design B, ratio-based). The manual `progress_percent` input is **removed**; the percent is derived.
- **One community = one site** (1:1), so targets, works counters, and the derived percent all live at the same grain — no roll-up/apportionment.
- **Material arrival order is irrelevant** to completion: materials may be received out of sequence, but works are credited strictly in the 5-stage order.
- **HT/LV source of truth:** an explicit `voltage_class` on BoQ (heuristic prefill + manual override), replacing the keyword-only guess.
- **Targets come from BoQ once, then decouple:** BoQ contract quantities seed the planned targets via a single, human-confirmed pull. After that, BoQ and the progress tracker never read or write each other again.

## How BoQ and the progress tracker stay separate

**Snapshot by value, never a live binding.** Targets are copied out of BoQ into the community's own numeric columns at setup; completion math reads only those columns. Consequences:

- BoQ revisions, over-issuance, and the justification flow **cannot** move a completion denominator — the baseline is frozen scope, not a live `quantity_received`.
- The **only** contact point is an explicit **"Pull targets from BoQ"** action with a per-bucket **diff preview**. No signals, no auto-sync, no write-back.
- Provenance is stamped (`targets_source`, `targets_pulled_at`, `targets_pulled_by`, `targets_locked`) so the pull is auditable without being coupled.
- Targets remain **manually editable** afterward (real scope sometimes diverges from contract).

## The five stages

| Stage (20% each) | Numerator (site works) | Denominator (frozen target) |
|---|---|---|
| 1. HT works | mean(HT erected, dressed, strung) | `planned_ht_poles` |
| 2. LV works | mean(LV erected, dressed, strung) | `planned_lv_poles` |
| 3. Transformer | `transformers_installed` | `planned_transformers` |
| 4. Meters | `meters_1ph + meters_3ph` | `planned_connections` |
| 5. Commissioning | `transformers_commissioned` | `planned_transformers` |

Each stage contribution is `0.20 × min(1, numerator ÷ denominator)`; a stage with a zero/blank target contributes 0 and is shown as "no target set". Conductor-used is recorded for audit + a stringing sanity check but is **not** a denominator.

## Datasets affected and how

| Dataset | Change |
|---|---|
| **`BillOfQuantity`** | **+`voltage_class`** (`HT/LV/XFMR/METER/OTHER`, blank default). Backfilled from the existing heuristic. Read **only** by the one-time pull. |
| **`Community`** | **+ planned-target snapshot**: `planned_ht_poles`, `planned_lv_poles`, `planned_transformers`, `planned_connections`, `planned_ht_conductor_m`, `planned_lv_conductor_m`. **+ provenance**: `targets_source`, `targets_pulled_at`, `targets_pulled_by`, `targets_locked`. |
| **`ProjectSite`** | **+ granular works counters**: `ht_poles_erected/dressed/strung`, `lv_poles_erected/dressed/strung`, `ht_conductor_strung_m`, `lv_conductor_strung_m`. `progress_percent` becomes **derived-on-save** (column kept so the Ghana map keeps reading it). Legacy `poles_erected`/`conductor_laid_m` retained and backfilled into the LV lifecycle. |
| **`SiteProgressForm`** | Grouped HT/LV lifecycle inputs + conductor used; validation (`strung ≤ dressed ≤ erected`, `commissioned ≤ installed`); manual percent removed. |
| **Services** | `pull_targets_from_boq(community)` (diff preview + apply + provenance); `compute_site_completion(site)` (5-stage math, returns percent + per-stage breakdown). |
| **Views/Templates** (Phase 2–3) | `site_progress_edit` sets derived percent on save; `_site_progress_for_community` sums new counters with correct labels; the breakdown shows real HT/LV lifecycle; **Expand** becomes an inline AJAX accordion refreshing live. |
| **`MeterInstallation`** | Unchanged — meter-delta sync to the access rate keeps working. |
| **`seed_simulation`** | Populates new counters and pulls targets so the simulation exercises the new completion math. |

## Phasing

- **Phase 1 (this change):** model fields + migrations/backfill + the two services + reworked Site Progress form + derived percent on save + re-seed.
- **Phase 2:** breakdown/list template rework — real HT/LV lifecycle, correct labels, works-aware completion, the "Pull from BoQ" UI with diff preview.
- **Phase 3:** real-time — inline AJAX **Expand** accordion + AJAX site-progress save so an open community refreshes immediately.

## Notes / open follow-ups

- `voltage_class` distinguishes voltage; the pull separates *pole vs conductor vs transformer vs meter* using item category/code so HT-pole and HT-conductor targets don't conflate.
- Sequential gating is **displayed** (and softly warned), not hard-blocked, since real sites overlap stages.
