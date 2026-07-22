"""
Waybill PDF generation + public QR verification.

Phase 1 rewrite: canvas-based rendering matching the release letter style
(pdf_generator.py).  The QR code encodes the waybill number directly so
anyone can scan and verify authenticity without logging in.
"""

import io
import logging
import os

from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from django_ratelimit.decorators import ratelimit

from ..models import (
    MaterialOrder, MaterialOrderAudit, MaterialTransport, ReleaseLetter,
    SiteReceipt, Transporter, TransportVehicle,
)
from ..utils import is_store_officer, is_superuser, is_schedule_officer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers (font registration, logo, QR, text wrap)
# Imported from the release-letter generator so both document families
# share identical rendering primitives.
# ---------------------------------------------------------------------------
from .pdf_generator import (
    BODY_FONT, BODY_FONT_BOLD,
    _find_logo_path, _render_qr_code, _wrap_text,
)


# ---------------------------------------------------------------------------
# Colour palette — matches the system UI (index.css tokens)
# ---------------------------------------------------------------------------
_PRIMARY = '#2e7d32'
_PRIMARY_DARK = '#1b5e20'
_HEADER_BG = '#1e293b'
_TINT = '#e8f5e9'
_SURFACE = '#ffffff'


def _tricolor_bar(pdf, width, page_height, bar_h=2.5 * 1):
    """Draw the Ghana tricolor accent bar (red / yellow / green) at the top of the page."""
    from reportlab.lib.units import mm
    bar_h = bar_h * mm
    y = page_height - bar_h  # top of page
    seg_w = width / 3
    pdf.setFillColorRGB(0.76, 0.15, 0.15)
    pdf.rect(0, y, seg_w, bar_h, stroke=0, fill=1)
    pdf.setFillColorRGB(0.85, 0.65, 0.13)
    pdf.rect(seg_w, y, seg_w, bar_h, stroke=0, fill=1)
    pdf.setFillColorRGB(0.18, 0.49, 0.20)
    pdf.rect(seg_w * 2, y, seg_w, bar_h, stroke=0, fill=1)


def _section_title(pdf, x, y, title, right_edge):
    """Draw a bold green section title + thin gray divider below it."""
    from reportlab.lib.units import mm
    pdf.setFont(BODY_FONT_BOLD, 11)
    pdf.setFillColorRGB(0.10, 0.36, 0.16)  # dark forest green
    pdf.drawString(x, y, title)
    pdf.setFillColorRGB(0, 0, 0)
    y -= 2 * mm
    pdf.setStrokeColorRGB(0.82, 0.82, 0.82)
    pdf.setLineWidth(0.5)
    pdf.line(x, y, right_edge, y)
    y -= 5 * mm
    return y


def _label_value_row(pdf, x, y, label, value, label_w=45 * 1, font_size=9):
    """Draw a single label: value row.  Returns new y."""
    from reportlab.lib.units import mm
    pdf.setFont(BODY_FONT_BOLD, font_size)
    pdf.drawString(x, y, label)
    pdf.setFont(BODY_FONT, font_size)
    pdf.drawString(x + label_w * mm, y, str(value)[:70])
    y -= 6.5 * mm
    return y


# ---------------------------------------------------------------------------
# Stamp / signature lookup  (single implementation, replaces 3 copies)
# ---------------------------------------------------------------------------
def _get_user_stamp(user):
    """Return (stamp_image_path_or_None, name, date_string) for *user*."""
    if user is None:
        return None, '', ''

    from ..models import Profile

    name = (user.get_full_name() or user.username).upper()
    date_str = ''

    digital_dir = os.path.join(settings.MEDIA_ROOT, 'digital_signatures')
    if not os.path.exists(digital_dir):
        digital_dir = os.path.join(settings.MEDIA_ROOT, 'digital signatures')

    for ext in ('png', 'jpg', 'jpeg'):
        for pattern in (f"{user.username}.{ext}", f"{user.id}.{ext}"):
            path = os.path.join(digital_dir, pattern)
            if os.path.exists(path):
                return path, name, date_str

    try:
        profile = Profile.objects.filter(user=user).first()
        if profile and hasattr(profile, 'generate_digital_stamp_png'):
            path = profile.generate_digital_stamp_png()
            if path and os.path.exists(path):
                return path, name, date_str
    except Exception:
        pass

    return None, name, date_str


# ---------------------------------------------------------------------------
# Signature rows builder
# ---------------------------------------------------------------------------
def _build_signature_rows(transport):
    """Return 4 tuples: (role_main, role_sub, name, sig_date[, stamp_path])."""
    order = transport.material_order

    # Store Officer
    so_user = None
    if order:
        so_user = order.processed_by or order.assigned_to or order.created_by
    so_stamp, so_name, _ = _get_user_stamp(so_user)
    so_date = ''
    if order and order.processed_at:
        so_date = order.processed_at.strftime('%d %B %Y')
    elif transport.date_dispatched:
        so_date = transport.date_dispatched.strftime('%d %B %Y')

    # Store Manager
    sm_user = None
    if order and order.assigned_by:
        sm_user = order.assigned_by
    elif transport.created_by:
        sm_user = transport.created_by
    sm_stamp, sm_name, _ = _get_user_stamp(sm_user)
    sm_date = ''
    if order and order.assigned_at:
        sm_date = order.assigned_at.strftime('%d %B %Y')
    elif transport.date_dispatched:
        sm_date = transport.date_dispatched.strftime('%d %B %Y')

    # Driver
    driver_name = transport.driver_name or ''
    veh = transport.vehicle
    driver_sub = veh.registration_number if veh else ''
    driver_date = transport.date_dispatched.strftime('%d %B %Y') if transport.date_dispatched else ''

    # Recipient / Consultant
    rcpt_user = None
    if hasattr(transport, 'site_receipt') and transport.site_receipt:
        rcpt_user = transport.site_receipt.received_by
    rcpt_stamp, rcpt_name, _ = _get_user_stamp(rcpt_user)
    if not rcpt_name and transport.consultant:
        rcpt_name = transport.consultant
    rcpt_date = ''
    if hasattr(transport, 'site_receipt') and transport.site_receipt and transport.site_receipt.received_date:
        rcpt_date = transport.site_receipt.received_date.strftime('%d %B %Y')

    return [
        ('Issued By', 'Store Officer', so_name, so_date, so_stamp),
        ('Approved By', 'Store Manager', sm_name, sm_date, sm_stamp),
        ('Picked Up By', 'Driver', driver_name, driver_date, driver_sub),
        ('Received By', 'Acknowledgement Form', rcpt_name, rcpt_date, rcpt_stamp),
    ]


def _build_ref_ids(transport):
    """Return (ack_ref, waybill_ref) for the two pages."""
    wb = transport.waybill_number or ''
    # wb format: WB-YYYYMMDD-NNNN
    parts = wb.split('-')
    if len(parts) == 3:
        date_part = parts[1]  # e.g. 20260722
        seq_part = parts[2]   # e.g. 0002
        year = date_part[:4]
        ack_ref = f'WB-GH-{year}-{seq_part}-ACK'
        waybill_ref = f'{wb}-TRANS'
    else:
        ack_ref = f'WB-GH-ACK-{transport.id}'
        waybill_ref = f'{wb}-TRANS' if wb else f'WB-TRANS-{transport.id}'
    return ack_ref, waybill_ref


def _draw_makeshift_stamp(pdf, cx, cy, radius, name):
    """Draw a circular makeshift stamp with driver name and 'PICKED UP' text."""
    import math
    from reportlab.lib.units import mm as _mm

    pdf.saveState()

    # Outer circle — dark green
    pdf.setStrokeColorRGB(0.10, 0.36, 0.16)
    pdf.setLineWidth(1.2)
    pdf.circle(cx, cy, radius, stroke=1, fill=0)

    # Inner circle
    pdf.setLineWidth(0.4)
    pdf.circle(cx, cy, radius - 1.5 * _mm, stroke=1, fill=0)

    # "PICKED UP" centered
    pdf.setFont(BODY_FONT_BOLD, 6)
    pdf.setFillColorRGB(0.10, 0.36, 0.16)
    pdf.drawCentredString(cx, cy + 1 * _mm, "PICKED UP")
    pdf.setFont(BODY_FONT, 4.5)
    pdf.drawCentredString(cx, cy - 2.5 * _mm, "BY DRIVER")

    # Name curved around the top of the circle
    display_name = (name or 'DRIVER').upper()
    if len(display_name) > 24:
        display_name = display_name[:22] + '..'

    n_chars = len(display_name)
    if n_chars > 0:
        start_angle = 150
        end_angle = 30
        total_arc = (360 - start_angle) + end_angle
        char_arc = total_arc / max(n_chars, 1)
        text_radius = radius - 3.5 * _mm

        for i, ch in enumerate(display_name):
            angle_deg = start_angle + i * char_arc
            angle_rad = math.radians(angle_deg)
            tx = cx + text_radius * math.cos(angle_rad)
            ty = cy + text_radius * math.sin(angle_rad)

            pdf.saveState()
            pdf.translate(tx, ty)
            pdf.rotate(angle_deg - 90)
            pdf.setFont(BODY_FONT_BOLD, 4.5)
            pdf.setFillColorRGB(0.10, 0.36, 0.16)
            pdf.drawCentredString(0, 0, ch)
            pdf.restoreState()

    pdf.restoreState()


def _draw_signature_table(pdf, left, right, y, rows_data, from_page=1):
    """Draw the 4-column signature table.  Returns y after table."""
    from reportlab.lib.units import mm

    usable = right - left
    col_role = int(usable * 0.20)
    col_name = int(usable * 0.25)
    col_sig = int(usable * 0.30)
    col_date = usable - col_role - col_name - col_sig

    # Header row
    hdr_h = 7 * mm
    pdf.setFillColorRGB(0.11, 0.16, 0.23)  # dark navy
    pdf.rect(left, y - hdr_h, usable, hdr_h, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont(BODY_FONT_BOLD, 7)
    cx = left + 3 * mm
    for hdr, cw in [('ROLE', col_role), ('NAME', col_name),
                     ('SIGNATURE / STAMP', col_sig), ('DATE', col_date)]:
        pdf.drawString(cx, y - 4.5 * mm, hdr)
        cx += cw
    pdf.setFillColorRGB(0, 0, 0)
    y -= hdr_h + 1 * mm

    row_h = 16 * mm
    for idx, row in enumerate(rows_data):
        if y - row_h < 25 * mm:
            pdf.showPage()
            # Draw tricolor bar on new page
            _tricolor_bar(pdf, pdf._pagesize[0], pdf._pagesize[1])
            y = pdf._pagesize[1] - 20 * mm
            y -= row_h

        role_main = row[0]
        role_sub = row[1]
        name = row[2]
        sig_date = row[3]
        extra = row[4] if len(row) > 4 else ''

        # For Picked Up By, extra is vehicle reg (shown under name)
        # For others, extra is stamp image path (rendered in signature box)
        stamp_path = None
        name_sub = ''
        if role_main == 'Picked Up By':
            name_sub = extra
        elif extra:
            stamp_path = extra if os.path.isfile(str(extra)) else None

        pdf.setFillColorRGB(0, 0, 0)

        cx = left + 3 * mm
        # Role column — main label bold, sub-label smaller gray
        pdf.setFont(BODY_FONT_BOLD, 8)
        pdf.drawString(cx, y - 4 * mm, role_main)
        pdf.setFont(BODY_FONT, 7)
        pdf.setFillColorRGB(0.45, 0.45, 0.45)
        pdf.drawString(cx, y - 8 * mm, f'({role_sub})')
        pdf.setFillColorRGB(0, 0, 0)
        cx += col_role

        # Name column — name + optional sub-line (vehicle reg)
        pdf.setFont(BODY_FONT, 8)
        pdf.drawString(cx, y - 4 * mm, (name or '')[:40])
        if name_sub:
            pdf.setFont(BODY_FONT, 7)
            pdf.setFillColorRGB(0.45, 0.45, 0.45)
            pdf.drawString(cx, y - 8.5 * mm, name_sub)
            pdf.setFillColorRGB(0, 0, 0)
        cx += col_name

        # Signature / Stamp — bordered box with stamp image or "Digitally Verified" seal
        box_w = col_sig - 6 * mm
        box_h = row_h - 5 * mm
        box_x = cx + 1 * mm
        box_y = y - row_h + 2.5 * mm
        # White fill for clean look
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(box_x, box_y, box_w, box_h, stroke=0, fill=1)
        pdf.setStrokeColorRGB(0.78, 0.78, 0.82)
        pdf.setLineWidth(0.4)
        pdf.rect(box_x, box_y, box_w, box_h, stroke=1, fill=0)

        if stamp_path:
            # Render actual stamp image
            try:
                stamp_pad = 2 * mm
                pdf.drawImage(stamp_path, box_x + stamp_pad, box_y + stamp_pad,
                              width=box_w - stamp_pad * 2, height=box_h - stamp_pad * 2,
                              preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
        elif role_main == 'Picked Up By' and name:
            # Makeshift circular stamp for driver (no user account)
            _draw_makeshift_stamp(pdf, box_x + box_w / 2, box_y + box_h / 2,
                                  min(box_w, box_h) / 2 - 1.5 * mm, name)
        else:
            # "Digitally Verified" text seal when no stamp
            seal_cx = box_x + box_w / 2
            seal_cy = box_y + box_h / 2
            pdf.setFont(BODY_FONT_BOLD, 5.5)
            pdf.setFillColorRGB(0.10, 0.36, 0.16)
            pdf.drawCentredString(seal_cx, seal_cy + 1.5 * mm, "DIGITALLY")
            pdf.drawCentredString(seal_cx, seal_cy - 2 * mm, "VERIFIED")
            pdf.setFillColorRGB(0, 0, 0)
        cx += col_sig

        # Date
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont(BODY_FONT, 8)
        pdf.drawString(cx, y - 4 * mm, sig_date or '')

        y -= row_h

    # Outer border around entire table
    table_top = y + row_h * len(rows_data) + (hdr_h + 1 * mm)
    pdf.setStrokeColorRGB(0.82, 0.82, 0.82)
    pdf.setLineWidth(0.5)
    pdf.rect(left, y + 1 * mm, usable, table_top - y - 1 * mm, stroke=1, fill=0)

    return y


# ---------------------------------------------------------------------------
# Page 1  —  ACKNOWLEDGEMENT FORM
# ---------------------------------------------------------------------------
def _draw_acknowledgement(pdf, width, height, transport, all_transports, copy_label):
    """Render the first page: Acknowledgement Form."""
    from reportlab.lib.units import mm

    margin = 25 * mm
    left = margin
    right = width - margin
    usable = right - left

    # ── Tricolor accent bar ────────────────────────────────────────────
    _tricolor_bar(pdf, width, height)
    y = height - 12 * mm

    # ── Logo in pale green box ─────────────────────────────────────────
    logo_path = _find_logo_path()
    logo_size = 18 * mm
    logo_box_pad = 4 * mm
    logo_box_size = logo_size + logo_box_pad * 2
    logo_box_x = (width - logo_box_size) / 2
    logo_box_y = y - logo_box_size
    # Pale green background
    pdf.setFillColorRGB(0.91, 0.96, 0.91)
    pdf.rect(logo_box_x, logo_box_y, logo_box_size, logo_box_size,
             stroke=0, fill=1)
    pdf.setFillColorRGB(0, 0, 0)
    # Draw logo centered in box
    if logo_path:
        try:
            logo_x = (width - logo_size) / 2
            logo_y = logo_box_y + logo_box_pad
            pdf.drawImage(logo_path, logo_x, logo_y, width=logo_size, height=logo_size,
                          preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
    y = logo_box_y - 5 * mm

    # ── Eyebrow text ──────────────────────────────────────────────────
    pdf.setFont(BODY_FONT_BOLD, 7)
    pdf.setFillColorRGB(0.35, 0.35, 0.35)
    pdf.drawCentredString(width / 2, y,
                          "M I N I S T R Y   O F   E N E R G Y   A N D   G R E E N   T R A N S I T I O N")
    pdf.setFillColorRGB(0, 0, 0)
    y -= 7 * mm

    # ── Main heading ──────────────────────────────────────────────────
    pdf.setFont(BODY_FONT_BOLD, 20)
    pdf.setFillColorRGB(0.10, 0.36, 0.16)
    pdf.drawCentredString(width / 2, y, "ACKNOWLEDGEMENT FORM")
    pdf.setFillColorRGB(0, 0, 0)
    y -= 5 * mm

    # ── Thin divider ──────────────────────────────────────────────────
    pdf.setStrokeColorRGB(0.82, 0.82, 0.82)
    pdf.setLineWidth(0.5)
    pdf.line(left, y, right, y)
    y -= 7 * mm

    # ── Meta row: Waybill No + Date ───────────────────────────────────
    pdf.setFont(BODY_FONT_BOLD, 9)
    pdf.drawString(left, y, "Waybill No:")
    pdf.setFont(BODY_FONT, 9)
    pdf.drawString(left + 25 * mm, y, transport.waybill_number or 'N/A')
    pdf.setFont(BODY_FONT_BOLD, 9)
    pdf.drawString(right - 40 * mm, y, "Date:")
    pdf.setFont(BODY_FONT, 9)
    date_str = (transport.date_dispatched or timezone.now()).strftime('%d %B %Y')
    pdf.drawString(right - 28 * mm, y, date_str)
    y -= 9 * mm

    # ── Store / Issuing Information ───────────────────────────────────
    y = _section_title(pdf, left, y, "Store / Issuing Information", right)

    order = transport.material_order
    storekeeper = None
    if order:
        storekeeper = order.processed_by or order.assigned_to or order.created_by

    wh = getattr(transport, 'warehouse', None)
    if wh is None and order:
        wh = order.warehouse

    if wh:
        y = _label_value_row(pdf, left, y, 'Warehouse:', wh.name)
        if wh.location:
            y = _label_value_row(pdf, left, y, 'Location:', wh.location)
    if storekeeper:
        y = _label_value_row(pdf, left, y, 'Storekeeper:',
                             storekeeper.get_full_name() or storekeeper.username)
    y -= 5 * mm

    # ── Destination / Recipient Information ────────────────────────────
    y = _section_title(pdf, left, y, "Destination / Recipient Information", right)

    dest_rows = []
    if transport.recipient:
        dest_rows.append(('Recipient:', str(transport.recipient)))
    if getattr(transport, 'consultant', None):
        dest_rows.append(('Consultant:', transport.consultant))
    if getattr(transport, 'region', None):
        dest_rows.append(('Region:', transport.region))
    if getattr(transport, 'district', None):
        dest_rows.append(('District:', transport.district))
    if getattr(transport, 'community', None):
        dest_rows.append(('Community:', transport.community))
    if getattr(transport, 'package_number', None):
        dest_rows.append(('Package No:', transport.package_number))

    for label, value in dest_rows:
        y = _label_value_row(pdf, left, y, label, value)
    if not dest_rows:
        y = _label_value_row(pdf, left, y, 'Recipient:', 'N/A')
    y -= 5 * mm

    # ── Signatures & Endorsements ─────────────────────────────────────
    y = _section_title(pdf, left, y, "Signatures & Endorsements", right)

    rows_data = _build_signature_rows(transport)
    y = _draw_signature_table(pdf, left, right, y, rows_data)


# ---------------------------------------------------------------------------
# Page 2  —  MATERIAL WAYBILL
# ---------------------------------------------------------------------------
def _draw_waybill_page(pdf, width, height, transport, all_transports,
                       copy_label, download_count):
    """Render the second page: full Material Waybill."""
    from reportlab.lib.units import mm

    margin = 25 * mm
    left = margin
    right = width - margin
    usable = right - left

    # ── Tricolor accent bar ────────────────────────────────────────────
    _tricolor_bar(pdf, width, height)
    y = height - 2.5 * mm

    # ── Green header banner ───────────────────────────────────────────
    banner_h = 42 * mm
    banner_y = y - banner_h
    pdf.setFillColorRGB(0.10, 0.36, 0.16)  # dark forest green
    pdf.rect(0, banner_y, width, banner_h, stroke=0, fill=1)

    # Logo in white box (left side)
    logo_path = _find_logo_path()
    if logo_path:
        logo_box_size = 24 * mm
        logo_box_x = left + 2 * mm
        logo_box_y = banner_y + (banner_h - logo_box_size) / 2
        pdf.setFillColorRGB(1, 1, 1)
        pdf.rect(logo_box_x, logo_box_y, logo_box_size, logo_box_size,
                 stroke=0, fill=1)
        try:
            logo_pad = 2 * mm
            pdf.drawImage(logo_path, logo_box_x + logo_pad, logo_box_y + logo_pad,
                          width=logo_box_size - logo_pad * 2,
                          height=logo_box_size - logo_pad * 2,
                          preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

    # Text centered horizontally and vertically in banner
    txt_top = banner_y + (banner_h + 13 * mm) / 2
    pdf.setFillColorRGB(1, 1, 1)

    pdf.setFont(BODY_FONT_BOLD, 18)
    pdf.drawCentredString(width / 2, txt_top, "MATERIAL WAYBILL")

    pdf.setFont(BODY_FONT, 9)
    pdf.drawCentredString(width / 2, txt_top - 7 * mm,
                   "MINISTRY OF ENERGY AND GREEN TRANSITION OF GHANA")

    pdf.setFont(BODY_FONT_BOLD, 6.5)
    pdf.drawCentredString(width / 2, txt_top - 13 * mm,
                   "I N V E N T O R Y   M A N A G E M E N T   S Y S T E M")

    pdf.setFillColorRGB(0, 0, 0)
    y = banner_y - 12 * mm

    # ── Waybill Information section ───────────────────────────────────
    y = _section_title(pdf, left, y, "Waybill Information", right)

    # Two-column layout: left = info box, right = QR code
    info_box_w = usable * 0.62
    qr_area_w = usable - info_box_w - 6 * mm

    # Left: tinted info box with 2×2 grid
    info_h = 16 * mm
    info_x = left
    info_y = y
    pdf.setFillColorRGB(0.94, 0.95, 0.97)  # pale lavender-gray
    pdf.rect(info_x, info_y - info_h, info_box_w, info_h, stroke=0, fill=1)
    pdf.setStrokeColorRGB(0.82, 0.82, 0.82)
    pdf.setLineWidth(0.4)
    pdf.rect(info_x, info_y - info_h, info_box_w, info_h, stroke=1, fill=0)

    # 2×2 grid inside the box
    grid_pad = 2 * mm
    cell_w = (info_box_w - grid_pad * 2) / 2
    cell_h = (info_h - grid_pad * 2) / 2
    info_pairs = [
        ('WAYBILL NUMBER', transport.waybill_number or 'N/A'),
        ('SHIPMENT TYPE', 'Bulk Shipment' if len(all_transports) > 1 else 'Single Shipment'),
        ('TOTAL MATERIALS', f'{len(all_transports)} Item{"s" if len(all_transports) != 1 else ""}'),
        ('DATE DISPATCHED', (transport.date_dispatched or timezone.now()).strftime('%d %B %Y')),
    ]
    for i, (lbl, val) in enumerate(info_pairs):
        col = i % 2
        row = i // 2
        cx = info_x + grid_pad + col * cell_w
        cy = info_y - grid_pad - row * cell_h
        pdf.setFont(BODY_FONT_BOLD, 6)
        pdf.setFillColorRGB(0.45, 0.45, 0.45)
        pdf.drawString(cx, cy, lbl)
        pdf.setFont(BODY_FONT, 8)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.drawString(cx, cy - 3.5 * mm, val)

    # Right: QR code in bordered box
    qr_x = left + info_box_w + 6 * mm
    qr_box_size = min(qr_area_w, info_h - 2 * mm)
    qr_box_y = info_y - info_h + 1 * mm
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(qr_x, qr_box_y, qr_box_size, info_h - 2 * mm, stroke=0, fill=1)
    pdf.setStrokeColorRGB(0.82, 0.82, 0.82)
    pdf.rect(qr_x, qr_box_y, qr_box_size, info_h - 2 * mm, stroke=1, fill=0)

    qr_payload = transport.waybill_number or str(transport.id)
    qr_img = _render_qr_code(qr_payload)
    if qr_img:
        qr_inner = qr_box_size - 6 * mm
        qr_img_x = qr_x + (qr_box_size - qr_inner) / 2
        qr_img_y = qr_box_y + (info_h - 2 * mm - qr_inner) / 2
        pdf.drawImage(qr_img, qr_img_x, qr_img_y,
                      width=qr_inner, height=qr_inner, mask='auto')
    # Caption below QR
    pdf.setFont(BODY_FONT, 5.5)
    pdf.setFillColorRGB(0.45, 0.45, 0.45)
    pdf.drawCentredString(qr_x + qr_box_size / 2, qr_box_y - 4 * mm, qr_payload)
    pdf.setFillColorRGB(0, 0, 0)

    y = info_y - info_h - 8 * mm

    # ── Materials table ───────────────────────────────────────────────
    y = _section_title(pdf, left, y, "Materials on This Waybill", right)

    col_no = int(usable * 0.06)
    col_mname = int(usable * 0.34)
    col_code = int(usable * 0.16)
    col_qty = int(usable * 0.20)
    col_req = usable - col_no - col_mname - col_code - col_qty

    # Header
    hdr_h = 7 * mm
    pdf.setFillColorRGB(0.11, 0.16, 0.23)
    pdf.rect(left, y - hdr_h, usable, hdr_h, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont(BODY_FONT_BOLD, 7)
    cx = left + 2 * mm
    for hdr, cw in [('#', col_no), ('MATERIAL', col_mname), ('CODE', col_code),
                     ('QUANTITY', col_qty), ('REQUEST CODE', col_req)]:
        pdf.drawString(cx, y - 4.5 * mm, hdr)
        cx += cw
    pdf.setFillColorRGB(0, 0, 0)
    y -= hdr_h + 1 * mm

    row_h = 6.5 * mm
    for idx, t in enumerate(all_transports, 1):
        if y < 65 * mm:
            pdf.showPage()
            _tricolor_bar(pdf, width, height)
            y = height - 20 * mm

        if idx % 2 == 0:
            pdf.setFillColorRGB(0.97, 0.97, 0.98)
            pdf.rect(left, y - row_h, usable, row_h, stroke=0, fill=1)
        pdf.setFillColorRGB(0, 0, 0)

        pdf.setFont(BODY_FONT, 8)
        cx = left + 2 * mm
        pdf.drawString(cx, y - 3 * mm, str(idx))
        cx += col_no
        pdf.drawString(cx, y - 3 * mm, (t.material_name or '')[:50])
        cx += col_mname
        pdf.drawString(cx, y - 3 * mm, (t.material_code or 'N/A')[:20])
        cx += col_code
        # Quantity in bold green
        pdf.setFont(BODY_FONT_BOLD, 8)
        pdf.setFillColorRGB(0.10, 0.36, 0.16)
        pdf.drawString(cx, y - 3 * mm, f"{t.quantity} {t.unit or ''}")
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont(BODY_FONT, 8)
        cx += col_qty
        pdf.drawString(cx, y - 3 * mm,
                       (t.material_order.request_code if t.material_order else 'N/A')[:25])
        y -= row_h

    # Table border
    table_bottom = y + 1 * mm
    pdf.setStrokeColorRGB(0.82, 0.82, 0.82)
    pdf.setLineWidth(0.4)
    pdf.rect(left, table_bottom, usable,
             (hdr_h + 1 * mm + row_h * len(all_transports) if all_transports else hdr_h),
             stroke=1, fill=0)
    y -= 6 * mm

    # ── Two-column: Transporter + Destination ─────────────────────────
    half_w = (usable - 6 * mm) / 2
    left_col_x = left
    right_col_x = left + half_w + 6 * mm

    # Transporter (left)
    tx_y = _section_title(pdf, left_col_x, y, "Transporter Information", left_col_x + half_w)
    tx_info = [
        ('Transporter:', transport.transporter.name if transport.transporter else 'N/A'),
        ('Vehicle:', f"{transport.vehicle.registration_number} ({transport.vehicle.vehicle_type})" if transport.vehicle else 'N/A'),
        ('Driver Name:', transport.driver_name or 'N/A'),
        ('Driver Phone:', transport.driver_phone or 'N/A'),
    ]
    for label, value in tx_info:
        pdf.setFont(BODY_FONT, 8)
        pdf.drawString(left_col_x, tx_y, label)
        pdf.setFont(BODY_FONT_BOLD, 8)
        pdf.drawString(left_col_x + 28 * mm, tx_y, str(value)[:45])
        tx_y -= 5.5 * mm

    # Destination (right)
    dest_y = _section_title(pdf, right_col_x, y, "Destination Information", right)
    dest_info = [
        ('Recipient:', str(transport.recipient) if transport.recipient else 'N/A'),
        ('Consultant:', getattr(transport, 'consultant', '') or 'N/A'),
        ('Region:', getattr(transport, 'region', '') or 'N/A'),
        ('District:', getattr(transport, 'district', '') or 'N/A'),
        ('Community:', getattr(transport, 'community', '') or 'N/A'),
        ('Package No:', getattr(transport, 'package_number', '') or 'N/A'),
    ]
    for label, value in dest_info:
        pdf.setFont(BODY_FONT, 8)
        pdf.drawString(right_col_x, dest_y, label)
        pdf.setFont(BODY_FONT_BOLD, 8)
        pdf.drawString(right_col_x + 28 * mm, dest_y, str(value)[:45])
        dest_y -= 5.5 * mm

    y = min(tx_y, dest_y) - 6 * mm

    # ── Signatures & Endorsements ─────────────────────────────────────
    if y < 80 * mm:
        pdf.showPage()
        _tricolor_bar(pdf, width, height)
        y = height - 20 * mm

    y = _section_title(pdf, left, y, "Signatures & Endorsements", right)

    rows_data = _build_signature_rows(transport)
    y = _draw_signature_table(pdf, left, right, y, rows_data)

    # ── Footer ────────────────────────────────────────────────────────
    y -= 6 * mm

    # Important notice box (pale green tint with border)
    box_h = 16 * mm
    pdf.setFillColorRGB(0.91, 0.96, 0.91)  # pale green tint
    pdf.rect(left, y - box_h, usable, box_h, stroke=0, fill=1)
    pdf.setStrokeColorRGB(0.18, 0.55, 0.20)
    pdf.setLineWidth(0.5)
    pdf.rect(left, y - box_h, usable, box_h, stroke=1, fill=0)

    bx = left + 3 * mm
    by = y - 4 * mm
    pdf.setFont(BODY_FONT_BOLD, 6.5)
    pdf.setFillColorRGB(0.10, 0.36, 0.16)
    pdf.drawString(bx, by, "Important:")
    pdf.setFont(BODY_FONT, 6)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.drawString(bx + 18 * mm, by,
                   "This waybill must accompany the materials during transport. "
                   "All parties must verify quantities before signing.")
    by -= 4 * mm
    pdf.drawString(bx + 18 * mm, by,
                   "Any discrepancies should be reported immediately.")

    y = y - box_h - 5 * mm

    # Ministry + system name
    pdf.setFont(BODY_FONT, 5.5)
    pdf.setFillColorRGB(0.45, 0.45, 0.45)
    pdf.drawCentredString(width / 2, y,
                          "Ministry of Energy and Green Transition of Ghana - Inventory Management System")
    y -= 4 * mm
    pdf.drawCentredString(width / 2, y,
                          "This is a computer-generated waybill. For verification or queries, contact IMS Support.")
    y -= 4 * mm
    gen_time = timezone.now().strftime('%d %B %Y at %H:%M')
    pdf.setFont(BODY_FONT_BOLD, 5.5)
    pdf.drawCentredString(width / 2, y, f"Document Generated: {gen_time}")
    pdf.setFillColorRGB(0, 0, 0)


# ---------------------------------------------------------------------------
# Main view — download waybill PDF
# ---------------------------------------------------------------------------
@ratelimit(key='user', rate=settings.RATELIMIT_WAYBILL_PDF, method=['GET'], block=True)
@login_required
def download_waybill_pdf(request, transport_id):
    """Generate and download waybill PDF for a transport.

    Rate-limited to 10/min per user.  Waybill is only available after
    site receipt has been logged by the consultant.
    """
    transport = get_object_or_404(MaterialTransport, id=transport_id)

    # ── Authorization ──────────────────────────────────────────────────
    _user = request.user
    _is_internal = (
        _user.is_superuser
        or _user.is_staff
        or _user.groups.filter(name='Management').exists()
    )
    if not _is_internal:
        _owned = MaterialTransport.objects.filter(
            id=transport_id, transporter__user=_user
        ).exists()
        if not _owned and transport.waybill_number and transport.waybill_number not in ['Unknown', '']:
            _owned = MaterialTransport.objects.filter(
                waybill_number=transport.waybill_number, transporter__user=_user
            ).exists()
        if not _owned:
            raise Http404("No MaterialTransport matches the given query.")

    # ── Site receipt gate ──────────────────────────────────────────────
    has_receipt = hasattr(transport, 'site_receipt') and transport.site_receipt is not None

    if transport.waybill_number and transport.waybill_number not in ['Unknown', '']:
        bulk = MaterialTransport.objects.filter(waybill_number=transport.waybill_number)
        all_received = all(
            hasattr(t, 'site_receipt') and t.site_receipt is not None
            for t in bulk
        )
        if not all_received:
            messages.error(
                request,
                'Waybill cannot be downloaded until ALL materials in this shipment '
                'are confirmed received on site.'
            )
            return redirect('transportation_status')
    elif not has_receipt:
        messages.error(
            request,
            'Waybill cannot be downloaded until materials are confirmed received on site.'
        )
        return redirect('transportation_status')

    # ── Download counter ───────────────────────────────────────────────
    download_count_key = f"waybill_download_count_{transport.pk}"
    download_count = int(request.session.get(download_count_key, 0)) + 1
    request.session[download_count_key] = download_count
    try:
        if hasattr(transport, 'waybill_download_count'):
            transport.waybill_download_count = download_count
            transport.save(update_fields=['waybill_download_count'])
    except Exception:
        pass

    copy_label = "ORIGINAL COPY" if download_count == 1 else f"DUPLICATE COPY {download_count - 1}"

    # ── Collect all transports on this waybill ─────────────────────────
    if transport.waybill_number and transport.waybill_number not in ['Unknown', '']:
        all_transports = list(
            MaterialTransport.objects.filter(waybill_number=transport.waybill_number)
            .select_related('material_order', 'transporter', 'vehicle')
            .order_by('id')
        )
    else:
        all_transports = [transport]

    # ── Generate PDF ───────────────────────────────────────────────────
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas as canvas_mod

    buffer = io.BytesIO()
    pdf = canvas_mod.Canvas(buffer, pagesize=A4)
    page_w, page_h = A4

    # Page 1: Acknowledgement Form
    _draw_acknowledgement(pdf, page_w, page_h, transport, all_transports, copy_label)
    pdf.showPage()

    # Page 2: Material Waybill
    _draw_waybill_page(pdf, page_w, page_h, transport, all_transports,
                       copy_label, download_count)

    pdf.save()
    buffer.seek(0)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    response = HttpResponse(content_type='application/pdf')
    filename = f"Waybill_{transport.waybill_number or transport.id}_{copy_label.replace(' ', '_')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write(pdf_bytes)
    return response


# ---------------------------------------------------------------------------
# Public QR verification endpoint
# ---------------------------------------------------------------------------
def verify_waybill_qr(request, waybill_identifier):
    """Public waybill verification — no login required for read-only view.

    Scans the QR code on the waybill and shows verification details.
    Logged-in users also get their digital stamp recorded.
    """
    from ..models import Profile
    from django.db import transaction as db_tx

    # Find transport by waybill number or numeric ID
    transport = None
    if waybill_identifier.startswith('WB-'):
        transport = MaterialTransport.objects.filter(
            waybill_number=waybill_identifier
        ).select_related('material_order', 'transporter', 'vehicle').first()
    else:
        try:
            transport = MaterialTransport.objects.filter(
                id=int(waybill_identifier)
            ).select_related('material_order', 'transporter', 'vehicle').first()
        except (ValueError, TypeError):
            pass

    if not transport:
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'error': 'Waybill not found'}, status=404)
        messages.error(request, "Waybill not found.")
        return redirect('transportation_status')

    # ── Logged-in: record stamp + auto-release ─────────────────────────
    role = None
    if request.user.is_authenticated:
        group_names = [g.name for g in request.user.groups.all()]

        if is_store_officer(request.user):
            role = "Store Officer (Issued By)"
        elif 'Transporters' in group_names or 'Transporter' in group_names:
            role = "Transporter/Driver (Picked Up By)"
        elif 'Consultants' in group_names or 'Consultant' in group_names:
            role = "Consultant (Received By)"
        else:
            role = "Authorized User"

        try:
            MaterialOrderAudit.objects.create(
                material_order=transport.material_order,
                user=request.user,
                action=f'Waybill verified via QR code — {role}',
                timestamp=timezone.now(),
            )
        except Exception:
            pass

        # Auto-mark release letter as 'released' if all transports received
        try:
            if transport.material_order and transport.material_order.release_letter:
                rl = transport.material_order.release_letter
                if rl.workflow_status == 'approved':
                    all_orders = rl.material_orders.all()
                    all_confirmed = all(
                        MaterialTransport.objects.filter(
                            material_order=order
                        ).exclude(waybill_number__in=['', 'Unknown']).filter(
                            site_receipt__isnull=False
                        ).exists()
                        for order in all_orders
                    )
                    if all_confirmed:
                        rl.workflow_status = 'released'
                        rl.save(update_fields=['workflow_status'])
                        MaterialOrderAudit.objects.create(
                            material_order=transport.material_order,
                            user=request.user,
                            action=f'Auto-released: all waybills verified for {rl.code}',
                            timestamp=timezone.now(),
                        )
        except Exception:
            pass

    # ── JSON response for AJAX ─────────────────────────────────────────
    if request.headers.get('Accept') == 'application/json':
        receipt = getattr(transport, 'site_receipt', None)
        return JsonResponse({
            'waybill_number': transport.waybill_number,
            'material': transport.material_name,
            'quantity': str(transport.quantity),
            'unit': transport.unit or '',
            'transporter': transport.transporter.name if transport.transporter else '',
            'driver': transport.driver_name or '',
            'vehicle': transport.vehicle.registration_number if transport.vehicle else '',
            'date_dispatched': transport.date_dispatched.isoformat() if transport.date_dispatched else '',
            'status': transport.status,
            'received': receipt is not None,
            'received_date': receipt.received_date.isoformat() if receipt and receipt.received_date else '',
            'received_by': (receipt.received_by.get_full_name() or receipt.received_by.username) if receipt and receipt.received_by else '',
            'verified_by': role,
        })

    # ── HTML verification page ─────────────────────────────────────────
    receipt = getattr(transport, 'site_receipt', None)
    context = {
        'transport': transport,
        'receipt': receipt,
        'role': role,
        'all_transports': MaterialTransport.objects.filter(
            waybill_number=transport.waybill_number
        ).select_related('material_order') if transport.waybill_number else [transport],
    }
    return render(request, 'Inventory/waybill_verify.html', context)
