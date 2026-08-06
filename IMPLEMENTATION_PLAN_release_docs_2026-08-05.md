# Implementation Plan — Rework Release Letter & Memo Generation

**Date:** 2026-08-05 · **Scope:** MOEN-IMS release-side documents (approval memo +
release letter to MMU) · **Goal:** adopt HTMS's document styling and its
letterhead-upload / content-adjustment model.

---

## 1. Why the current output is a mess

`Inventory/services/pdf_generator.py` (843 lines) draws every document with the
**low-level reportlab canvas**: hardcoded millimetre coordinates, manual
`_wrap_text`, hand-rolled `_draw_paragraphs` / `_draw_materials_schedule`,
manual `showPage()` juggling, `y -= 5*mm` bookkeeping on every line. Layout is
imperative and brittle — any change to spacing, a longer signatory title, or an
extra body paragraph shifts everything below it. There is no letterhead upload
(it draws a seal from a file path), no way to preview before minting, and no
content editing beyond the four override fields already on `ReleaseLetter`.

## 2. What HTMS actually does (verified in the appended HTMS folder)

- **Templating, not drawing.** `htms-app/shared/documents.ts` builds a
  self-contained **HTML** document. A single `shell()` wraps the body with a
  `<style>` block: `@page { size:A4; margin:22mm }`, Tahoma 12pt justified body,
  a `.letterhead` header (flex row, **green `#1b5e20` bottom rule**, monogram
  tile, org + address + contact lines; a `.center` column variant), tables with
  `border-collapse` and an `#e8f5e9` header row, a `.total` line and a
  `.sign-line`. Every value is HTML-escaped (`esc()`), so it is XSS-safe.
- **Render pipeline.** `netlify/functions/generate-document.ts` renders the HTML,
  stores it, and returns it. Its own comment: *"HTML is returned so the client
  can render/print-to-PDF; a server-side Puppeteer render can be swapped in
  behind the same contract for true PDFs."* → today it is browser print-to-PDF,
  with a documented upgrade path to a server render for real PDF files.
- **Content adjustment.** `DocOpts { referenceNo, addressee, notes }` are passed
  at generation time — the officer overrides the reference number, the addressee
  ("Bill To" / recipient), and adds free-text notes, without a code change.
- **Letterhead (migration `0023_transporter_letterhead.sql`).** The org uploads a
  **scan of its printed letterhead** → `letterhead_path` (PNG in the `documents`
  bucket) plus **`letterhead_insets`** (jsonb: `{top,bottom,left,right}` in pt)
  that calibrate the printable area so body content clears the scan's header/
  footer bands. `Settings.tsx` has the upload + a four-way inset editor. When a
  letterhead is present the final PDF is rendered **onto it** (pdf-lib overlay in
  `Invoices.tsx` / `mergeScans.ts`); when absent, the generated header is used.

**Takeaway:** the HTMS "look" is HTML + CSS, and its letterhead feature is an
uploaded image + calibrated insets + a generated-header fallback. So the right
move for MOEN-IMS is to replace canvas drawing with **HTML templates rendered to
PDF**, and add a letterhead model mirroring 0023.

## 3. Target architecture for MOEN-IMS

Port both documents to **Django HTML templates → PDF via WeasyPrint**.

- One template = one source of truth for **both the on-screen preview and the
  PDF** (WeasyPrint renders the same HTML), so "edit fields + live preview, then
  generate" (your choice) is nearly free.
- Styling ported 1:1 from HTMS's `<style>` (A4 22mm, Tahoma 12pt justified,
  green-ruled letterhead, `#e8f5e9` table header) so the memo/letter match the
  HTMS documents.
- **Engine — WeasyPrint, not browser print.** Unlike HTMS's interim
  print-to-PDF, MOEN-IMS must persist real PDF files (`memo_pdf`, `letter_pdf`)
  because the QR-match + scan-upload audit workflow depends on stored documents.
  WeasyPrint is exactly HTMS's "swap in a server render for true PDFs," done in
  Python. **Cost:** it needs the Pango/cairo/gdk-pixbuf system libraries on Azure
  App Service — see Phase 0. (Fallback if we cannot add system libs: keep
  reportlab but move to Platypus flowables; uglier, so WeasyPrint is preferred.)

### What is preserved (must not break)
QR code on each document (encodes the release code for scan matching), the
Schedule of Materials table, the `Signatory` model + the four
`memo_*_override` / `letter_signatory_override` fields, the workflow states
(`draft → memo_generated → awaiting_signature → awaiting_scan_upload`), the
`memo_pdf` / `letter_pdf` FileFields, and the existing 247-test suite.

---

## 4. Phased implementation

### Phase 0 — WeasyPrint on Azure (de-risk first, ~½ day)
- Add `weasyprint` to `requirements.txt`.
- Install native deps on the App Service: add
  `apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0
  libffi-dev libcairo2` to the startup path (extend `start.sh`), **or** move to a
  custom container if apt-at-startup proves flaky.
- Smoke test: render one hardcoded HTML string to PDF in a shell on the box.
- **Gate:** if native deps can't be made reliable, fall back to Platypus and
  skip WeasyPrint — decide here, before building templates.

### Phase 1 — Letterhead model + admin (mirrors HTMS 0023, ~1 day)
- New `Letterhead` model (single active row, or one per issuing office):
  `image` (ImageField), `inset_top/right/bottom/left` (mm, default the current
  22 mm), `pre_printed` (bool — leave the band blank for pre-printed paper),
  `active`, plus editable org lines (name, address, contact) for the
  **generated-header fallback** when no image is uploaded.
- Migration + admin (image upload + inset fields + a "print test page" action to
  calibrate insets, the equivalent of HTMS's inset editor).
- `ponytail:` start with one global active letterhead; per-office only if asked.

### Phase 2 — HTML templates + render service (the core, ~2 days)
- `templates/Inventory/documents/release_memo.html` and
  `release_letter.html`, plus a shared `_doc_base.html` carrying the ported CSS
  (A4, Tahoma/justified, green-ruled `.letterhead`, `#e8f5e9` tables,
  `.sign-line`). Letterhead block renders the uploaded image (with insets) or the
  generated header; body content is inset to clear the band.
- New `services/document_render.py`: `render_memo(release_letter, opts)` /
  `render_letter(...)` → build context (reuse existing `_build_memo_context` /
  `_build_letter_context` and the materials schedule), render template, run
  WeasyPrint → `ContentFile`. QR image passed in as a data-URI `<img>`.
- Rewire `generate_release_memo` / `generate_release_letter` in
  `pdf_generator.py` to delegate to the new service (keep the function names so
  `release_document_views.py` and tests are untouched). Delete the dead canvas
  drawing helpers once green.

### Phase 3 — Edit-fields + live preview, then generate (your choice, ~1.5 days)
- On the release-letter detail page, an **"Adjust & preview"** panel exposing the
  editable fields (TO/FROM/subject, addressee, signatory pick, free-text notes —
  extending the existing override fields with a `notes` field). Mirrors HTMS's
  `DocOpts`.
- **Preview** = the same template rendered as HTML in an `<iframe>` (new
  `MemoPreviewView` / `LetterPreviewView` returning HTML). No PDF cost to preview
  because it's the identical template.
- **Generate** commits the edited fields and mints the PDFs through the Phase-2
  service. Workflow transition unchanged (`draft → memo_generated`).

### Phase 4 — Verify (~½ day)
- Extend tests: a `Letterhead` with insets renders without error; preview HTML
  contains the edited subject/notes; the generated PDF is non-empty and still
  QR-decodes to the release code (reuse the existing QR-decode test helper).
- Run full `python manage.py test Inventory` (you run CI; I can't install
  WeasyPrint's native deps in the sandbox — I'll ship the code + tests and you
  run the gate, as usual).

**Estimate:** ~5.5 focused days, shippable per phase (Phase 1 is independently
useful; Phases 2–3 land the visible change).

---

## 5. Data model / migration summary
- `Letterhead` (new): `image`, `inset_{top,right,bottom,left}`, `pre_printed`,
  org text fields, `active`. One migration.
- `ReleaseLetter`: add `memo_notes` / `letter_notes` TextFields (the HTMS `notes`
  equivalent). Existing `memo_*_override` fields reused as-is.
- Optional later: `Signatory.signature_image` (HTMS stores signature images) to
  drop a signature graphic above the name — deferred unless you want e-sign now.

## 6. Risks & mitigations
- **WeasyPrint native deps on Azure** — the one real risk. Phase 0 de-risks it
  before any template work; Platypus is the fallback.
- **Layout drift vs the wet-signed originals** — port CSS values verbatim from
  HTMS and diff a rendered sample against a current memo before deleting the
  canvas code.
- **Font** — Tahoma isn't on Linux; bundle a metric-compatible font (DejaVu/
  Carlito) or accept the existing Helvetica fallback, same as today.

## 7. Decisions
1. **Letterhead — RESOLVED.** One global Ministry letterhead, **uploaded and
   adjustable** (image + insets). Phase 1 as written.
2. **Signatures — RESOLVED.** Keep the blank wet-signature line so the
   upload-signed-copy workflow stays intact. Move to e-signatures (upload to
   `Signatory`, placed above the name) **when the Chief Director is onboarded** —
   deferred until then.
3. **Azure (open)**: extend `start.sh` with `apt-get` for the WeasyPrint native
   libs, or use a container image? Affects Phase 0. Default if unspecified:
   `apt-get` in `start.sh` (cheapest, reversible).
