"""
HTML-template → PDF rendering for release documents (approval memo + release
letter), replacing the imperative reportlab canvas layout.

One template drives both the on-screen preview (HTML) and the stored PDF
(WeasyPrint renders the same HTML), so the preview is faithful by construction.
Styling is ported from HTMS's `shared/documents.ts` (A4, Tahoma 12pt justified,
green-ruled letterhead, #e8f5e9 table headers). The Ministry letterhead + insets
come from the `Letterhead` model.

Content/data (subject, body prose, signatory resolution, materials schedule) is
still assembled by the existing builders in `pdf_generator.py` — this module only
changes how that content is laid out.
"""

import base64
import hashlib
import io
import json
import logging

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def _data_uri(content_bytes, mime='image/png'):
    return f"data:{mime};base64," + base64.b64encode(content_bytes).decode('ascii')


def _css_string(text):
    """Make `text` safe to drop inside a CSS `content: "..."` literal.

    The page footer lives in `@page { @bottom-center { content: "..." } }`, which
    is CSS, not HTML — Django's autoescape would print a literal `&amp;` there,
    and an unescaped quote or backslash would break out of the string. Strip the
    two dangerous characters and collapse newlines; the template then emits it
    with `|safe`.
    """
    return (str(text or '')
            .replace('\\', '')
            .replace('"', "'")
            .replace('\r', ' ')
            .replace('\n', ' '))


def qr_payload(code, verify_token=None):
    """What the QR on a document actually encodes.

    Historically this was the bare release code, which meant scanning a printed
    document with a phone produced the string `RE-2026-0001` and an offer to
    web-search it — useless to the person holding the paper. It now encodes a
    link to the public verify page.

    The link carries `verify_token` because **release codes are enumerable**:
    they run RE-2026-0001, 0002, 0003. Verifying by code alone proves only that
    a reference exists, so a forger could enumerate to find a real approved code,
    print it on a fake letter, and have the page answer "issued by MOEN-IMS".
    The token is unguessable, so its presence proves the scanner held the actual
    document — which is the question verification exists to answer.

    Falls back to the bare code when `PUBLIC_BASE_URL` is unset: a QR pointing at
    `http://localhost:8000` on a printed Ministry letter would be worse than no
    link at all, and scan matching works either way (see
    `scan_validation.payload_matches_code`).
    """
    from django.conf import settings
    from django.urls import reverse, NoReverseMatch

    base = (getattr(settings, 'PUBLIC_BASE_URL', '') or '').strip().rstrip('/')
    if not base or not code:
        return code

    try:
        path = reverse('verify_document', args=[code])
    except NoReverseMatch:      # verify page not wired up in this deployment
        return code

    url = f"{base}{path}"
    if verify_token:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode({'t': verify_token})}"
    return url


def _qr_data_uri(payload):
    """Release code as a QR PNG data-URI for inline <img>. None if qrcode absent."""
    try:
        import qrcode
    except ImportError:
        logger.warning("qrcode not installed; document will lack a QR code.")
        return None
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color='black', back_color='white').save(buf, format='PNG')
    return _data_uri(buf.getvalue(), 'image/png')


# Default insets in points when no letterhead is configured (≈22 mm all round,
# matching what the documents used before the letterhead model existed).
_DEFAULT_INSETS_PT = {'top': 62, 'right': 62, 'bottom': 62, 'left': 62}


def _read_file(field):
    """Bytes of a FileField, or None. Storage hiccups must never stop a render."""
    try:
        field.open('rb')
        data = field.read()
        field.close()
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Letterhead file read failed (%s): %s", getattr(field, 'name', '?'), exc)
        return None


def letterhead_applies(kind):
    """True when a rendered letterhead appears on this document at all.

    Only the release letter carries one; the approval memo is an internal
    document on a plain sheet. Exported so callers can decide whether to offer
    the print-on-letterhead-stock option — offering it on the memo would imply a
    difference between the two renders that does not exist.
    """
    return kind == 'letter'


def _letterhead_ctx(kind, for_pdf=False, plain=False):
    """Resolve the active Letterhead into a render dict (mode + insets + preview).

    `plain=True` is the wet-signature route: the sheet already carries the
    Ministry letterhead, so the artwork must not be drawn a second time.

    **The letterhead is for the release letter only.** The approval memo is an
    internal document on a plain sheet: mode 'plain', its own `memo_inset_*`
    margins, no header of any kind and no stamping. Inheriting the letterhead's
    insets would give the memo a ~65mm top margin sized to clear artwork that
    isn't on the page.

    `for_pdf=True` suppresses the inline preview raster: in the PDF pipeline the
    letterhead is stamped onto every page afterwards by `_stamp_letterhead`,
    which keeps a PDF letterhead vector and covers page 2+. The HTML preview
    still inlines it so the officer sees what will print.
    """
    from Inventory.models import Letterhead

    lh = Letterhead.current()

    if kind == 'memo':
        insets = lh.memo_insets_pt if lh else dict(_DEFAULT_INSETS_PT)
        # No letterhead anywhere, so every page is margined identically. The
        # memo already prints on a plain sheet, so `plain` changes nothing here.
        return {'mode': 'plain', 'cont_top': insets['top'], **insets}

    # ── Printing onto Ministry letterhead stock (the wet-signature route) ────
    #
    # The artwork is already on the paper, so drawing it again would print it
    # twice. But the **insets must stay**: they are what keeps the body text
    # clear of the pre-printed header, and they were calibrated against that
    # exact stock. Dropping them along with the image is the tempting
    # simplification, and it puts the first line of the letter underneath the
    # Ministry crest.
    #
    # `pre_printed` is already precisely this mode — letterhead stock, no
    # rendered header, calibrated insets reserved — so this reuses it rather
    # than inventing a second way to say the same thing.
    if plain:
        if lh:
            return {'mode': 'pre_printed',
                    'top': lh.inset_top, 'right': lh.inset_right,
                    'bottom': lh.inset_bottom, 'left': lh.inset_left,
                    'cont_top': lh.cont_inset_top,
                    'org_name': lh.org_name, 'org_address': lh.org_address,
                    'org_contact': lh.org_contact}
        # No letterhead configured, so nothing has been calibrated against the
        # Ministry's stock and these insets are a ~22mm guess. Still the right
        # answer: a document that prints with the wrong margin is fixable by
        # calibrating, whereas one that prints its own letterhead on top of the
        # pre-printed one is not fixable at all.
        return {'mode': 'pre_printed',
                'cont_top': _DEFAULT_INSETS_PT['top'], **_DEFAULT_INSETS_PT}

    if not lh:
        return {'mode': 'text',
                'org_name': 'Ministry of Energy and Green Transition',
                'org_address': 'P.O. Box SD 40, Accra', 'org_contact': '',
                'cont_top': _DEFAULT_INSETS_PT['top'], **_DEFAULT_INSETS_PT}

    ctx = {'top': lh.inset_top, 'right': lh.inset_right, 'bottom': lh.inset_bottom,
           'left': lh.inset_left,
           # Page 2+ is plain paper: no header band to clear, so only the top
           # margin shrinks. Left/right/bottom stay put so the text block on the
           # continuation page lines up with page 1.
           'cont_top': lh.cont_inset_top,
           'org_name': lh.org_name,
           'org_address': lh.org_address, 'org_contact': lh.org_contact}

    if lh.pre_printed:
        ctx['mode'] = 'pre_printed'
        return ctx

    if not lh.file:
        ctx['mode'] = 'text'
        return ctx

    # A file is configured. For the PDF we draw no header in the HTML at all —
    # the stamp goes on afterwards, underneath the body, on every page.
    if for_pdf:
        ctx['mode'] = 'stamped'
        return ctx

    source = lh.preview_image if lh.preview_image else lh.file
    data = _read_file(source)
    if data is None:
        ctx['mode'] = 'text'      # degrade rather than block the officer
        return ctx
    mime = 'image/png' if source.name.lower().endswith('.png') else 'image/jpeg'
    ctx['mode'] = 'image'
    ctx['img'] = _data_uri(data, mime)
    return ctx


def _stamp_letterhead(pdf_bytes, kind='letter'):
    """Stamp the active letterhead onto the FIRST page of a rendered PDF.

    Scope, deliberately narrow:
      * **release letter only** — the approval memo prints on a plain sheet;
      * **page 1 only** — the Ministry prints page 1 on letterhead stock and
        continuation pages on plain paper, so stamping every page would produce
        something that never matches the wet-signed original. Pages 2+ get
        `cont_inset_top` instead of the calibrated inset (see `@page :first`).

    Why stamp at all, rather than putting the image in the HTML flow:
      * a PDF letterhead stays **vector** — crisp at any zoom, and a stamped
        vector page adds a few KB where an inlined 300 dpi raster adds megabytes
        to every document;
      * the body is rendered independently, so the officer's WYSIWYG edits and
        the letterhead can never fight over layout.

    Returns the original bytes unchanged if there is nothing to stamp or if
    anything goes wrong — a missing letterhead must degrade to a plain document,
    never to a failed release.
    """
    from Inventory.models import Letterhead

    if kind != 'letter':
        return pdf_bytes

    lh = Letterhead.current()
    if not lh or lh.pre_printed or not lh.file:
        return pdf_bytes

    source = _read_file(lh.file)
    if source is None:
        return pdf_bytes

    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.warning("PyMuPDF unavailable — letterhead not stamped.")
        return pdf_bytes

    doc = stamp = None
    try:
        doc = fitz.open(stream=pdf_bytes, filetype='pdf')
        if not doc.page_count:
            return pdf_bytes
        first = doc.load_page(0)   # page 1 only — pages 2+ are plain paper

        if lh.is_pdf:
            stamp = fitz.open(stream=source, filetype='pdf')
            if not stamp.page_count:
                return pdf_bytes
            # overlay=False puts the letterhead *behind* the body text.
            first.show_pdf_page(first.rect, stamp, 0, overlay=False)
        else:
            first.insert_image(first.rect, stream=source, overlay=False)

        return doc.tobytes(deflate=True, garbage=3)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Letterhead stamping failed, returning unstamped PDF: %s", exc)
        return pdf_bytes
    finally:
        for handle in (stamp, doc):
            try:
                if handle is not None:
                    handle.close()
            except Exception:  # noqa: BLE001
                pass


def _schedule_rows(orders):
    rows = []
    for o in (orders or []):
        rows.append({
            'material': o.name or '',
            'qty': o.quantity,
            'unit': o.unit.name if o.unit_id else '',
            'community': o.community or o.district or '',
        })
    return rows


# ── Shared build ─────────────────────────────────────────────────────────────
#
# Both documents follow the same shape: build the data context, render the body
# from either the template or the officer's stored hand-edit, and wrap it in the
# shared shell (page CSS + letterhead band + QR).
#
# The shell is ALWAYS template-driven, even for an edited document. That is
# deliberate: a letterhead swap or an inset recalibration must still reach every
# document, and the QR must keep encoding the real release code — neither can be
# edited away.

_SPEC = {
    'memo': {
        'template': 'Inventory/documents/release_memo.html',
        'context': '_build_memo_context',
        'body': '_build_memo_body',
        'notes': 'memo_notes',
        'stored': 'memo_html',
        'footer': lambda ctx: (f"System-generated by MOEN-IMS — Release event {ctx['code']} — "
                               f"Generated {timezone.now().strftime('%d %B %Y, %H:%M')}"),
    },
    'letter': {
        'template': 'Inventory/documents/release_letter.html',
        'context': '_build_letter_context',
        'body': '_build_letter_body',
        'notes': 'letter_notes',
        'stored': 'letter_html',
        'footer': lambda ctx: (f"System-generated by MOEN-IMS — Release event {ctx['code']} — "
                               f"Validate the scanned signed copy by checking the QR code."),
    },
}


def _signature_blocks(release_letter, kind):
    """Applied signatures, ready for the template.

    Each block is the drawn signature as a data-URI plus the authority stamp
    lines. Inlining the image keeps the PDF self-contained and means the file is
    never fetched from storage at render time — the signature image has no
    public URL by design.
    """
    blocks = []
    try:
        signatures = release_letter.signatures_for(kind)
    except Exception:  # noqa: BLE001 — a release with no signing configured
        return blocks

    for signature in signatures:
        img = None
        if signature.signature_image:
            data = _read_file(signature.signature_image)
            if data:
                img = _data_uri(data, 'image/png')
        blocks.append({'img': img, 'lines': signature.stamp_lines,
                       'token': signature.verification_token})
    return blocks


def _build(release_letter, kind):
    """→ (spec, ctx, paragraphs, schedule) for 'memo' or 'letter'."""
    from . import pdf_generator

    spec = _SPEC[kind]
    ctx = getattr(pdf_generator, spec['context'])(release_letter)
    paragraphs = list(getattr(pdf_generator, spec['body'])(release_letter, ctx))
    note = (getattr(release_letter, spec['notes'], '') or '').strip()
    if note:
        paragraphs.append(note)
    return spec, ctx, paragraphs, _schedule_rows(ctx.get('orders'))


def context_fingerprint(release_letter, kind):
    """Stable hash of the data a document is built from.

    Recorded when an officer saves a hand-edit. If the live data later hashes
    differently, the materials, subject or signatory moved underneath the stored
    wording and the detail page raises a "data changed" banner — we never
    silently overwrite an edit, and never silently serve a stale one either.
    """
    try:
        _, ctx, paragraphs, schedule = _build(release_letter, kind)
    except Exception as exc:  # noqa: BLE001 — fingerprinting must never break a page
        logger.warning("Fingerprint build failed for %s: %s", kind, exc)
        return ''
    # The BoQ position is part of what the memo asserts, so it belongs in the
    # fingerprint. Without it, an officer's hand-edit freezes a reconciliation
    # into stored HTML and the memo goes on printing last week's contract
    # balance with no warning — a stale reconciliation being worse than none,
    # because it still looks authoritative. Included here, a BoQ movement raises
    # the same "data changed" banner that a changed quantity already does.
    boq_position = None
    if kind == 'memo':
        try:
            from .reconciliation import reconcile
            result = reconcile(release_letter)
            boq_position = [
                [line['item_code'], str(line['requested']),
                 str(line['balance_before']), str(line['matched'])]
                for line in result['lines']
            ]
        except Exception as exc:  # noqa: BLE001 — must never break a page render
            logger.warning("Reconciliation fingerprint failed for %s: %s",
                           release_letter.pk, exc)

    payload = json.dumps({
        'code': ctx.get('code'),
        'subject': ctx.get('memo_subject') or ctx.get('letter_subject'),
        'to': ctx.get('memo_to'),
        'from': ctx.get('memo_from'),
        'signatory': ctx.get('memo_signatory_name') or ctx.get('letter_signatory_name'),
        'paragraphs': paragraphs,
        'schedule': [[r['material'], str(r['qty']), r['unit'], r['community']] for r in schedule],
        'cc': list(ctx.get('cc_list') or []),
        'boq': boq_position,
    }, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def render_document_html(release_letter, kind, edit_mode=False, use_stored=True,
                         for_pdf=False, plain=False):
    """Render a release document to standalone HTML.

    `use_stored=False` forces the data-driven template even when a hand-edit
    exists — that is how "revert to generated" previews the original, and how
    the editor reloads a clean copy.

    `for_pdf=True` omits the inline letterhead raster because the PDF pipeline
    stamps the real asset onto every page afterwards.

    `plain=True` omits the letterhead entirely for printing onto Ministry
    letterhead stock. This is a **render option, not a second document**: the
    stored PDF is never produced this way, so there is one file and one
    letterhead, and the wet-signature route cannot drift from the e-signature
    one. Same body, same signatures, same QR — only the artwork is left off.
    """
    spec, ctx, paragraphs, schedule = _build(release_letter, kind)
    stored = (getattr(release_letter, spec['stored'], '') or '').strip() if use_stored else ''

    # BoQ reconciliation — memo only. The approving officer needs to know
    # whether the contract has room for this release; MMU does not, and putting
    # contract balances on the letter would send them to the warehouse counter.
    #
    # Computed at render time rather than stored, so a re-render after the BoQ
    # moves shows the position as it is now. That is the right trade: a stale
    # reconciliation is worse than none, because it looks authoritative.
    reconciliation = reconciliation_summary = None
    if kind == 'memo':
        from .reconciliation import reconcile, summary_sentence
        result = reconcile(release_letter)
        # Non-conventional releases (Streetlights / Cost-sharing) have no BoQ to
        # reconcile against, so the section is omitted entirely — there is no
        # position to state. Mixed releases keep it for their conventional lines.
        if not result['all_nonconventional']:
            reconciliation = result
            reconciliation_summary = summary_sentence(result)

    return render_to_string(spec['template'], {
        'lh': _letterhead_ctx(kind, for_pdf=for_pdf, plain=plain),
        'reconciliation': reconciliation,
        'reconciliation_summary': reconciliation_summary,
        'qr': _qr_data_uri(qr_payload(ctx['code'], release_letter.ensure_verify_token())),
        'ctx': ctx,
        'paragraphs': paragraphs,
        'schedule': schedule,
        'stored_body': stored,
        'edit_mode': edit_mode,
        'screen': not for_pdf,
        'doc_kind': kind,
        'signatures': _signature_blocks(release_letter, kind),
        'footer_text': _css_string(spec['footer'](ctx)),
    })


class RendererUnavailable(RuntimeError):
    """WeasyPrint (or its native libraries) is not usable on this host.

    Raised as its own type so the generate view can show an actionable message
    instead of a bare ImportError. This must never fall back to the retired
    canvas layout: a silent fallback is exactly how stale documents get minted
    and nobody notices the renderer is missing.
    """


def weasyprint_status():
    """→ (ok, detail). Cheap enough to call on a page render."""
    try:
        import weasyprint  # noqa: F401
    except ImportError as exc:
        return False, (f"WeasyPrint is not installed ({exc}). "
                       "Add it with: pip install weasyprint==69.0")
    except OSError as exc:
        # The import succeeds but Pango/cairo are missing — the usual symptom
        # on a fresh Linux host or a macOS box without the Homebrew libs.
        return False, (f"WeasyPrint's native libraries are missing ({exc}). "
                       "Linux: apt-get install libpango-1.0-0 libpangocairo-1.0-0 "
                       "libgdk-pixbuf-2.0-0 libcairo2 libffi-dev. "
                       "macOS: brew install pango gdk-pixbuf libffi cairo")
    return True, "ok"


def render_document_pdf(release_letter, kind):
    ok, detail = weasyprint_status()
    if not ok:
        # Loud and specific. The old behaviour — a broad except in the view —
        # left the previous PDFs in place and reported only "generation
        # failed", which reads as "the template didn't change".
        logger.error("PDF generation unavailable: %s", detail)
        raise RendererUnavailable(
            f"Cannot render PDFs — the documents on this release were NOT updated. {detail}")

    from weasyprint import HTML
    html = render_document_html(release_letter, kind, for_pdf=True)
    pdf = _stamp_letterhead(HTML(string=html).write_pdf(), kind)
    return ContentFile(pdf, name=f"{kind}_{release_letter.code or 'draft'}.pdf")


# ── Public API (names kept so callers and tests are untouched) ───────────────
def render_memo_html(release_letter, edit_mode=False, use_stored=True):
    return render_document_html(release_letter, 'memo', edit_mode, use_stored)


def render_letter_html(release_letter, edit_mode=False, use_stored=True):
    return render_document_html(release_letter, 'letter', edit_mode, use_stored)


def render_memo(release_letter):
    return render_document_pdf(release_letter, 'memo')


def render_letter(release_letter):
    return render_document_pdf(release_letter, 'letter')
