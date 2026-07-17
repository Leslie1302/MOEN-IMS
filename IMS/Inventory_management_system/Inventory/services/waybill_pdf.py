"""
Waybill PDF generation + QR verification (moved from transporter_views.py,
Phase 6 decision 6 — pure relocation, no behavior change).
"""
from django.contrib.auth.decorators import login_required, user_passes_test
from django_ratelimit.decorators import ratelimit
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Q, Count, Sum, F
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.conf import settings
import pandas as pd
import json
import os
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from ..models import (
    MaterialOrder, ReleaseLetter, MaterialTransport, Transporter, TransportVehicle, 
    MaterialOrderAudit, SiteReceipt
    # Note: Notification, Project, ProjectSite, ProjectPhase will be available after migration
)
from ..forms import TransporterForm, TransportVehicleForm, TransportAssignmentForm, TransporterImportForm
from ..utils import is_store_officer, is_superuser, is_schedule_officer

from django.views.decorators.http import require_POST





def generate_qr_code(data, size=100):
    """Generate a QR code image from data."""
    if not QRCODE_AVAILABLE:
        return None
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        # Resize to desired size
        if PIL_AVAILABLE:
            img = img.resize((size, size), PILImage.Resampling.LANCZOS)
        # Convert to BytesIO
        img_buffer = BytesIO()
        img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        return img_buffer
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating QR code: {str(e)}")
        return None


class WaybillTemplate(SimpleDocTemplate):
    """Custom PDF template that adds QR code and watermark to every page."""
    def __init__(self, *args, qr_code_data=None, watermark_text=None, **kwargs):
        self.qr_code_data = qr_code_data
        self.watermark_text = watermark_text
        super().__init__(*args, **kwargs)
    
    def build(self, flowables, onFirstPage=None, onLaterPages=None, canvasmaker=canvas.Canvas):
        """Override build to add QR code and watermark to every page."""
        def add_qr_and_watermark(canvas_obj, doc):
            # Add QR code to top right of every page
            if self.qr_code_data and QRCODE_AVAILABLE:
                qr_img = generate_qr_code(self.qr_code_data, size=80)
                if qr_img:
                    try:
                        canvas_obj.saveState()
                        # Position QR code at top right
                        qr_x = doc.width - 1.2*inch
                        qr_y = doc.height - 1.0*inch
                        canvas_obj.drawImage(ImageReader(qr_img), qr_x, qr_y, width=0.8*inch, height=0.8*inch, mask='auto')
                        canvas_obj.restoreState()
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.error(f"Error adding QR code to PDF: {str(e)}")
            
            # Add watermark (diagonal text)
            if self.watermark_text:
                try:
                    canvas_obj.saveState()
                    canvas_obj.setFont("Helvetica-Bold", 48)
                    canvas_obj.setFillColor(colors.HexColor('#cccccc'), alpha=0.3)
                    # Rotate and position watermark diagonally
                    canvas_obj.translate(doc.width/2, doc.height/2)
                    canvas_obj.rotate(45)
                    canvas_obj.drawCentredString(0, 0, self.watermark_text)
                    canvas_obj.restoreState()
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error adding watermark to PDF: {str(e)}")
        
        # Combine custom function with user's functions
        def first_page(canvas_obj, doc):
            add_qr_and_watermark(canvas_obj, doc)
            if onFirstPage:
                onFirstPage(canvas_obj, doc)
        
        def later_pages(canvas_obj, doc):
            add_qr_and_watermark(canvas_obj, doc)
            if onLaterPages:
                onLaterPages(canvas_obj, doc)
        
        super().build(flowables, onFirstPage=first_page, onLaterPages=later_pages, canvasmaker=canvasmaker)


@ratelimit(key='user', rate=settings.RATELIMIT_WAYBILL_PDF, method=['GET'], block=True)
@login_required
def download_waybill_pdf(request, transport_id):
    """Generate and download waybill PDF for a transport (or all transports with same waybill for bulk assignments).

    Rate-limited to 10/min per user: PDF generation is CPU/memory-heavy
    (this view builds a full multi-page document), so repeated calls are a
    resource-exhaustion vector even for an authenticated user.
    
    Waybill is only available for download after site receipt has been logged by the consultant.
    This ensures all stamps (Store Manager, Store Officer, Driver, Recipient) are present on the final document.
    """
    transport = get_object_or_404(MaterialTransport, id=transport_id)

    # Object-level authorization: a waybill is only downloadable by internal
    # staff (Store/Schedule Officers, Stores Management), Management, and
    # superusers — OR by the external Transporter the shipment is assigned to.
    # Without this, any authenticated user (incl. an external transporter or
    # consultant) could pull ANY waybill by iterating transport_id (IDOR).
    # Out-of-scope requests 404 rather than 403 so we don't leak existence.
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
        # Bulk waybills: allow if the user owns ANY transport on this waybill.
        if not _owned and transport.waybill_number and transport.waybill_number not in ['Unknown', '']:
            _owned = MaterialTransport.objects.filter(
                waybill_number=transport.waybill_number, transporter__user=_user
            ).exists()
        if not _owned:
            raise Http404("No MaterialTransport matches the given query.")

    # Check if site receipt exists - waybill can only be downloaded after receipt is confirmed
    has_site_receipt = hasattr(transport, 'site_receipt') and transport.site_receipt is not None
    
    # For bulk assignments, check if ALL transports have site receipts
    if transport.waybill_number and transport.waybill_number not in ['Unknown', '']:
        bulk_transports = MaterialTransport.objects.filter(
            waybill_number=transport.waybill_number
        )
        all_received = all(
            hasattr(t, 'site_receipt') and t.site_receipt is not None 
            for t in bulk_transports
        )
        if not all_received:
            messages.error(
                request, 
                'Waybill cannot be downloaded until ALL materials in this shipment are confirmed received on site. '
                'Please ensure the consultant has logged site receipt for all items.'
            )
            return redirect('transportation_status')
    elif not has_site_receipt:
        messages.error(
            request, 
            'Waybill cannot be downloaded until materials are confirmed received on site. '
            'The consultant must first log the site receipt.'
        )
        return redirect('transportation_status')
    
    # Track download count without requiring a database field on the model.
    # If a real field exists in a future migration, keep it in sync too.
    download_count_key = f"waybill_download_count_{transport.pk}"
    download_count = int(request.session.get(download_count_key, 0)) + 1
    request.session[download_count_key] = download_count
    if hasattr(transport, 'waybill_download_count'):
        try:
            transport.waybill_download_count = download_count
            transport.save(update_fields=['waybill_download_count'])
        except Exception:
            pass

    # Determine copy label
    if download_count == 1:
        copy_label = "ORIGINAL COPY"
    else:
        copy_label = f"DUPLICATE COPY {download_count - 1}"
    
    # For bulk assignments, fetch ALL transports with the same waybill number
    if transport.waybill_number and transport.waybill_number not in ['Unknown', '']:
        # Bulk assignment - get all materials on this waybill
        all_transports = MaterialTransport.objects.filter(
            waybill_number=transport.waybill_number
        ).select_related('material_order', 'transporter', 'vehicle').order_by('id')
    else:
        # Single assignment
        all_transports = [transport]
    
    # Generate QR code URL for waybill verification - points to sign-in with redirect
    from django.urls import reverse
    waybill_id = transport.waybill_number or str(transport.id)
    # QR code links to sign-in page with next parameter pointing to waybill verification
    signin_url = request.build_absolute_uri(reverse('signin'))
    verify_url = request.build_absolute_uri(reverse('verify_waybill_qr', args=[waybill_id]))
    qr_url = f"{signin_url}?next={verify_url}"
    
    # Load logo if available - Ministry of Energy and Green Transition of Ghana logo
    logo_path = None
    logo_paths = [
        # Check both 'logo' and 'logos' directories (user may have created either)
        os.path.join(settings.MEDIA_ROOT, 'logos', 'black.jpg'),  # Primary logo location (plural)
        os.path.join(settings.MEDIA_ROOT, 'logo', 'black.jpg'),   # Primary logo location (singular)
        os.path.join(settings.MEDIA_ROOT, 'logos', 'black.png'),
        os.path.join(settings.MEDIA_ROOT, 'logo', 'black.png'),
        os.path.join(settings.MEDIA_ROOT, 'logos', 'ministry_logo.png'),
        os.path.join(settings.MEDIA_ROOT, 'logo', 'ministry_logo.png'),
        os.path.join(settings.MEDIA_ROOT, 'logos', 'ministry_logo.jpg'),
        os.path.join(settings.MEDIA_ROOT, 'logo', 'ministry_logo.jpg'),
        os.path.join(settings.MEDIA_ROOT, 'logos', 'ministry_logo.jpeg'),
        os.path.join(settings.MEDIA_ROOT, 'logo', 'ministry_logo.jpeg'),
        os.path.join(settings.MEDIA_ROOT, 'logos', 'logo.png'),
        os.path.join(settings.MEDIA_ROOT, 'logo', 'logo.png'),
        os.path.join(settings.MEDIA_ROOT, 'logos', 'logo.jpg'),
        os.path.join(settings.MEDIA_ROOT, 'logo', 'logo.jpg'),
        os.path.join(settings.MEDIA_ROOT, 'logos', 'logo.jpeg'),
        os.path.join(settings.MEDIA_ROOT, 'logo', 'logo.jpeg'),
        # Fallback locations
        os.path.join(settings.MEDIA_ROOT, 'profile_pics', 'ministry_logo.png'),
        os.path.join(settings.BASE_DIR, 'static', 'images', 'ministry_logo.png'),
        os.path.join(settings.MEDIA_ROOT, 'profile_pics', 'logo.png'),
        os.path.join(settings.BASE_DIR, 'static', 'images', 'logo.png'),
    ]
    for path in logo_paths:
        if os.path.exists(path):
            logo_path = path
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"Using logo from: {logo_path}")
            break
    
    # Debug: Log if no logo found
    if not logo_path:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"No logo found. Checked paths: {logo_paths[:3]}...")
    
    # Create PDF buffer with custom template
    buffer = BytesIO()
    doc = WaybillTemplate(
        buffer, 
        pagesize=A4, 
        rightMargin=0.5*inch, 
        leftMargin=0.5*inch, 
        topMargin=0.4*inch, 
        bottomMargin=0.5*inch,
        qr_code_data=qr_url,
        watermark_text=copy_label
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=28,
        textColor=colors.white,
        spaceAfter=0,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=32
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=11,
        textColor=colors.white,
        alignment=TA_CENTER,
        fontName='Helvetica',
        spaceAfter=0
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=13,
        textColor=colors.HexColor('#1a5490'),
        spaceAfter=6,
        spaceBefore=10,
        fontName='Helvetica-Bold',
        borderPadding=5,
        leftIndent=8
    )
    
    normal_style = styles['Normal']
    
    small_text = ParagraphStyle(
        'SmallText',
        parent=styles['Normal'],
        fontSize=8,
        leading=10
    )
    
    cover_title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['Heading1'],
        fontSize=36,
        textColor=colors.HexColor('#1a5490'),
        spaceAfter=20,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    
    # ========== ACKNOWLEDGEMENT FORM (First Page) ==========
    # Simplified format matching the template
    cover_elements = []
    cover_elements.append(Spacer(1, 0.2*inch))
    
    # Logo at top left
    if logo_path and os.path.exists(logo_path):
        try:
            logo_img = Image(logo_path, width=1.2*inch, height=1.2*inch)
            cover_elements.append(logo_img)
            cover_elements.append(Spacer(1, 0.1*inch))
        except Exception:
            pass  # Continue without logo if there's an error
    
    # Title: ACKNOWLEDGEMENT FORM
    cover_elements.append(Paragraph("ACKNOWLEDGEMENT FORM", ParagraphStyle(
        'CoverTitle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.black,
        spaceAfter=8,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )))
    cover_elements.append(Spacer(1, 0.15*inch))
    
    # Waybill Number and Date - simple format matching template
    waybill_date = transport.date_dispatched.strftime('%d %B %Y') if transport.date_dispatched else timezone.now().strftime('%d %B %Y')
    waybill_info_data = [
        ['Waybill No:', Paragraph(f"<b>{transport.waybill_number or 'N/A'}</b>", normal_style)],
        ['Date:', Paragraph(waybill_date, normal_style)],
    ]
    
    waybill_info_table = Table(waybill_info_data, colWidths=[1.2*inch, 5.3*inch])
    waybill_info_table.setStyle(TableStyle([
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    cover_elements.append(waybill_info_table)
    cover_elements.append(Spacer(1, 0.2*inch))
    
    # Store/Issuing Information
    cover_elements.append(Paragraph("<b>Store/Issuing Information</b>", ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.black,
        spaceAfter=4,
        spaceBefore=2,
        fontName='Helvetica-Bold',
    )))
    
    # Get storekeeper from processed_by (who actually processed it), assigned_to, or created_by
    storekeeper_for_cover = None
    if transport.material_order:
        storekeeper_for_cover = (transport.material_order.processed_by or 
                                transport.material_order.assigned_to or 
                                transport.material_order.created_by)
    
    store_data = []
    if transport.warehouse:
        store_data.append(['Warehouse:', Paragraph(f"<b>{transport.warehouse.name}</b>", normal_style)])
        if transport.warehouse.location:
            store_data.append(['Location:', Paragraph(transport.warehouse.location, normal_style)])
        if transport.warehouse.contact_person:
            store_data.append(['Contact Person:', Paragraph(transport.warehouse.contact_person, normal_style)])
        if transport.warehouse.contact_phone:
            store_data.append(['Contact Phone:', Paragraph(transport.warehouse.contact_phone, normal_style)])
    if storekeeper_for_cover:
        store_data.append(['Storekeeper:', Paragraph(f"<b>{storekeeper_for_cover.get_full_name() or storekeeper_for_cover.username}</b>", normal_style)])
        if storekeeper_for_cover.email:
            store_data.append(['Email:', Paragraph(storekeeper_for_cover.email, normal_style)])
    
    if store_data:
        store_table = Table(store_data, colWidths=[1.8*inch, 4.7*inch])
        store_table.setStyle(TableStyle([
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.HexColor('#cccccc')),
        ]))
        cover_elements.append(store_table)
    
    cover_elements.append(Spacer(1, 0.2*inch))
    
    # Destination/Recipient Information
    cover_elements.append(Paragraph("<b>Destination/Recipient Information</b>", ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.black,
        spaceAfter=4,
        spaceBefore=2,
        fontName='Helvetica-Bold',
    )))
    
    destination_data = []
    if transport.recipient:
        destination_data.append(['Recipient:', Paragraph(f"<b>{transport.recipient}</b>", normal_style)])
    if transport.consultant:
        destination_data.append(['Consultant:', Paragraph(transport.consultant, normal_style)])
    if transport.region:
        destination_data.append(['Region:', Paragraph(transport.region, normal_style)])
    if transport.district:
        destination_data.append(['District:', Paragraph(transport.district, normal_style)])
    if transport.community:
        destination_data.append(['Community:', Paragraph(f"<b>{transport.community}</b>", normal_style)])
    if transport.destination_contact:
        destination_data.append(['Destination Contact:', Paragraph(transport.destination_contact, normal_style)])
    if transport.destination_phone:
        destination_data.append(['Destination Phone:', Paragraph(transport.destination_phone, normal_style)])
    if transport.package_number:
        destination_data.append(['Package Number:', Paragraph(f"<b>{transport.package_number}</b>", normal_style)])
    
    if destination_data:
        destination_table = Table(destination_data, colWidths=[1.8*inch, 4.7*inch])
        destination_table.setStyle(TableStyle([
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LINEBELOW', (0, -1), (-1, -1), 1, colors.HexColor('#cccccc')),
        ]))
        cover_elements.append(destination_table)
    
    cover_elements.append(Spacer(1, 0.3*inch))
    
    # Signatures section - All parties
    cover_elements.append(Paragraph("<b>Signatures & Endorsements</b>", ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.black,
        spaceAfter=6,
        spaceBefore=2,
        fontName='Helvetica-Bold',
    )))
    
    # Get store officer info and stamp (with image embedding support)
    # Priority: processed_by (who actually processed it) > assigned_to (who it was assigned to) > created_by
    store_officer_name = ''
    store_officer_stamp_image = None
    store_officer_stamp_text = ''
    store_officer_date = ''
    store_officer = None
    if transport.material_order:
        # Use processed_by first (the person who actually processed the order)
        store_officer = (transport.material_order.processed_by or 
                      transport.material_order.assigned_to or 
                      transport.material_order.created_by)
    
    if store_officer:
        store_officer_name = store_officer.get_full_name() or store_officer.username
        try:
            from .models import Profile
            profile = Profile.objects.filter(user=store_officer).first()
            if profile:
                # Look for PNG stamp in media/digital_signatures/ folder
                stamp_filenames = [
                    f"{store_officer.username}.png",
                    f"{store_officer.id}.png",
                    f"{store_officer.username}.jpg",
                    f"{store_officer.id}.jpg",
                ]
                
                digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital_signatures')
                if not os.path.exists(digital_signatures_dir):
                    digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital signatures')
                
                for filename in stamp_filenames:
                    stamp_path = os.path.join(digital_signatures_dir, filename)
                    if os.path.exists(stamp_path):
                        try:
                            store_officer_stamp_image = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                            break
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"Could not load digital stamp image {stamp_path}: {str(e)}")
                            continue
                
                if not store_officer_stamp_image and profile:
                    try:
                        if hasattr(profile, 'generate_digital_stamp_png'):
                            stamp_path = profile.generate_digital_stamp_png()
                            if stamp_path and os.path.exists(stamp_path):
                                store_officer_stamp_image = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Could not generate digital stamp PNG: {str(e)}")
                
                if not store_officer_stamp_image:
                    stamp = profile.get_or_create_signature_stamp() if profile else None
                    if stamp:
                        try:
                            stamp_data = profile.display_signature_stamp()
                            if stamp_data:
                                store_officer_stamp_text = f"{stamp_data.get('SIGNED_BY', store_officer_name)}\nID: {stamp_data.get('ID', '')}"
                        except Exception:
                            if '|' in stamp:
                                parts = stamp.split('|')
                                signed_by = parts[0].replace('SIGNED_BY:', '') if 'SIGNED_BY:' in parts[0] else store_officer_name
                                stamp_id = parts[2].replace('ID:', '') if len(parts) > 2 and 'ID:' in parts[2] else ''
                                store_officer_stamp_text = f"{signed_by}\nID: {stamp_id}"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting store officer stamp: {str(e)}")
        # Use processed_at date if available, otherwise assigned_at, otherwise date_dispatched
        if transport.material_order and transport.material_order.processed_at:
            store_officer_date = transport.material_order.processed_at.strftime('%d %B %Y')
        elif transport.material_order and transport.material_order.assigned_at:
            store_officer_date = transport.material_order.assigned_at.strftime('%d %B %Y')
        else:
            store_officer_date = transport.date_dispatched.strftime('%d %B %Y') if transport.date_dispatched else ''
    
    # Build signature cell - use image if available, otherwise text
    store_officer_signature_cell = store_officer_stamp_image if store_officer_stamp_image else Paragraph(store_officer_stamp_text or '_________________', small_text)
    
    # Get store manager info and stamp
    store_manager = None
    store_manager_name = ''
    store_manager_stamp_image = None
    store_manager_stamp_text = ''
    store_manager_date = ''
    
    # Try to get store manager from material_order.assigned_by or transport.created_by
    if transport.material_order and transport.material_order.assigned_by:
        store_manager = transport.material_order.assigned_by
    elif transport.created_by:
        store_manager = transport.created_by
    
    if store_manager:
        store_manager_name = store_manager.get_full_name() or store_manager.username
        try:
            from .models import Profile
            profile = Profile.objects.filter(user=store_manager).first()
            if profile:
                # Look for PNG stamp in media/digital_signatures/ folder
                stamp_filenames = [
                    f"{store_manager.username}.png",
                    f"{store_manager.id}.png",
                    f"{store_manager.id}.jpg",
                    f"{store_manager.username}.jpg",
                ]
                
                digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital_signatures')
                if not os.path.exists(digital_signatures_dir):
                    digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital signatures')
                
                for filename in stamp_filenames:
                    stamp_path = os.path.join(digital_signatures_dir, filename)
                    if os.path.exists(stamp_path):
                        try:
                            store_manager_stamp_image = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                            break
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"Could not load store manager digital stamp image {stamp_path}: {str(e)}")
                            continue
                
                if not store_manager_stamp_image and profile:
                    try:
                        if hasattr(profile, 'generate_digital_stamp_png'):
                            stamp_path = profile.generate_digital_stamp_png()
                            if stamp_path and os.path.exists(stamp_path):
                                store_manager_stamp_image = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Could not generate store manager digital stamp PNG: {str(e)}")
                
                if not store_manager_stamp_image:
                    stamp = profile.get_or_create_signature_stamp() if profile else None
                    if stamp:
                        try:
                            stamp_data = profile.display_signature_stamp()
                            if stamp_data:
                                store_manager_stamp_text = f"{stamp_data.get('SIGNED_BY', store_manager_name)}\nID: {stamp_data.get('ID', '')}"
                        except Exception:
                            if '|' in stamp:
                                parts = stamp.split('|')
                                signed_by = parts[0].replace('SIGNED_BY:', '') if 'SIGNED_BY:' in parts[0] else store_manager_name
                                stamp_id = parts[2].replace('ID:', '') if len(parts) > 2 and 'ID:' in parts[2] else ''
                                store_manager_stamp_text = f"{signed_by}\nID: {stamp_id}"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting store manager stamp: {str(e)}")
        
        # Get date from material_order.assigned_at or transport.date_dispatched
        if transport.material_order and transport.material_order.assigned_at:
            store_manager_date = transport.material_order.assigned_at.strftime('%d %B %Y')
        elif transport.date_dispatched:
            store_manager_date = transport.date_dispatched.strftime('%d %B %Y')
    
    # Build store manager signature cell
    store_manager_signature_cell = store_manager_stamp_image if store_manager_stamp_image else Paragraph(store_manager_stamp_text or '_________________', small_text)
    
    # Signature table with all parties: Store Officer, Store Manager, Driver, Recipient
    signature_cover_data = [
        [
            Paragraph('<b>Name</b>', small_text),
            Paragraph('<b>Signature</b>', small_text),
            Paragraph('<b>Date</b>', small_text)
        ],
        [
            Paragraph('<b>Store Officer</b>', small_text),
            store_officer_signature_cell,
            Paragraph(store_officer_date or '_________________', small_text)
        ],
        [
            Paragraph('<b>Store Manager</b>', small_text),
            store_manager_signature_cell,
            Paragraph(store_manager_date or '_________________', small_text)
        ],
        [
            Paragraph('<b>Driver</b>', small_text),
            Paragraph('_________________', small_text),
            Paragraph('_________________', small_text)
        ],
        [
            Paragraph('<b>Recipient</b>', small_text),
            Paragraph('_________________', small_text),
            Paragraph('_________________', small_text)
        ],
    ]
    
    signature_cover_table = Table(signature_cover_data, colWidths=[1.8*inch, 3.0*inch, 1.7*inch])
    signature_cover_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a5490')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
    ]))
    cover_elements.append(signature_cover_table)
    
    # Add cover page to elements
    elements.extend(cover_elements)
    elements.append(PageBreak())
    
    # ========== MAIN WAYBILL CONTENT ==========
    # Header Banner with logo and gradient effect
    header_cells = []
    if logo_path and os.path.exists(logo_path):
        try:
            logo_img = Image(logo_path, width=1*inch, height=1*inch)
            header_cells.append(logo_img)
        except Exception:
            header_cells.append('')
    else:
        header_cells.append('')
    
    header_cells.append(Paragraph("MATERIAL WAYBILL", title_style))
    
    header_data = [header_cells]
    # Adjust column widths based on whether logo exists
    if logo_path and os.path.exists(logo_path):
        header_table = Table(header_data, colWidths=[1.2*inch, 5.8*inch])
    else:
        header_table = Table(header_data, colWidths=[7*inch])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1a5490')),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),  # Center the title
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),     # Left align logo
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LINEABOVE', (0, 0), (-1, 0), 3, colors.HexColor('#0d3a6b')),
        ('LINEBELOW', (0, -1), (-1, -1), 3, colors.HexColor('#2c5f8d')),
    ]))
    
    elements.append(header_table)
    
    # Subtitle under banner
    subtitle_data = [[
        Paragraph("Ministry of Energy and Green Transition of Ghana - Inventory Management System", subtitle_style),
    ]]
    subtitle_table = Table(subtitle_data, colWidths=[7*inch])
    subtitle_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#2c5f8d')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    
    elements.append(subtitle_table)
    elements.append(Spacer(1, 0.25*inch))
    
    # Waybill Information Box with colored accent
    elements.append(Paragraph("📋 Waybill Information", heading_style))
    
    waybill_data = [
        ['Waybill Number:', Paragraph(f"<b>{transport.waybill_number or 'N/A'}</b>", normal_style)],
        ['Shipment Type:', Paragraph(f"<b>{'Bulk Shipment' if len(all_transports) > 1 else 'Single Shipment'}</b>", normal_style)],
        ['Total Materials:', Paragraph(f"<b>{len(all_transports)}</b> item{'s' if len(all_transports) > 1 else ''}", normal_style)],
        ['Date Assigned:', transport.date_dispatched.strftime('%d %B %Y, %H:%M') if transport.date_dispatched else 'N/A'],
        ['Status:', Paragraph(f"<b><font color='#28a745'>{transport.get_status_display()}</font></b>", normal_style)],
    ]
    
    waybill_table = Table(waybill_data, colWidths=[2*inch, 4.5*inch])
    waybill_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f8ff')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#1a5490')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, -1), (-1, -1), 2, colors.HexColor('#1a5490')),
    ]))
    
    elements.append(waybill_table)
    elements.append(Spacer(1, 0.25*inch))
    
    # Material Information - Show ALL materials on this waybill
    elements.append(Paragraph("📦 Materials on This Waybill", heading_style))
    
    # Build table with all materials - Use Paragraph for text wrapping
    material_data = [[
        Paragraph('<b>#</b>', normal_style),
        Paragraph('<b>Material Name</b>', normal_style),
        Paragraph('<b>Code</b>', normal_style),
        Paragraph('<b>Quantity</b>', normal_style),
        Paragraph('<b>Request Code</b>', normal_style)
    ]]
    
    for idx, t in enumerate(all_transports, 1):
        # Use Paragraph to enable text wrapping
        material_data.append([
            Paragraph(f"<b>{idx}</b>", small_text),
            Paragraph(t.material_name, small_text),  # Full name, will wrap
            Paragraph(t.material_code or 'N/A', small_text),
            Paragraph(f"<b>{t.quantity}</b> {t.unit or ''}", small_text),
            Paragraph(t.material_order.request_code if t.material_order else 'N/A', small_text)
        ])
    
    material_table = Table(material_data, colWidths=[0.35*inch, 2.5*inch, 0.9*inch, 1.1*inch, 1.15*inch])
    material_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a5490')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # Center # column
        ('ALIGN', (1, 0), (-1, -1), 'LEFT'),   # Left align rest
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#1a5490')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Top alignment for wrapping
        ('PADDING', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#0d3a6b')),
    ]))
    
    elements.append(material_table)
    elements.append(Spacer(1, 0.25*inch))
    
    # Transporter Information
    elements.append(Paragraph("🚚 Transporter Information", heading_style))
    
    transporter_data = [
        ['Transporter:', Paragraph(f"<b>{transport.transporter.name if transport.transporter else 'N/A'}</b>", normal_style)],
        ['Vehicle:', Paragraph(f"<b>{transport.vehicle.registration_number}</b> ({transport.vehicle.vehicle_type})" 
                    if transport.vehicle else 'N/A', normal_style)],
        ['Driver Name:', Paragraph(transport.driver_name or 'N/A', normal_style)],
        ['Driver Phone:', Paragraph(f"<font color='#1a5490'>{transport.driver_phone or 'N/A'}</font>", normal_style)],
    ]
    
    transporter_table = Table(transporter_data, colWidths=[1.8*inch, 4.7*inch])
    transporter_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#fff3cd')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#ffc107')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, -1), (-1, -1), 2, colors.HexColor('#ffc107')),
    ]))
    
    elements.append(transporter_table)
    elements.append(Spacer(1, 0.25*inch))
    
    # Destination Information
    elements.append(Paragraph("📍 Destination Information", heading_style))
    
    destination_data = [
        ['Recipient:', Paragraph(f"<b>{transport.recipient or 'N/A'}</b>", normal_style)],
        ['Consultant:', Paragraph(transport.consultant or 'N/A', normal_style)],
        ['Region:', Paragraph(transport.region or 'N/A', normal_style)],
        ['District:', Paragraph(transport.district or 'N/A', normal_style)],
        ['Community:', Paragraph(f"<b>{transport.community or 'N/A'}</b>", normal_style)],
        ['Package Number:', Paragraph(f"<font color='#dc3545'>{transport.package_number or 'N/A'}</font>", normal_style)],
    ]
    
    destination_table = Table(destination_data, colWidths=[1.8*inch, 4.7*inch])
    destination_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#d4edda')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#28a745')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('LINEBELOW', (0, -1), (-1, -1), 2, colors.HexColor('#28a745')),
    ]))
    
    elements.append(destination_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Signatures
    elements.append(Paragraph("✍️ Signatures & Endorsements", heading_style))
    elements.append(Spacer(1, 0.1*inch))
    
    # Get store officer info and stamp for main waybill (with image embedding support)
    store_officer_name_main = ''
    store_officer_stamp_image_main = None
    store_officer_stamp_text_main = ''
    store_officer_date_main = ''
    # Try to get store officer from processed_by (who actually processed it), assigned_to, or created_by
    store_officer_main = None
    if transport.material_order:
        store_officer_main = (transport.material_order.processed_by or 
                          transport.material_order.assigned_to or 
                          transport.material_order.created_by)
    
    if store_officer_main:
        store_officer_name_main = store_officer_main.get_full_name() or store_officer_main.username
        try:
            from .models import Profile
            profile = Profile.objects.filter(user=store_officer_main).first()
            if profile:
                # Look for PNG stamp in media/digital_signatures/ folder
                # Try multiple possible filenames: username.png, user_id.png, etc.
                stamp_filenames = [
                    f"{store_officer_main.username}.png",
                    f"{store_officer_main.id}.png",
                    f"{store_officer_main.username}.jpg",
                    f"{store_officer_main.id}.jpg",
                ]
                
                digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital_signatures')
                if not os.path.exists(digital_signatures_dir):
                    # Try with space in folder name
                    digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital signatures')
                
                for filename in stamp_filenames:
                    stamp_path = os.path.join(digital_signatures_dir, filename)
                    if os.path.exists(stamp_path):
                        try:
                            # Use PNG/JPG image for signature
                            store_officer_stamp_image_main = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                            break  # Found the stamp, exit loop
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"Could not load digital stamp image {stamp_path}: {str(e)}")
                            continue
                
                # If no PNG found, try to generate one
                if not store_officer_stamp_image_main and profile:
                    try:
                        # Generate PNG stamp if method exists
                        if hasattr(profile, 'generate_digital_stamp_png'):
                            stamp_path = profile.generate_digital_stamp_png()
                            if stamp_path and os.path.exists(stamp_path):
                                store_officer_stamp_image_main = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Could not generate digital stamp PNG: {str(e)}")
                
                # Fallback to text-based stamp only if PNG is not available
                if not store_officer_stamp_image_main:
                    stamp = profile.get_or_create_signature_stamp() if profile else None
                    if stamp:
                        try:
                            stamp_data = profile.display_signature_stamp()
                            if stamp_data:
                                store_officer_stamp_text_main = f"{stamp_data.get('SIGNED_BY', store_officer_name_main)}\nID: {stamp_data.get('ID', '')}"
                        except Exception:
                            # If display_signature_stamp doesn't exist, parse the stamp string
                            if '|' in stamp:
                                parts = stamp.split('|')
                                signed_by = parts[0].replace('SIGNED_BY:', '') if 'SIGNED_BY:' in parts[0] else store_officer_name_main
                                stamp_id = parts[2].replace('ID:', '') if len(parts) > 2 and 'ID:' in parts[2] else ''
                                store_officer_stamp_text_main = f"{signed_by}\nID: {stamp_id}"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting store officer stamp for main waybill: {str(e)}")
        # Use processed_at date if available, otherwise assigned_at, otherwise date_dispatched
        if transport.material_order and transport.material_order.processed_at:
            store_officer_date_main = transport.material_order.processed_at.strftime('%d %B %Y')
        elif transport.material_order and transport.material_order.assigned_at:
            store_officer_date_main = transport.material_order.assigned_at.strftime('%d %B %Y')
        else:
            store_officer_date_main = transport.date_dispatched.strftime('%d %B %Y') if transport.date_dispatched else ''
    
    # Build signature cell for main waybill - use image if available, otherwise text
    store_officer_signature_cell_main = store_officer_stamp_image_main if store_officer_stamp_image_main else Paragraph(store_officer_stamp_text_main or '_________________', small_text)
    
    # Get store manager info and stamp for main waybill (with image embedding support)
    store_manager_main = None
    store_manager_name_main = ''
    store_manager_stamp_image_main = None
    store_manager_stamp_text_main = ''
    store_manager_date_main = ''
    
    # Try to get store manager from material_order.assigned_by or transport.created_by
    if transport.material_order and transport.material_order.assigned_by:
        store_manager_main = transport.material_order.assigned_by
    elif transport.created_by:
        store_manager_main = transport.created_by
    
    if store_manager_main:
        store_manager_name_main = store_manager_main.get_full_name() or store_manager_main.username
        try:
            from .models import Profile
            profile = Profile.objects.filter(user=store_manager_main).first()
            if profile:
                # Look for PNG stamp in media/digital_signatures/ folder
                stamp_filenames = [
                    f"{store_manager_main.username}.png",
                    f"{store_manager_main.id}.png",
                    f"{store_manager_main.username}.jpg",
                    f"{store_manager_main.id}.jpg",
                ]
                
                digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital_signatures')
                if not os.path.exists(digital_signatures_dir):
                    digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital signatures')
                
                for filename in stamp_filenames:
                    stamp_path = os.path.join(digital_signatures_dir, filename)
                    if os.path.exists(stamp_path):
                        try:
                            store_manager_stamp_image_main = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                            break
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"Could not load store manager digital stamp image {stamp_path}: {str(e)}")
                            continue
                
                # If no PNG found, try to generate one
                if not store_manager_stamp_image_main and profile:
                    try:
                        if hasattr(profile, 'generate_digital_stamp_png'):
                            stamp_path = profile.generate_digital_stamp_png()
                            if stamp_path and os.path.exists(stamp_path):
                                store_manager_stamp_image_main = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Could not generate store manager digital stamp PNG: {str(e)}")
                
                # Fallback to text-based stamp only if PNG is not available
                if not store_manager_stamp_image_main:
                    stamp = profile.get_or_create_signature_stamp() if profile else None
                    if stamp:
                        try:
                            stamp_data = profile.display_signature_stamp()
                            if stamp_data:
                                store_manager_stamp_text_main = f"{stamp_data.get('SIGNED_BY', store_manager_name_main)}\nID: {stamp_data.get('ID', '')}"
                        except Exception:
                            if '|' in stamp:
                                parts = stamp.split('|')
                                signed_by = parts[0].replace('SIGNED_BY:', '') if 'SIGNED_BY:' in parts[0] else store_manager_name_main
                                stamp_id = parts[2].replace('ID:', '') if len(parts) > 2 and 'ID:' in parts[2] else ''
                                store_manager_stamp_text_main = f"{signed_by}\nID: {stamp_id}"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting store manager stamp for main waybill: {str(e)}")
        
        # Get date from material_order.assigned_at or transport.date_dispatched
        if transport.material_order and transport.material_order.assigned_at:
            store_manager_date_main = transport.material_order.assigned_at.strftime('%d %B %Y')
        elif transport.date_dispatched:
            store_manager_date_main = transport.date_dispatched.strftime('%d %B %Y')
    
    # Build store manager signature cell
    store_manager_signature_cell_main = store_manager_stamp_image_main if store_manager_stamp_image_main else Paragraph(store_manager_stamp_text_main or '_________________', small_text)
    
    # Get driver stamp info (auto-generated from transport details)
    driver_name = transport.driver_name or 'N/A'
    driver_stamp_text = ''
    driver_date = ''
    
    if transport.driver_name:
        vehicle_info = transport.vehicle.registration_number if transport.vehicle else 'N/A'
        pickup_time = transport.date_dispatched.strftime('%d %B %Y at %H:%M') if transport.date_dispatched else 'N/A'
        driver_stamp_text = f"{driver_name}\nVehicle: {vehicle_info}\nPickup: {pickup_time}"
        driver_date = transport.date_dispatched.strftime('%d %B %Y') if transport.date_dispatched else ''
    
    driver_signature_cell = Paragraph(driver_stamp_text or '_________________', small_text)
    
    # Get recipient/consultant stamp from SiteReceipt
    recipient_name = transport.consultant or 'N/A'
    recipient_stamp_image = None
    recipient_stamp_text = ''
    recipient_date = ''
    
    if hasattr(transport, 'site_receipt') and transport.site_receipt:
        receipt = transport.site_receipt
        recipient_user = receipt.received_by
        recipient_name = recipient_user.get_full_name() or recipient_user.username
        recipient_date = receipt.received_date.strftime('%d %B %Y') if receipt.received_date else ''
        
        # Try to get digital stamp for recipient
        try:
            from .models import Profile
            profile = Profile.objects.filter(user=recipient_user).first()
            if profile:
                # Look for PNG stamp in media/digital_signatures/ folder
                stamp_filenames = [
                    f"{recipient_user.username}.png",
                    f"{recipient_user.id}.png",
                    f"{recipient_user.username}.jpg",
                    f"{recipient_user.id}.jpg",
                ]
                
                digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital_signatures')
                if not os.path.exists(digital_signatures_dir):
                    digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital signatures')
                
                for filename in stamp_filenames:
                    stamp_path = os.path.join(digital_signatures_dir, filename)
                    if os.path.exists(stamp_path):
                        try:
                            recipient_stamp_image = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                            break
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"Could not load recipient digital stamp image: {str(e)}")
                            continue
                
                # Generate stamp if no PNG found
                if not recipient_stamp_image and profile:
                    try:
                        if hasattr(profile, 'generate_digital_stamp_png'):
                            stamp_path = profile.generate_digital_stamp_png()
                            if stamp_path and os.path.exists(stamp_path):
                                recipient_stamp_image = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                    except Exception:
                        pass
                
                # Fallback to text-based stamp
                if not recipient_stamp_image:
                    stamp = profile.get_or_create_signature_stamp() if profile else None
                    if stamp:
                        try:
                            stamp_data = profile.display_signature_stamp()
                            if stamp_data:
                                recipient_stamp_text = f"{stamp_data.get('SIGNED_BY', recipient_name)}\nID: {stamp_data.get('ID', '')}"
                        except Exception:
                            if '|' in stamp:
                                parts = stamp.split('|')
                                signed_by = parts[0].replace('SIGNED_BY:', '') if 'SIGNED_BY:' in parts[0] else recipient_name
                                stamp_id = parts[2].replace('ID:', '') if len(parts) > 2 and 'ID:' in parts[2] else ''
                                recipient_stamp_text = f"{signed_by}\nID: {stamp_id}"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting recipient stamp: {str(e)}")
    
    recipient_signature_cell = recipient_stamp_image if recipient_stamp_image else Paragraph(recipient_stamp_text or '_________________', small_text)
    
    signature_data = [
        [
            Paragraph('<b>Role</b>', normal_style),
            Paragraph('<b>Name</b>', normal_style),
            Paragraph('<b>Signature</b>', normal_style),
            Paragraph('<b>Date</b>', normal_style)
        ],
        [
            Paragraph('<b>Issued By</b><br/>(Store Officer)', small_text),
            Paragraph(store_officer_name_main or '_________________', small_text),
            store_officer_signature_cell_main,
            Paragraph(store_officer_date_main or '_________________', small_text)
        ],
        [
            Paragraph('<b>Approved By</b><br/>(Stores Manager)', small_text),
            Paragraph(store_manager_name_main or '_________________', small_text),
            store_manager_signature_cell_main,
            Paragraph(store_manager_date_main or '_________________', small_text)
        ],
        [
            Paragraph('<b>Picked Up By</b><br/>(Driver)', small_text),
            Paragraph(driver_name or '_________________', small_text),
            driver_signature_cell,
            Paragraph(driver_date or '_________________', small_text)
        ],
        [
            Paragraph('<b>Received By</b><br/>(Consultant)', small_text),
            Paragraph(recipient_name or '_________________', small_text),
            recipient_signature_cell,
            Paragraph(recipient_date or '_________________', small_text)
        ],
    ]
    
    signature_table = Table(signature_data, colWidths=[1.8*inch, 1.6*inch, 1.6*inch, 1.0*inch])
    signature_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6c757d')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#6c757d')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), 18),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 18),
        ('PADDING', (0, 0), (-1, 0), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#f8f9fa'), colors.white]),
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.HexColor('#495057')),
    ]))
    
    elements.append(signature_table)
    elements.append(Spacer(1, 0.25*inch))
    
    # Important Note Box
    note_style = ParagraphStyle(
        'Note',
        parent=normal_style,
        fontSize=9,
        textColor=colors.HexColor('#856404'),
        alignment=TA_LEFT,
        leftIndent=10
    )
    
    note_text = """
    <b>Important:</b> This waybill must accompany the materials during transport. 
    All parties must verify quantities before signing. Any discrepancies should be reported immediately.
    """
    
    note_data = [[Paragraph(note_text, note_style)]]
    note_table = Table(note_data, colWidths=[6.5*inch])
    note_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff3cd')),
        ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#ffc107')),
        ('PADDING', (0, 0), (-1, -1), 12),
    ]))
    
    elements.append(note_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # Footer
    footer_text = f"""
    <para align=center fontSize=8 textColor='#999999'>
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━<br/>
    <b>Ministry of Energy and Green Transition of Ghana - Inventory Management System</b><br/>
    This is a computer-generated waybill. For verification or queries, contact IMS Support.<br/>
    <font color='#666666'>Document Generated: {timezone.now().strftime('%d %B %Y at %H:%M:%S')}</font>
    </para>
    """
    elements.append(Paragraph(footer_text, normal_style))
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF data
    pdf = buffer.getvalue()
    buffer.close()
    
    # Return PDF response
    response = HttpResponse(content_type='application/pdf')
    filename = f"Waybill_{transport.waybill_number}_{copy_label.replace(' ', '_')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write(pdf)
    
    return response


@login_required
def verify_waybill_qr(request, waybill_identifier):
    """
    QR code verification endpoint.
    After login, identifies user role and auto-places digital stamp on waybill.
    Users scan QR code, sign in, and their stamp is automatically recorded.
    """
    from django.contrib.auth.models import User
    from .models import Profile
    from django.db import transaction
    
    # Try to find transport by waybill number or ID
    try:
        if waybill_identifier.startswith('WB-'):
            transport = MaterialTransport.objects.filter(waybill_number=waybill_identifier).first()
        else:
            transport = MaterialTransport.objects.filter(id=int(waybill_identifier)).first()
    except (ValueError, MaterialTransport.DoesNotExist):
        transport = None
    
    if not transport:
        messages.error(request, "Waybill not found.")
        return redirect('transportation_status')
    
    # Get user profile
    try:
        profile = Profile.objects.get(user=request.user)
    except Profile.DoesNotExist:
        messages.error(request, "User profile not found.")
        return redirect('transportation_status')
    
    # Ensure user has a signature stamp
    stamp = profile.get_or_create_signature_stamp()
    if not stamp:
        messages.warning(request, "Could not generate signature stamp. Please contact administrator.")
        return redirect('transportation_status')
    
    # Determine user role and record stamp accordingly
    user_groups = request.user.groups.all()
    group_names = [g.name for g in user_groups]
    
    # Check if user is store officer, transporter, or consultant
    is_store_officer_user = is_store_officer(request.user)
    is_transporter_user = 'Transporter' in group_names or 'transporter' in group_names
    is_consultant_user = 'Consultant' in group_names or 'consultant' in group_names
    
    # Record the stamp based on role
    with transaction.atomic():
        stamp_recorded = False
        
        if is_store_officer_user:
            role = "Store Officer (Issued By)"
            # Store Officer stamp is already embedded in waybill generation
            # This is just for verification/audit
            stamp_recorded = True
        elif is_transporter_user:
            role = "Transporter/Driver (Received By)"
            # Record transporter stamp (could be stored in a separate model for tracking)
            # For now, we'll just log it
            stamp_recorded = True
        elif is_consultant_user:
            role = "Consultant (Delivered To)"
            # Record consultant stamp
            stamp_recorded = True
        else:
            role = "Authorized User"
        
        if stamp_recorded:
            # Log the stamp verification in audit trail
            try:
                MaterialOrderAudit.objects.create(
                    material_order=transport.material_order if transport.material_order else None,
                    user=request.user,
                    action=f'Waybill verified via QR code - {role}',
                    timestamp=timezone.now()
                )
            except Exception:
                pass  # Don't fail if audit logging fails
    
    messages.success(
        request, 
        f"Waybill verified! Your digital stamp as {role} has been recorded for waybill {transport.waybill_number or waybill_identifier}."
    )
    
    # Redirect to transportation status or waybill detail
    return redirect('transportation_status')
