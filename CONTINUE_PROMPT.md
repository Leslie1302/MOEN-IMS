# Continuation prompt — paste this into a fresh session

---

I'm continuing work on MOEN-IMS (MOEGT IEPS), a Django inventory/release system
for Ghana's Ministry of Energy and Green Transition. Read these first, in order:

1. `IMPLEMENTATION_PLAN_signing_2026-08-06.md` — **especially §2a**, which records
   decisions that supersede the earlier phases. Do not relitigate them.
2. `HANDOFF_2026-08-05.md` — prior session context.
3. `IMPLEMENTATION_PLAN_release_docs_2026-08-05.md` — the document rework that
   preceded this.

## Where things stand

**Shipped and tested (tests written, never executed — see constraints):**
migrations 0076–0086; letterhead upload with drag-to-calibrate insets in points;
WYSIWYG document editing with an allowlist sanitiser; a Word-style formatting
ribbon; in-app signing with drawn signatures and an authority stamp; a public
verify page with two disclosure tiers; a historical-requisition archive; a
registry-grade release-code allocator; BoQ re-match for stranded receipts;
role-scoped material orders.

**Just completed:** the signing chain now spans BOTH documents in one sequence
(migration 0086). Previously chains were per-document and independent, so the
Chief Director could sign the release letter before the Ag. Director had approved
the memo — backwards, since the signed memo is the authority for the letter.

## What I need built

The remaining pieces of the linear release workflow, **as one coherent whole** —
I want to test it end to end, not in fragments. All specified in §2a:

1. **Send for signature** — an explicit officer action that emails the next
   signatory a *link* to sign in-system. No PDF attachments: documents never
   leave the system. Uses `accounts/notifications.py::send_email_notification`.
2. **Sequential notification** — completing a step notifies the next signatory
   automatically. Generation must NOT notify anyone.
3. **Approvals page** — the signatory's landing point. Three sections: awaiting
   my signature · awaiting others · recently signed by me. Driven by the same
   `next_signing_step()` that drives the email, so queue and notification cannot
   disagree.
4. **Read-only release dashboard for signatories** — informational archive, no
   generate/edit/adjust controls. Read access stays open; only emphasis changes.
   Currently `ReleaseLetterDetailView` and the tracking dashboard have **no
   per-user filtering at all**.
5. **Both documents on the signing page** — the signer always sees the pack, not
   just the document they sign.
6. **Print without letterhead** for the wet-signature route — a print-time render
   (you print onto Ministry letterhead stock), leaving the stored PDF untouched.
7. **Replace the 3-step wizard**: request → documents auto-generate → land on the
   release letter page → live edit → choose e-signature or wet signature.

Also outstanding, lower priority: the overissuance summary shows a blank item
code — **check a BoQ row in admin first**, since the template already renders
`item_code`, so it may be blank at source and the fix belongs in the upload path.

## Constraints — please respect these

- **You cannot run the test suite.** No Django in the sandbox. `py_compile`
  proves syntax and nothing about behaviour. Say so plainly rather than implying
  verification. I run tests and paste output.
- **Nothing is deployed.** GitHub Actions was 409-ing on a stale Azure
  deployment lock; WeasyPrint's native libraries are still pending my server
  admin (I'm a viewer, not an admin). PDF generation and signing are blocked in
  production regardless of what you build.
- ~70 tests written across recent sessions have never been executed.

## Traps that have already bitten, twice each

- **Django's `{# #}` is single-line only.** A multi-line one renders as visible
  text, and if it contains `{% %}` it raises TemplateSyntaxError. Use
  `{% comment %}`. `Inventory/tests/test_template_hygiene.py` sweeps for this —
  run it mentally before finishing.
- **Column/field lists built by subtraction break silently.** An import-only
  column reached a model constructor and raised TypeError. Name groups
  explicitly.
- **Check for duplicate method definitions** when adding `get_context_data` etc.
  to an existing class — the second silently wins.

## Working agreements

- Ponytail mode: smallest correct diff; mark deliberate ceilings with
  `ponytail:` comments.
- Concise responses. I prefer doing over discussing, but flag genuine design
  forks before building — several of my corrections have improved the design.
- Explain *why* in code comments, especially where a control exists for an audit
  reason.

Start by reading §2a, then tell me your plan before you build.
