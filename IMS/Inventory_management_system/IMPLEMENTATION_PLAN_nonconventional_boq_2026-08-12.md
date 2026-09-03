# Implementation Plan — Releasing Non-Conventional Projects Without a Pre-Established BoQ

**Date:** 2026-08-12
**Problem:** Streetlights / Cost-sharing releases are blocked with *"N line(s) have
no Bill of Quantity entry for their community…"* even though these programmes have
no pre-loaded, community-by-community Bill of Quantity to check against.

---

## 1. Root cause (verified against the running DB)

The generation gate refuses any release line whose material+community has no BoQ
row ("unmatched"). That is correct for **SHEP** (a missing row is a real data
fault) but wrong for **Streetlights / Cost-sharing**, which are never scoped in
advance. Three concrete faults make it still fire:

1. **The fix is on only one of two generation doors.** An auto-provision step was
   added to `release_document_views._blocking_message` (the detail-page *Generate*
   button). But the **request-code wizard** —
   `release_letter_views.ReleaseLetterUploadView._handle_generate` — calls
   `reconciliation.generation_blockers()` **directly** (line ~176) and never
   auto-provisions. Its own docstring admits *"this is the door most releases come
   through."* Release 9 (`Single Phase Meter SMM001 at NSUAEM`, project_type
   `STREET`) went through the wizard, so it blocked.

2. **project_type is stored in two different value-spaces.** Verified:
   - `MaterialOrder.project_type` → short codes: `SHEP`, `STREET`, (`COST`, `SPEC`).
   - `BillOfQuantity.project_type` → full names: `SHEP`, `Streetlights`, `Cost Sharing`.
   The auto-provision writes the **short** code (`STREET`) onto a BoQ row whose
   siblings all say `Streetlights`. Even when it runs it produces an
   inconsistent row, and any project-aware BoQ query is landmined.

3. **The block is expressed as data-repair.** The reconciliation layer treats
   "no BoQ" as always-an-error. For non-conventional programmes it is the normal,
   expected state — so the *policy* is wrong there, not just the plumbing.

There is nothing wrong with the SMM001/NSUAEM data: NSUAEM legitimately has only
`SMP001/SMC001/SMT001` in the BoQ, and this release draws `SMM001`, which no
streetlights BoQ line covers — exactly the case that should be allowed to proceed.

---

## 2. Design decision (pick one; Option A recommended)

**Option A — Non-conventional is authorised by the release itself (recommended).**
Make the reconciliation layer treat an unmatched line as **non-blocking when the
release's project type is non-conventional**, and (optionally) record a BoQ row so
the programme still shows up in tracking. The decision lives in the ONE function
every door already calls (`generation_blockers`), so all paths are fixed at once
with no duplicated logic. The memo states the authorisation basis honestly.

**Option B — Robust central auto-provision (closest to what exists).**
Keep creating BoQ rows, but move the step so **every** door runs it exactly once,
and fix the value-space. Heavier (writes data on every generation) and still needs
the memo wording, but keeps a BoQ row per non-conventional line for reporting.

Both share Phases 1–2 below; they differ only in Phase 3. **Recommendation: A**,
because it needs no fabricated contract quantities, can't drift value-spaces, and
keeps the BoQ table meaning "a real, pre-agreed contract line." A can still record
a lightweight tracking row when a programme wants one, without pretending it is a
contract.

---

## 3. Phased implementation

### Phase 1 — One canonical project-type comparison (fixes fault #2)
- Add `Inventory/constants.py::is_nonconventional(value)` and a
  `normalize_project_type(value) -> {'SHEP'|'STREET'|'COST'|'SPEC'}` that accepts
  **either** space (`'Streetlights'`, `'STREET'`, `'streetlights'`, `'Cost Sharing'`,
  `'COST'`, …). Reuse the existing `LEGACY_PROJECT_TYPE_MAP` / `project_type_to_charfield`
  rather than a new table.
- Every project-type test in this feature goes through this helper, so short-code
  vs full-name can never diverge again.
- Guardrail: this is a correctness fix beyond this ticket — grep for direct
  `project_type ==`/`in (...)` comparisons on BoQ and route them through it.

### Phase 2 — A single shared generation gate (fixes fault #1)
- Extract one entrypoint, e.g. `reconciliation.evaluate_release(release_letter)`
  (or a thin `services/release_gate.py`), returning `(blockers, result)`.
- Route **both** doors through it:
  - `release_document_views._blocking_message`
  - `release_letter_views.ReleaseLetterUploadView._handle_generate`
- Delete the now-duplicated inline gate in the wizard. The docstring's promise
  ("the same gate guards both doors") becomes true in code.
- `boq_assistance` keeps calling the **read-only** `generation_blockers` for its
  display (it must still show what *would* block), so the non-conventional policy
  lives in the gate, not in the raw blocker computation used for display.

### Phase 3A — Non-conventional lines don't block (Option A)
- In the shared gate: split `unmatched` into `unmatched_blocking` (conventional /
  SHEP / unknown) and `unmatched_allowed` (release project type is
  `is_nonconventional`). Only `unmatched_blocking` stops generation.
- The refusal message and the `boq-assistance` page report only the blocking set.
- Optional tracking row: behind a setting
  (`AUTO_TRACK_NONCONVENTIONAL_BOQ = True`), record a BoQ row for each allowed
  line using the **normalized full-name** project type, `contract_quantity =
  requested`, and an `auto_provisioned=True` marker so reports can tell contract
  rows from release-authorised ones. Idempotent; skips lines missing item code or
  community.

  *(Phase 3B — Option B alternative: same, but always create the row and never
  add the "allowed" branch; the row's existence is what unblocks. Requires the
  Phase-1 value fix to match `_boq_for`.)*

### Phase 4 — Honest documents
- When a release is non-conventional, the memo's reconciliation line reads e.g.
  *"This is a Streetlights release; the listed materials are authorised by this
  release order, as the programme is not scoped by a pre-loaded Bill of Quantity."*
  — instead of silently claiming it reconciles. One conditional in the memo
  reconciliation partial (`_reconciliation.html`) keyed on the gate result.

### Phase 5 — Tests + backfill
- Tests: **both** doors generate a non-conventional release with an unmatched
  line; a SHEP release with an unmatched line still blocks; value-space
  normalisation (`'STREET'` and `'Streetlights'` both classify non-conventional);
  idempotency; a mixed release blocks only its SHEP line.
- `manage.py audit_release_gate` (or extend `audit_boq_blanks`) to list releases
  that *would* block, so go-live surprises are found before an officer hits them.
- Retire `services/boq_autoprovision.py` (its logic moves into the shared gate) or
  reduce it to the optional tracking-row helper.

---

## 4. Files touched
- `Inventory/constants.py` — `normalize_project_type` / `is_nonconventional`.
- `Inventory/services/reconciliation.py` — split unmatched by project type; shared
  `evaluate_release`.
- `Inventory/views/release_letter_views.py` — route the wizard through the shared gate.
- `Inventory/views/release_document_views.py` — route `_blocking_message` through it.
- `Inventory/templates/Inventory/documents/_reconciliation.html` — non-conventional wording.
- `Inventory/services/boq_autoprovision.py` — folded in / demoted to tracking helper.
- Tests: `tests/test_boq_autoprovision.py` → `tests/test_release_gate.py`.

## 5. Risks
- **No contract ceiling for non-conventional.** By definition these have no scope,
  so there is no over-issuance number to enforce — the control that remains is the
  memo → Director approval → signature, which the workflow already provides.
- **Existing inconsistent BoQ rows** written by the current auto-provision
  (short-code `STREET`) — a one-off data fix normalises them to `Streetlights`.
- **`generation_blockers` is also a display source** for `boq-assistance`; keep the
  policy in the gate, not in the raw blocker function, or the assistance page will
  wrongly show nothing.

## 6. Decisions I need from you
1. **Option A vs B** — allow non-conventional through with an honest note (A,
   recommended), or always auto-create a BoQ row per line (B)?
2. **Tracking rows** — for non-conventional, do you still want a BoQ row recorded
   for reporting (default: yes, marked `auto_provisioned`)? Or leave the BoQ table
   strictly for real contracts?
3. **Which programmes count as non-conventional** — Streetlights + Cost-sharing
   confirmed. Add `SPEC` (Special/other)? SHEP stays conventional.
