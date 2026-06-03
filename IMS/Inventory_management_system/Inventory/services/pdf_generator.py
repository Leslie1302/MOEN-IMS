"""
Phase F.1 PDF generator service.

Produces two documents per release event:

  generate_release_memo(release_letter)
    Internal memorandum from Ag. Director, Power to the Chief Director
    seeking approval to release materials from MMU. Mirrors the structure
    of REQUEST FOR A REPLACEMENT OF TRANSFORMER THE HEAD OF STATE AWARD
    SCHEME.docx -- TO/FROM/DATE/SUBJECT block at top, body prose, signature.

  generate_release_letter(release_letter)
    External letter from MOEN to the MMU manager directing release of the
    materials to the consignee (consultant for SHEP, MP for Cost Sharing /
    Streetlights). Mirrors the structure of RELEASE LETTER MINISTRY OF
    EDUCATION.docx -- addressee block, bold subject, body, signature
    block ("FOR: HON. MINISTER"), cc list. QR code with the release code
    in the top-right corner so scan uploads can be matched back to this
    specific release event.

Both functions return Django ContentFile instances ready to assign to a
FileField. The caller is responsible for persisting them on the
ReleaseLetter row and committing the transaction.
"""

import io
import logging
import os
from datetime import datetime

from django.core.files.base import ContentFile
from django.utils import timezone

logger = logging.getLogger(__name__)


# ── Body font registration ─────────────────────────────────────────────
# We want Tahoma 12 for the body text. Tahoma is not a built-in PDF font
# in ReportLab so we register it from a system TTF when one is present
# and fall back to Helvetica if not. Both names get exposed on
# BODY_FONT / BODY_FONT_BOLD so the rest of the file stays portable.

BODY_FONT = 'Helvetica'
BODY_FONT_BOLD = 'Helvetica-Bold'


def _register_body_fonts():
    """Best-effort Tahoma registration. Silent fallback to Helvetica."""
    global BODY_FONT, BODY_FONT_BOLD
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except Exception:
        return

    regular_candidates = [
        '/Library/Fonts/Tahoma.ttf',
        '/System/Library/Fonts/Tahoma.ttf',
        '/Library/Fonts/Microsoft/Tahoma.ttf',
        '/usr/share/fonts/truetype/msttcorefonts/Tahoma.ttf',
        '/usr/share/fonts/truetype/tahoma/Tahoma.ttf',
        '/usr/share/fonts/truetype/tahoma/tahoma.ttf',
        'C:/Windows/Fonts/tahoma.ttf',
    ]
    bold_candidates = [
        '/Library/Fonts/Tahoma Bold.ttf',
        '/System/Library/Fonts/Tahoma Bold.ttf',
        '/Library/Fonts/Microsoft/Tahoma Bold.ttf',
        '/usr/share/fonts/truetype/msttcorefonts/Tahoma_Bold.ttf',
        '/usr/share/fonts/truetype/tahoma/Tahoma-Bold.ttf',
        '/usr/share/fonts/truetype/tahoma/tahomabd.ttf',
        'C:/Windows/Fonts/tahomabd.ttf',
    ]

    reg_path = next((p for p in regular_candidates if os.path.exists(p)), None)
    if not reg_path:
        return
    try:
        pdfmetrics.registerFont(TTFont('Tahoma', reg_path))
        BODY_FONT = 'Tahoma'
    except Exception:
        return

    bold_path = next((p for p in bold_candidates if os.path.exists(p)), None)
    if bold_path:
        try:
            pdfmetrics.registerFont(TTFont('Tahoma-Bold', bold_path))
            BODY_FONT_BOLD = 'Tahoma-Bold'
        except Exception:
            BODY_FONT_BOLD = 'Tahoma'  # use regular for bold if the bold TTF fails
    else:
        # No bold TTF — Paragraph and table headers still want a bold
        # face. Pair Tahoma regular with Helvetica-Bold so things at
        # least stand out, rather than silently rendering bold as regular.
        BODY_FONT_BOLD = 'Helvetica-Bold'

    try:
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily('Tahoma', normal='Tahoma', bold=BODY_FONT_BOLD,
                           italic='Tahoma', boldItalic=BODY_FONT_BOLD)
    except Exception:
        pass


_register_body_fonts()


# ── MoEnGT logo helper ────────────────────────────────────────────────
# Both the memo and the release letter top-center the Ministry seal.
# Lookup order:
#   1. settings.MOENGT_LOGO_PATH
#   2. <BASE_DIR>/Inventory/static/Inventory/img/moengt_logo.png
#   3. <BASE_DIR>/staticfiles/Inventory/img/moengt_logo.png
#   4. Inventory/static/Inventory/img/moengt_logo.png  (relative to this file)
# If none exists the call is a silent no-op so older deployments don't
# break before the file is dropped into static/.

def _find_logo_path():
    candidates = []
    try:
        from django.conf import settings
        explicit = getattr(settings, 'MOENGT_LOGO_PATH', None)
        if explicit:
            candidates.append(explicit)
        base_dir = getattr(settings, 'BASE_DIR', None)
        if base_dir:
            candidates.append(os.path.join(
                str(base_dir), 'Inventory', 'static', 'Inventory', 'img', 'moengt_logo.png'
            ))
            candidates.append(os.path.join(
                str(base_dir), 'staticfiles', 'Inventory', 'img', 'moengt_logo.png'
            ))
    except Exception:
        pass
    candidates.append(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', 'static', 'Inventory', 'img', 'moengt_logo.png',
    ))
    for p in candidates:
        try:
            if p and os.path.exists(p):
                return p
        except Exception:
            continue
    return None


def _draw_letterhead_logo(pdf, page_width, page_height, size_mm=22):
    """Top-center the Ministry seal. No-op when the file is missing."""
    from reportlab.lib.units import mm
    path = _find_logo_path()
    if not path:
        return False
    size = size_mm * mm
    x = (page_width - size) / 2
    y = page_height - size - 8 * mm
    try:
        pdf.drawImage(path, x, y, width=size, height=size,
                      preserveAspectRatio=True, mask='auto')
        return True
    except Exception as exc:
        logger.warning(f"Failed to render MoEnGT logo: {exc}")
        return False


def _body_style(font_size=12, leading=15, alignment=None, bold=False):
    """Return a ParagraphStyle for justified body text in the registered font."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY
    return ParagraphStyle(
        'body',
        fontName=(BODY_FONT_BOLD if bold else BODY_FONT),
        fontSize=font_size,
        leading=leading,
        alignment=(alignment if alignment is not None else TA_JUSTIFY),
    )


def _draw_paragraphs(pdf, paragraphs, x, top_y, max_width, bottom_margin,
                     page_height, font_size=12, leading=15, paragraph_gap=4):
    """Render a list of paragraphs as justified Tahoma 12 text.

    Paginates when the next paragraph would cross `bottom_margin`. Returns
    the y-coordinate immediately below the last drawn line.
    """
    from reportlab.platypus import Paragraph
    from reportlab.lib.units import mm

    style = _body_style(font_size=font_size, leading=leading)
    y = top_y
    for text in paragraphs:
        if not text:
            continue
        p = Paragraph(text, style)
        avail_h = y - bottom_margin
        w, h = p.wrap(max_width, avail_h)
        if h > avail_h:
            pdf.showPage()
            y = page_height - 30 * mm
            avail_h = y - bottom_margin
            w, h = p.wrap(max_width, avail_h)
        p.drawOn(pdf, x, y - h)
        y -= h + paragraph_gap * mm
    return y


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_release_memo(release_letter):
    """
    Generate the approval memo PDF for a release. Returns a ContentFile
    suitable for assignment to ReleaseLetter.memo_pdf.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    ctx = _build_memo_context(release_letter)

    # Ministry letterhead seal — top-center, sits above the MEMORANDUM line.
    _draw_letterhead_logo(pdf, width, height, size_mm=22)

    # Header: MEMORANDUM centered, bold
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(width / 2, height - 42 * mm, "MEMORANDUM")

    # QR code top-right (encodes the release code so the memo can be matched
    # back to its sibling release letter and scan upload at audit time).
    qr_size = 22 * mm
    qr_x = width - qr_size - 15 * mm
    qr_y = height - qr_size - 10 * mm
    qr_image = _render_qr_code(ctx['code'])
    if qr_image is not None:
        pdf.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size, mask='auto')
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(width - 15 * mm, qr_y - 3 * mm, ctx['code'])

    # TO/FROM/DATE/SUBJECT block
    y = height - 62 * mm
    line_height = 6 * mm
    label_x = 20 * mm
    value_x = 55 * mm

    pdf.setFont(BODY_FONT_BOLD, 12)
    for label, value in [
        ("TO:", ctx['memo_to']),
        ("FROM:", ctx['memo_from']),
        ("DATE:", ctx['date']),
        ("SUBJECT:", ctx['memo_subject']),
    ]:
        pdf.drawString(label_x, y, label)
        pdf.setFont(BODY_FONT, 12)
        wrapped_lines = _wrap_text(value, max_width=width - value_x - 20 * mm, font_size=12)
        for line in wrapped_lines:
            pdf.drawString(value_x, y, line)
            y -= line_height
        pdf.setFont(BODY_FONT_BOLD, 12)

    y -= 4 * mm  # extra space before body

    # Body paragraphs — justified Tahoma 12 (with Helvetica fallback when
    # Tahoma isn't installed on the host).
    body_paragraphs = _build_memo_body(release_letter, ctx)
    y = _draw_paragraphs(
        pdf, body_paragraphs,
        x=20 * mm, top_y=y,
        max_width=width - 40 * mm,
        bottom_margin=50 * mm,
        page_height=height,
        font_size=12, leading=15, paragraph_gap=4,
    )

    # Schedule of Materials — itemises every order in the release event.
    # Single-line releases also benefit by getting an explicit table; bulk
    # releases needed it because the body now defers to it.
    orders_for_table = ctx.get('orders') or []
    if orders_for_table:
        y -= 2 * mm
        if y < 70 * mm:
            pdf.showPage()
            y = height - 30 * mm
        y = _draw_materials_schedule(pdf, orders_for_table, y, width)
        pdf.setFont("Helvetica", 11)

    # Signature block
    y -= 20 * mm  # leave space for wet signature
    if y < 60 * mm:
        pdf.showPage()
        y = height - 60 * mm

    pdf.setFont(BODY_FONT_BOLD, 12)
    pdf.drawString(20 * mm, y, ctx['memo_signatory_name'].upper())
    y -= 5 * mm
    pdf.setFont(BODY_FONT, 12)
    if ctx['memo_signatory_title']:
        pdf.drawString(20 * mm, y, ctx['memo_signatory_title'].upper())
        y -= 5 * mm

    # Footer
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawCentredString(width / 2, 15 * mm,
                          f"System-generated by MOEN-IMS — Release event {ctx['code']} — "
                          f"Generated {timezone.now().strftime('%d %B %Y, %H:%M')}")

    pdf.save()
    buffer.seek(0)
    return ContentFile(buffer.getvalue(), name=f"memo_{ctx['code']}.pdf")


def generate_release_letter(release_letter):
    """
    Generate the release letter PDF to MMU. Returns a ContentFile suitable
    for assignment to ReleaseLetter.letter_pdf.

    Includes a QR code in the top-right corner encoding the release code
    so uploaded scans can be matched back to this release event.
    """
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    ctx = _build_letter_context(release_letter)

    # Ministry letterhead seal — top-center.
    drew_logo = _draw_letterhead_logo(pdf, width, height, size_mm=26)
    if not drew_logo:
        # Fall back to the original placeholder line so absence of the
        # logo file doesn't leave the top of the letter blank.
        pdf.setFont("Helvetica-Oblique", 8)
        pdf.setFillGray(0.55)
        pdf.drawString(20 * mm, height - 12 * mm,
                       "[ Ministry of Energy and Green Transition — letterhead reserved ]")
        pdf.setFillGray(0)

    # QR code in top-right
    qr_size = 25 * mm
    qr_x = width - qr_size - 15 * mm
    qr_y = height - qr_size - 12 * mm
    qr_image = _render_qr_code(ctx['code'])
    if qr_image is not None:
        pdf.drawImage(qr_image, qr_x, qr_y, width=qr_size, height=qr_size, mask='auto')
    # Code printed below the QR for human reading.
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(width - 15 * mm, qr_y - 3 * mm, ctx['code'])

    # Date right-aligned below the QR
    pdf.setFont("Helvetica", 10)
    pdf.drawRightString(width - 15 * mm, qr_y - 9 * mm, ctx['date'])

    # Recipient block (left-aligned, ~45mm from top of body area)
    y = height - 55 * mm
    pdf.setFont(BODY_FONT_BOLD, 12)
    pdf.drawString(20 * mm, y, "THE MANAGER")
    y -= 5.5 * mm
    pdf.drawString(20 * mm, y, "MATERIALS MANAGEMENT UNIT")
    y -= 5.5 * mm
    pdf.drawString(20 * mm, y, "KPONE-TEMA")
    y -= 12 * mm

    # Subject — bold, all caps, centered
    pdf.setFont(BODY_FONT_BOLD, 12)
    subject_lines = _wrap_text(ctx['letter_subject'], max_width=width - 40 * mm, font_size=12)
    for line in subject_lines:
        pdf.drawCentredString(width / 2, y, line)
        y -= 5.5 * mm
    y -= 6 * mm

    # Body paragraphs — justified Tahoma 12 (Helvetica fallback).
    body_paragraphs = _build_letter_body(release_letter, ctx)
    y = _draw_paragraphs(
        pdf, body_paragraphs,
        x=20 * mm, top_y=y,
        max_width=width - 40 * mm,
        bottom_margin=60 * mm,
        page_height=height,
        font_size=12, leading=15, paragraph_gap=4,
    )

    # Schedule of Materials — enumerates every order on the release event
    # so the wet-signed letter covers the full scope of the authorisation.
    orders_for_table = ctx.get('orders') or []
    if orders_for_table:
        y -= 2 * mm
        if y < 80 * mm:
            pdf.showPage()
            y = height - 30 * mm
        y = _draw_materials_schedule(pdf, orders_for_table, y, width)
        pdf.setFont("Helvetica", 11)

    # Signature block: NAME / TITLE / FOR: HON. MINISTER
    y -= 22 * mm  # leave space for wet signature
    if y < 70 * mm:
        pdf.showPage()
        y = height - 70 * mm

    pdf.setFont(BODY_FONT_BOLD, 12)
    pdf.drawString(20 * mm, y, ctx['letter_signatory_name'].upper())
    y -= 5 * mm
    pdf.setFont(BODY_FONT, 12)
    if ctx['letter_signatory_title']:
        pdf.drawString(20 * mm, y, ctx['letter_signatory_title'].upper())
        y -= 5 * mm
    if ctx['letter_signatory_signs_for']:
        pdf.drawString(20 * mm, y, f"FOR: {ctx['letter_signatory_signs_for'].upper()}")
        y -= 8 * mm

    # CC list
    if ctx['cc_list']:
        pdf.setFont(BODY_FONT, 10)
        pdf.drawString(20 * mm, y, "cc:")
        y -= 4.5 * mm
        for cc in ctx['cc_list']:
            if y < 25 * mm:
                pdf.showPage()
                y = height - 30 * mm
            pdf.drawString(25 * mm, y, cc)
            y -= 4.5 * mm

    # Footer
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawCentredString(width / 2, 12 * mm,
                          f"System-generated by MOEN-IMS — Release event {ctx['code']} — "
                          f"Validate the scanned signed copy by checking the QR code.")

    pdf.save()
    buffer.seek(0)
    return ContentFile(buffer.getvalue(), name=f"letter_{ctx['code']}.pdf")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_memo_context(release_letter):
    """Pull the variable substitution data for the memo template.

    Per-event overrides on the ReleaseLetter row win over the default
    Signatory lookup, so an acting officer's name + title can be set at
    generation time without a code deploy.
    """
    from Inventory.models import Signatory

    signatory = (
        getattr(release_letter, 'memo_signatory_override', None)
        or Signatory.for_release_memo()
    )
    orders = release_letter.material_orders.all() if release_letter.pk else []
    first_order = orders[0] if orders else None

    to_line = (getattr(release_letter, 'memo_to_override', '') or 'CHIEF DIRECTOR').upper()
    default_from = (signatory.title if signatory else 'DIRECTOR, POWER')
    from_line = (getattr(release_letter, 'memo_from_override', '') or default_from).upper()

    return {
        'code': release_letter.code or '(pending)',
        'date': timezone.now().strftime('%d %B %Y').upper(),
        'memo_to': to_line,
        'memo_from': from_line,
        'memo_subject': _build_subject(release_letter, orders),
        'memo_signatory_name': signatory.name if signatory else '',
        'memo_signatory_title': '',  # FROM line already shows the title
        'first_order': first_order,
        'orders': orders,
        'project_type': release_letter.project_type or 'SHEP',
    }


def _build_letter_context(release_letter):
    """Pull the variable substitution data for the release letter template.

    Honours the per-event letter_signatory_override the same way the memo
    context does.
    """
    from Inventory.models import Signatory

    signatory = (
        getattr(release_letter, 'letter_signatory_override', None)
        or Signatory.for_release_letter()
    )
    orders = release_letter.material_orders.all() if release_letter.pk else []

    return {
        'code': release_letter.code or '(pending)',
        'date': timezone.now().strftime('%d %B %Y').upper(),
        'letter_subject': _build_subject(release_letter, orders).upper(),
        'letter_signatory_name': signatory.name if signatory else '',
        'letter_signatory_title': signatory.title if signatory else 'CHIEF DIRECTOR',
        'letter_signatory_signs_for': signatory.signs_for if signatory else 'HON. MINISTER',
        'orders': orders,
        'project_type': release_letter.project_type or 'SHEP',
        'cc_list': _build_cc_list(release_letter, orders),
    }


def _build_subject(release_letter, orders):
    """Compose a subject line from the materials and locations.

    Rules:
      - Single line item: keep the verbose "RELEASE OF 200 BAGS PORTLAND
        CEMENT AT ABOKOBI" wording (works for one-line releases).
      - Multi-line: classify line items into "poles" vs "other electrical
        materials" and emit ELECTRICAL MATERIALS / ELECTRICAL POLES /
        ELECTRICAL MATERIALS AND ELECTRICAL POLES accordingly.
      - Locations: list every distinct community on the release event,
        capped at 4 names with an "AND N OTHERS" suffix when more exist.
    """
    if not orders:
        return release_letter.title or "REQUEST FOR RELEASE OF MATERIALS"

    order_list = list(orders) if not isinstance(orders, list) else orders
    if not order_list:
        return release_letter.title or "REQUEST FOR RELEASE OF MATERIALS"

    # Build the locations phrase from every unique community on the event.
    seen, locs = set(), []
    for o in order_list:
        loc = (o.community or o.district or '').strip()
        if loc and loc not in seen:
            seen.add(loc)
            locs.append(loc.upper())
    if not locs:
        location_phrase = ''
    elif len(locs) == 1:
        location_phrase = f" AT {locs[0]}"
    else:
        head = locs[:4]
        extra = len(locs) - len(head)
        joined = ', '.join(head[:-1]) + f" AND {head[-1]}" if len(head) > 1 else head[0]
        if extra > 0:
            joined += f" AND {extra} OTHER{'S' if extra > 1 else ''}"
        location_phrase = f" AT {joined}"

    if len(order_list) == 1:
        first = order_list[0]
        qty = first.quantity
        unit = first.unit.name if first.unit_id else 'no.'
        material = first.name or 'materials'
        return (
            f"REQUEST FOR RELEASE OF {qty}{unit.upper()} {material.upper()}"
            f"{location_phrase}"
        )

    # Multi-line: classify into poles vs other electrical materials.
    has_pole = any('POLE' in (o.name or '').upper() for o in order_list)
    has_other = any('POLE' not in (o.name or '').upper() for o in order_list)
    if has_pole and has_other:
        materials_phrase = "ELECTRICAL MATERIALS AND ELECTRICAL POLES"
    elif has_pole:
        materials_phrase = "ELECTRICAL POLES"
    else:
        materials_phrase = "ELECTRICAL MATERIALS"

    return f"REQUEST FOR RELEASE OF {materials_phrase}{location_phrase}"


def _build_memo_body(release_letter, ctx):
    """Compose the body paragraphs of the approval memo.

    Single-line releases keep the verbose original phrasing. Bulk releases
    swap that for "release of N items as detailed in the Schedule of
    Materials below" — the table itself is drawn after the body by
    `_draw_materials_schedule`.
    """
    orders = list(ctx.get('orders') or [])
    project_type = ctx.get('project_type', 'SHEP')

    if not orders:
        return [
            "We write to seek approval for the release of materials from the Ministry's "
            "Materials Management Unit (MMU) for the project listed in this release event.",
            "We have attached the release letter for sign-off.",
        ]

    first_order = orders[0]
    location = first_order.community or first_order.district or 'the project site'

    if project_type == 'SHEP':
        beneficiary_phrase = f"the Self-Help Electrification Project (SHEP) at {location}"
    elif project_type == 'COST':
        beneficiary_phrase = f"the Cost Sharing programme at {location}"
    elif project_type == 'STREET':
        beneficiary_phrase = f"the Streetlights programme at {location}"
    else:
        beneficiary_phrase = f"the project at {location}"

    if len(orders) == 1:
        qty = first_order.quantity
        unit = first_order.unit.name if first_order.unit_id else 'no.'
        material = first_order.name or 'materials'
        opening = (
            f"We write to seek approval for the release of {qty} {unit} of {material} "
            f"from the Ministry's Materials Management Unit (MMU) for {beneficiary_phrase}."
        )
    else:
        opening = (
            f"We write to seek approval for the release of {len(orders)} items "
            f"of materials, as detailed in the Schedule of Materials below, "
            f"from the Ministry's Materials Management Unit (MMU) for {beneficiary_phrase}."
        )

    return [
        opening,
        "MMU has confirmed the availability of the materials in stock.",
        f"A release letter to MMU is attached for sign-off, referenced "
        f"under release event {ctx['code']}.",
    ]


def _build_letter_body(release_letter, ctx):
    """Compose the body paragraphs of the release letter to MMU.

    On a single-line release we keep the directive verbose with the
    material, quantity, unit, and consignee inline. For bulk releases we
    redirect the reader to the Schedule of Materials table that follows.
    """
    orders = list(ctx.get('orders') or [])
    project_type = ctx.get('project_type', 'SHEP')

    if not orders:
        return [
            "I refer to the stock of materials at the Materials Management Unit (MMU), Kpone-Tema.",
            "You are hereby directed to release the materials listed under "
            f"release event {ctx['code']} to the consignee identified in our records.",
        ]

    first = orders[0]
    region = first.region or ''
    district = first.district or ''
    community = first.community or 'the project site'

    location_phrase = community
    if district:
        location_phrase += f" in the {district}"
    if region:
        location_phrase += f", {region} Region"

    stock_phrase = {
        'SHEP': 'SHEP materials/equipment',
        'COST': 'Cost-sharing materials',
        'STREET': 'Streetlights materials',
    }.get(project_type, 'materials')

    consignee_phrase = first.consultant or first.contractor or 'the project consignee'

    if len(orders) == 1:
        qty = first.quantity
        unit = first.unit.name if first.unit_id else 'no.'
        material = first.name or 'materials'
        directive = (
            f"You are hereby directed to release via the Ministry's Inventory Management System (IMS), "
            f"{qty} {unit} of {material} to {consignee_phrase}, "
            f"to carry out the installation work at {location_phrase}."
        )
    else:
        # Distinct delivery locations across the batch (capped to keep the
        # paragraph readable; the table carries the full detail).
        seen, locs = set(), []
        for o in orders:
            loc = (o.community or o.district or '').strip()
            if loc and loc not in seen:
                seen.add(loc)
                locs.append(loc)
            if len(locs) >= 3:
                break
        more = max(0, len(set((o.community or o.district or '').strip()
                              for o in orders if (o.community or o.district))) - len(locs))
        location_clause = ', '.join(locs)
        if more > 0:
            location_clause += f" and {more} other location{'s' if more > 1 else ''}"
        directive = (
            f"You are hereby directed to release via the Ministry's Inventory Management System (IMS) "
            f"the {len(orders)} items of materials enumerated in the Schedule of Materials below "
            f"to {consignee_phrase}, to carry out the installation work at {location_clause or location_phrase}."
        )

    return [
        f"I refer to the stock of {stock_phrase} at the Materials Management Unit (MMU), Kpone-Tema.",
        directive,
        f"We are by a copy of this letter requesting {consignee_phrase} and the relevant local stakeholders "
        f"to contact you for the release of the materials for installation.",
    ]


def _draw_materials_schedule(pdf, orders, y, width):
    """Draw a "Schedule of Materials" table for every order in the release.

    Returns the y-coordinate below the table. Paginates when it runs out
    of vertical room. Used by both the memo and the release letter so the
    signed paperwork enumerates every authorised line item — the previous
    behaviour was to print only the first row even on bulk releases.
    """
    from reportlab.lib.units import mm

    order_list = list(orders) if not isinstance(orders, list) else orders
    if not order_list:
        return y

    left = 20 * mm
    right = width - 20 * mm
    usable_w = right - left

    # Column widths: Material wide, Qty/Unit narrow, Community medium.
    col_material = int(usable_w * 0.46)
    col_qty      = int(usable_w * 0.13)
    col_unit     = int(usable_w * 0.13)
    col_loc      = usable_w - col_material - col_qty - col_unit

    # Heading
    pdf.setFont(BODY_FONT_BOLD, 12)
    pdf.drawString(left, y, "Schedule of Materials")
    y -= 6 * mm

    # Header row
    header_y = y
    pdf.setFillGray(0.92)
    pdf.rect(left, header_y - 4.8 * mm, usable_w, 6.5 * mm, stroke=0, fill=1)
    pdf.setFillGray(0)
    pdf.setFont(BODY_FONT_BOLD, 10)
    pdf.drawString(left + 2 * mm, header_y - 3.2 * mm, "Material")
    pdf.drawRightString(left + col_material + col_qty - 2 * mm, header_y - 3.2 * mm, "Qty")
    pdf.drawString(left + col_material + col_qty + 2 * mm, header_y - 3.2 * mm, "Unit")
    pdf.drawString(left + col_material + col_qty + col_unit + 2 * mm, header_y - 3.2 * mm, "Community")
    y = header_y - 6.5 * mm

    pdf.setFont(BODY_FONT, 10)
    row_h = 5.5 * mm
    total_qty_by_unit = {}

    for o in order_list:
        if y < 35 * mm:
            pdf.showPage()
            y = pdf._pagesize[1] - 30 * mm
            pdf.setFont(BODY_FONT_BOLD, 10)
            pdf.drawString(left, y, "Schedule of Materials (continued)")
            y -= 7 * mm
            pdf.setFont(BODY_FONT, 10)

        material = (o.name or '')[:60]
        qty = o.quantity
        unit = o.unit.name if o.unit_id else ''
        loc = (o.community or o.district or '')[:32]

        pdf.drawString(left + 2 * mm, y, material)
        pdf.drawRightString(left + col_material + col_qty - 2 * mm, y, f"{qty}")
        pdf.drawString(left + col_material + col_qty + 2 * mm, y, unit)
        pdf.drawString(left + col_material + col_qty + col_unit + 2 * mm, y, loc)
        y -= row_h

        # Tally per-unit totals so the footer reflects mixed-unit batches.
        try:
            total_qty_by_unit[unit or '—'] = total_qty_by_unit.get(unit or '—', 0) + float(qty)
        except (TypeError, ValueError):
            pass

    # Bottom rule + totals
    pdf.line(left, y + 1 * mm, right, y + 1 * mm)
    y -= 4 * mm
    pdf.setFont(BODY_FONT_BOLD, 10)
    totals_phrase = ', '.join(
        f"{('%g' % v)} {k}" for k, v in total_qty_by_unit.items()
    )
    if totals_phrase:
        pdf.drawString(left + 2 * mm, y, f"Total: {totals_phrase} across {len(order_list)} line items.")
        y -= row_h
    return y


def _build_cc_list(release_letter, orders):
    """Build the cc distribution list. Per-project defaults plus the consignee."""
    project_type = release_letter.project_type or 'SHEP'

    base = [
        "The Hon. Minister, MoEn&GT",
        "The Hon. Deputy Minister, MoEn&GT",
        "Ag. Director, Power, MoEn&GT",
        "Director, Internal Audit Unit, MoEn&GT",
    ]
    if project_type == 'SHEP':
        base.append("Ag. Managing Director, NEDCo / ECG (as applicable)")
    elif project_type == 'COST':
        base.append("Hon. Member of Parliament (constituency)")
    elif project_type == 'STREET':
        base.append("Hon. Member of Parliament (constituency)")
        base.append("Metropolitan / Municipal / District Chief Executive (MMDCE)")

    base.append("The Beneficiary")
    return base


def _wrap_text(text, max_width, font_size):
    """Crude word-wrap. Returns a list of lines that fit within max_width."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    if not text:
        return ['']
    words = str(text).split()
    if not words:
        return ['']
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = current + ' ' + word
        if stringWidth(candidate, "Helvetica", font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _render_qr_code(payload):
    """Render the release code as a QR code. Returns a ReportLab ImageReader
    object, or None if qrcode library isn't available (degrades to no QR)."""
    try:
        import qrcode
        from reportlab.lib.utils import ImageReader
    except ImportError:
        logger.warning("qrcode library not installed; release letter will lack QR code.")
        return None

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=1,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return ImageReader(buffer)
