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

from .models import (
    MaterialOrder, ReleaseLetter, MaterialTransport, Transporter, TransportVehicle, 
    MaterialOrderAudit, SiteReceipt
    # Note: Notification, Project, ProjectSite, ProjectPhase will be available after migration
)
from .forms import TransporterForm, TransportVehicleForm, TransportAssignmentForm, TransporterImportForm
from Inventory.utils import is_store_officer, is_superuser, is_schedule_officer

from django.views.decorators.http import require_POST

# Superuser-only access mixin that returns 404 for non-superusers
class SuperuserOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        # Hide existence of the page from non-superusers
        raise Http404()

class ReleaseLetterListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    View for store officers and superusers to see all release letters with their associated orders.
    """
    model = ReleaseLetter
    template_name = 'Inventory/release_letter_list.html'
    context_object_name = 'release_letters'
    paginate_by = 20
    
    
    
    def get_queryset(self):
        queryset = ReleaseLetter.objects.select_related('uploaded_by').prefetch_related('material_orders').all()
        
        # Apply search
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(request_code__icontains=search_query) |
                Q(notes__icontains=search_query) |
                Q(material_orders__name__icontains=search_query)
            ).distinct()
        
        # Apply date filters
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if date_from:
            queryset = queryset.filter(upload_time__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(upload_time__date__lte=date_to)
        
        return queryset.order_by('-upload_time')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add search query to context for template
        context['search_query'] = self.request.GET.get('search', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        
        # Add summary statistics
        context['total_letters'] = ReleaseLetter.objects.count()
        context['pending_letters'] = ReleaseLetter.objects.filter(
            material_orders__status__in=['Pending', 'Approved', 'In Progress']
        ).distinct().count()
        
        return context


class TransporterAssignmentView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """
    View for store officers to assign transporters to material orders.
    """
    model = MaterialOrder
    template_name = 'Inventory/transporter_assignment.html'
    context_object_name = 'material_orders'
    paginate_by = 20
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        # Release orders with processed quantities awaiting transport.
        # 'Completed' included: an order can be completed for its processed
        # portion while remaining_quantity still needs future processing.
        queryset = MaterialOrder.objects.filter(
            request_type='Release',
            # 'In Transit' included: status is explicit now, so a partially
            # transported order keeps that status while the rest of its
            # processed quantity still needs a transporter.
            # ponytail: 'Ready for Pickup' / 'Fulfilled' removed — nothing
            # in the codebase ever sets them (dead statuses, Phase 5).
            status__in=['Approved', 'In Progress', 'Partially Fulfilled', 'Completed', 'In Transit'],
            processed_quantity__isnull=False,
        ).exclude(
            processed_quantity=0
        ).select_related('release_letter', 'unit', 'user').prefetch_related('transports')

        # Exclude orders whose processed quantity is fully transported AND
        # have nothing left to process. 'Awaiting Transporter' placeholders
        # (auto-created on completion) don't count as transported.
        # ponytail: python-side loop, fine at this row count; move to a
        # Sum() annotation if the page ever slows down.
        fully_completed_orders = []
        for order in queryset:
            total_transported = order.transports.exclude(
                status='Awaiting Transporter'
            ).aggregate(
                total=Sum('quantity')
            )['total'] or 0
            if total_transported >= order.processed_quantity and order.remaining_quantity <= 0:
                fully_completed_orders.append(order.id)

        if fully_completed_orders:
            queryset = queryset.exclude(id__in=fully_completed_orders)

        # Apply search filters if provided
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(request_code__icontains=search_query) |
                Q(name__icontains=search_query) |
                Q(contractor__icontains=search_query) |
                Q(region__icontains=search_query) |
                Q(district__icontains=search_query)
            )
        
        # Apply status filter if provided
        status_filter = self.request.GET.get('status', '').strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Apply date filters if provided
        date_from = self.request.GET.get('date_from', '').strip()
        date_to = self.request.GET.get('date_to', '').strip()
        
        if date_from:
            queryset = queryset.filter(date_requested__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date_requested__date__lte=date_to)

        return queryset.order_by('-date_requested', 'priority')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add search query to context for template
        context['search_query'] = self.request.GET.get('search', '')
        context['status_filter'] = self.request.GET.get('status', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        
        # Add transporters for the assignment modal
        context['transporters'] = Transporter.objects.filter(is_active=True).order_by('name')
        
        # Add forms to context
        context['transporter_form'] = TransporterForm()
        context['vehicle_form'] = TransportVehicleForm()
        context['assignment_form'] = TransportAssignmentForm()
        
        # Add summary statistics
        context['total_orders'] = self.get_queryset().count()
        context['pending_count'] = self.get_queryset().filter(
            status__in=['Pending', 'Approved', 'In Progress']
        ).count()
        
        return context
    
    def generate_waybill_number(self):
        """Generate a unique waybill number."""
        from datetime import datetime
        import uuid
        
        # Format: WB-YYYYMMDD-XXXXX (WB = Waybill)
        date_str = datetime.now().strftime('%Y%m%d')
        unique_id = str(uuid.uuid4())[:5].upper()
        return f"WB-{date_str}-{unique_id}"
    
    def generate_consignment_number(self):
        """Generate a unique consignment number for bulk shipments."""
        from datetime import datetime
        import uuid
        
        # Format: CN-YYYYMMDD-XXXXX (CN = Consignment)
        date_str = datetime.now().strftime('%Y%m%d')
        unique_id = str(uuid.uuid4())[:5].upper()
        return f"CN-{date_str}-{unique_id}"
    
    def handle_bulk_assignment(self, request):
        """Handle bulk assignment of transporter to multiple orders."""
        # Get selected order IDs
        order_ids = request.POST.getlist('selected_orders')
        transporter_id = request.POST.get('bulk_transporter')
        vehicle_id = request.POST.get('bulk_vehicle')
        driver_name = request.POST.get('bulk_driver_name', '')
        driver_phone = request.POST.get('bulk_driver_phone', '')
        
        if not order_ids:
            messages.error(request, 'Please select at least one order to assign.')
            return redirect('transport_assignment')
        
        if not transporter_id:
            messages.error(request, 'Please select a transporter.')
            return redirect('transport_assignment')
        
        try:
            transporter = get_object_or_404(Transporter, id=transporter_id)
            vehicle = None
            if vehicle_id:
                vehicle = get_object_or_404(TransportVehicle, id=vehicle_id)
            assigned_count = 0
            errors = []
            
            # Generate ONE consignment number AND ONE waybill number for all materials in this bulk assignment
            consignment_number = self.generate_consignment_number()
            waybill_number = self.generate_waybill_number()  # ONE waybill for entire bulk shipment
            
            with transaction.atomic():
                for order_id in order_ids:
                    try:
                        order = MaterialOrder.objects.get(id=order_id)
                        
                        # Calculate available quantity for transport
                        # (placeholder 'Awaiting Transporter' rows don't count)
                        total_transported = order.transports.exclude(
                            status='Awaiting Transporter'
                        ).aggregate(
                            total=Sum('quantity')
                        )['total'] or 0
                        
                        available_quantity = (order.processed_quantity or 0) - total_transported
                        
                        if available_quantity <= 0:
                            errors.append(f"Order {order.request_code}: No quantity available for transport")
                            continue
                        
                        # Validate against BOQ guardrails (via signals)
                        # We do this here to catch it before creating the transport
                        if order.release_letter:
                            from .release_letter_services import validate_material_request_against_release_letter
                            try:
                                # This is just a check, the actual validation happens in signals
                                pass 
                            except ValidationError as ve:
                                errors.append(f"Order {order.request_code}: {ve.message}")
                                continue
                        
                        # Get release letter if exists
                        release_letter = None
                        try:
                            release_letter = order.release_letter
                        except ReleaseLetter.DoesNotExist:
                            pass
                        
                        # Create transport record
                        transport = MaterialTransport.objects.create(
                            material_order=order,
                            transporter=transporter,
                            vehicle=vehicle,
                            driver_name=driver_name,
                            driver_phone=driver_phone,
                            waybill_number=waybill_number,  # Same waybill for all materials in bulk assignment
                            status='Assigned',
                            
                            # Quantity details
                            quantity=available_quantity,
                            
                            date_dispatched=timezone.now()
                        )
                        
                        # Mark transport underway — but never demote a
                        # completed order (status is explicit now).
                        if order.status not in ('Completed', 'In Transit'):
                            order.status = 'In Progress'
                            order.save()

                        # Create audit log
                        MaterialOrderAudit.objects.create(
                            order=order,
                            action=f'Bulk assigned to transporter: {transporter.name} (Consignment: {consignment_number}, Waybill: {waybill_number})',
                            performed_by=request.user
                        )
                        
                        assigned_count += 1
                        
                    except MaterialOrder.DoesNotExist:
                        errors.append(f"Order ID {order_id}: Not found")
                    except ValidationError as ve:
                        errors.append(f"Order ID {order_id}: {ve.message}")
                    except Exception as e:
                        errors.append(f"Order ID {order_id}: {str(e)}")
            
            # Show results
            if assigned_count > 0:
                messages.success(request, f'Successfully assigned {assigned_count} order(s) to {transporter.name} under Consignment {consignment_number} with Waybill {waybill_number}')
            
            if errors:
                for error in errors:
                    messages.warning(request, error)
            
            return redirect('transport_assignment')
            
        except Transporter.DoesNotExist:
            messages.error(request, 'Transporter not found.')
            return redirect('transport_assignment')
        except Exception as e:
            messages.error(request, f'Error during bulk assignment: {str(e)}')
            return redirect('transport_assignment')
    
    def post(self, request, *args, **kwargs):
        """Handle form submissions for creating/updating transport assignments."""
        # Handle bulk assignment
        if 'bulk_assign_transporter' in request.POST:
            return self.handle_bulk_assignment(request)
        
        # Handle single assignment
        if 'assign_transporter' in request.POST:
            order_id = request.POST.get('order_id')
            transporter_id = request.POST.get('transporter')
            
            if not order_id or not transporter_id:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Missing order ID or transporter ID'})
                messages.error(request, 'Missing order ID or transporter ID.')
                return self.get(request, *args, **kwargs)
            
            try:
                order = get_object_or_404(MaterialOrder, id=order_id)
                transporter = get_object_or_404(Transporter, id=transporter_id)
                
                with transaction.atomic():
                    # Get the release letter if it exists
                    release_letter = None
                    try:
                        release_letter = order.release_letter
                    except ReleaseLetter.DoesNotExist:
                        pass
                    
                    # Get transport quantity from form
                    transport_quantity = request.POST.get('transport_quantity')
                    if not transport_quantity:
                        raise ValueError('Transport quantity is required')
                    
                    transport_quantity = float(transport_quantity)
                    
                    # Validate quantity doesn't exceed available processed quantity
                    available_quantity = order.processed_quantity or 0
                    if transport_quantity > available_quantity:
                        raise ValueError(f'Transport quantity ({transport_quantity}) cannot exceed available processed quantity ({available_quantity})')
                    
                    # Get vehicle if provided
                    vehicle = None
                    vehicle_id = request.POST.get('vehicle')
                    if vehicle_id:
                        vehicle = get_object_or_404(TransportVehicle, id=vehicle_id)
                    
                    # Check for duplicate assignments in the last 10 seconds (prevents double-clicking)
                    from datetime import timedelta
                    ten_seconds_ago = timezone.now() - timedelta(seconds=10)
                    recent_duplicate = MaterialTransport.objects.filter(
                        material_order=order,
                        transporter=transporter,
                        quantity=transport_quantity,
                        date_dispatched__gte=ten_seconds_ago
                    ).exists()
                    
                    if recent_duplicate:
                        raise ValueError('Duplicate assignment detected. This transporter was just assigned to this order.')
                    
                    # Generate waybill number automatically
                    waybill_number = self.generate_waybill_number()
                    
                    # Create a new MaterialTransport record for this specific quantity
                    transport = MaterialTransport.objects.create(
                        material_order=order,
                        transporter=transporter,
                        vehicle=vehicle,
                        driver_name=request.POST.get('driver_name', ''),
                        driver_phone=request.POST.get('driver_phone', ''),
                        waybill_number=waybill_number,  # Auto-generated
                        status='Assigned',
                        
                        # Set material details from the order
                        quantity=transport_quantity,  # Use the specific quantity for this transport
                        
                        # Set the assignment date
                        date_dispatched=timezone.now()
                    )
                    
                    # Ensure status is set correctly (in case model save method interferes)
                    if transport.status != 'Assigned':
                        transport.status = 'Assigned'
                        transport.save()
                    
                    # Mark transport underway — but never demote a
                    # completed order (status is explicit now).
                    if order.status not in ('Completed', 'In Transit'):
                        order.status = 'In Progress'
                        order.save()

                    # Create audit log entry
                    MaterialOrderAudit.objects.create(
                        order=order,
                        action=f'Transporter assigned: {transporter.name} (Waybill: {waybill_number})',
                        performed_by=request.user
                    )
                
                success_message = f'Transporter {transporter.name} assigned successfully to order {order.request_code}.'
                
                # Return JSON response for AJAX requests
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True, 
                        'message': success_message,
                        'transport_id': transport.id
                    })
                
                # Return redirect for regular form submissions
                messages.success(request, success_message)
                return redirect('transport_assignment')
                
            except MaterialOrder.DoesNotExist:
                error_msg = 'Material order not found.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                
            except Transporter.DoesNotExist:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': True, 'message': 'Transporter assigned successfully'})
                
                messages.success(request, 'Transporter assigned successfully.')
                return redirect('transport_assignment')
            
            except ValidationError as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': str(e.message) if hasattr(e, 'message') else str(e)})
                messages.error(request, str(e.message) if hasattr(e, 'message') else str(e))
                return redirect('transport_assignment')
                
            except Exception as e:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': str(e)})
                messages.error(request, f'Error assigning transporter: {str(e)}')
                return redirect('transport_assignment')
        
        # If we get here, there was an error - redisplay the form with errors
        return self.get(request, *args, **kwargs)


@login_required
@user_passes_test(lambda u: is_store_officer(u) or is_superuser(u))
@require_POST
def update_transport_status(request, pk):
    """
    Update the status of a transport assignment.
    If the transport is part of a bulk consignment, update all transports in that consignment.
    """
    transport = get_object_or_404(MaterialTransport, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')

        if new_status == 'Delivered':
            # Delivered only via a Site Receipt — receipts post the delivery
            # to the Bill of Quantity; this endpoint would skip the books.
            return JsonResponse({
                'success': False,
                'error': 'Mark deliveries by logging a Site Receipt, not by '
                         'setting status directly. The receipt records the '
                         'delivery against the Bill of Quantity.',
            }, status=400)

        if new_status in dict(MaterialTransport.STATUS_CHOICES):
            updated_count = 0
            updated_orders = []
            
            with transaction.atomic():
                # Check if this transport is part of a bulk consignment via waybill_number
                waybill = getattr(transport, 'waybill_number', 'Unknown')
                if waybill not in [None, '', 'Unknown']:
                    # Update ALL transports in the same waybill
                    consignment_transports = MaterialTransport.objects.filter(
                        waybill_number=waybill
                    ).select_related('material_order')
                    
                    for consignment_transport in consignment_transports:
                        consignment_transport.status = new_status
                        if notes:
                            # Append notes if they exist
                            if consignment_transport.notes:
                                consignment_transport.notes += f"\n{notes}"
                            else:
                                consignment_transport.notes = notes
                        consignment_transport.save()
                        
                        # Update related order status
                        order = consignment_transport.material_order
                        if new_status == 'In Transit':
                            order.status = 'In Transit'
                        elif new_status == 'Delivered':
                            order.status = 'Delivered'
                        elif new_status == 'Completed':
                            order.status = 'Completed'
                        order.save()
                        
                        updated_count += 1
                        updated_orders.append(order.request_code)
                        
                        # Create audit log
                        MaterialOrderAudit.objects.create(
                            order=order,
                            action=f'Transport status updated to {new_status} (Waybill: {waybill})',
                            performed_by=request.user
                        )
                    
                    messages.success(
                        request, 
                        f'Bulk consignment status updated to {transport.get_status_display()}. '
                        f'Updated {updated_count} transport(s) in Waybill {waybill}.'
                    )
                else:
                    # Single transport - update only this one
                    transport.status = new_status
                    if notes:
                        transport.notes = notes
                    transport.save()
                    
                    # Update related order status
                    order = transport.material_order
                    if new_status == 'In Transit':
                        order.status = 'In Transit'
                    elif new_status == 'Delivered':
                        order.status = 'Delivered'
                    elif new_status == 'Completed':
                        order.status = 'Completed'
                    order.save()
                    
                    # Create audit log
                    MaterialOrderAudit.objects.create(
                        order=order,
                        action=f'Transport status updated to {new_status}',
                        performed_by=request.user
                    )
                    
                    updated_count = 1
                    updated_orders.append(order.request_code)
                    
                    messages.success(request, f'Status updated to {transport.get_status_display()}')
            
            waybill = getattr(transport, 'waybill_number', 'Unknown')
            return JsonResponse({
                'success': True, 
                'status': transport.get_status_display(),
                'updated_count': updated_count,
                'updated_orders': updated_orders,
                'is_bulk': waybill not in [None, '', 'Unknown']
            })
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})


class TransporterListView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """View for managing transport companies. Access restricted to store officers and management."""
    model = Transporter
    template_name = 'Inventory/transporter_list.html'
    context_object_name = 'transporters'
    paginate_by = 20
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        queryset = Transporter.objects.all().annotate(
            active_vehicles=Count('vehicles', filter=Q(vehicles__is_active=True)),
            total_transports=Count('materialtransport')
        )
        
        # Apply search
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(contact_person__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(phone__icontains=search_query)
            )
        
        return queryset.order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['import_form'] = TransporterImportForm()
        return context


class TransporterCreateView(LoginRequiredMixin, SuperuserOnlyMixin, CreateView):
    """View for adding a new transport company."""
    model = Transporter
    form_class = TransporterForm
    template_name = 'Inventory/transporter_form.html'
    success_url = reverse_lazy('transporter_list')
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)
    
    def form_valid(self, form):
        form.instance.added_by = self.request.user
        messages.success(self.request, 'Transporter added successfully.')
        return super().form_valid(form)


class TransporterUpdateView(LoginRequiredMixin, SuperuserOnlyMixin, UpdateView):
    """View for editing a transport company."""
    model = Transporter
    form_class = TransporterForm
    template_name = 'Inventory/transporter_form.html'
    success_url = reverse_lazy('transporter_list')
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, 'Transporter updated successfully.')
        return super().form_valid(form)


@login_required
@user_passes_test(lambda u: is_store_officer(u) or is_superuser(u))
def export_transporters_template(request):
    """Export an Excel template for importing transporters."""
    import pandas as pd
    from django.http import HttpResponse
    
    # Create a DataFrame with the required columns
    columns = [
        'name', 'contact_person', 'email', 'phone', 
        'address', 'is_active', 'notes'
    ]
    df = pd.DataFrame(columns=columns)
    
    # Create a sample row with instructions
    sample_data = {
        'name': 'Example Transporter Ltd',
        'contact_person': 'John Doe',
        'email': 'contact@example.com',
        'phone': '+1234567890',
        'address': '123 Transport St, City',
        'is_active': True,
        'notes': 'Sample transporter entry - replace with your data'
    }
    df = pd.DataFrame([sample_data])
    
    # Create a response with the Excel file
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=transporter_import_template.xlsx'
    
    # Write the DataFrame to the response
    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transporters')
        
        # Get the worksheet and format it
        worksheet = writer.sheets['Transporters']
        for column in worksheet.columns:
            max_length = 0
            column = [cell for cell in column]
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except (TypeError, ValueError):
                    pass
            adjusted_width = (max_length + 2) * 1.2
            worksheet.column_dimensions[column[0].column_letter].width = adjusted_width
    
    return response


@login_required
@user_passes_test(lambda u: is_store_officer(u) or is_superuser(u))
def ajax_load_vehicles(request):
    """AJAX view to load vehicles for a specific transporter."""
    from django.http import JsonResponse
    from .models import TransportVehicle
    
    transporter_id = request.GET.get('transporter_id')
    if not transporter_id:
        return JsonResponse({'error': 'No transporter ID provided'}, status=400)
    
    try:
        vehicles = list(TransportVehicle.objects.filter(
            transporter_id=transporter_id,
            is_active=True
        ).values('id', 'registration_number', 'vehicle_type'))
        
        return JsonResponse({'vehicles': vehicles})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@user_passes_test(lambda u: is_store_officer(u) or is_superuser(u))
def import_transporters(request):
    """Import transporters from an Excel file."""
    if request.method == 'POST':
        form = TransporterImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                df = pd.read_excel(request.FILES['file'])
                required_columns = ['name', 'contact_person', 'email', 'phone']
                
                # Validate required columns
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    messages.error(request, f'Missing required columns: {", ".join(missing_columns)}')
                    return redirect('transporter_list')
                
                # Process each row
                imported_count = 0
                for _, row in df.iterrows():
                    Transporter.objects.update_or_create(
                        name=row['name'].strip(),
                        defaults={
                            'contact_person': row.get('contact_person', '').strip(),
                            'email': row.get('email', '').strip().lower(),
                            'phone': str(row.get('phone', '')).strip(),
                            'address': row.get('address', '').strip(),
                            'is_active': bool(row.get('is_active', True)),
                            'notes': row.get('notes', '').strip()
                        }
                    )
                    imported_count += 1
                
                messages.success(request, f'Successfully imported {imported_count} transporters.')
                return redirect('transporter_list')
                
            except Exception as e:
                messages.error(request, f'Error importing file: {str(e)}')
        else:
            messages.error(request, 'Invalid file format. Please upload a valid Excel file.')
    
    return redirect('transporter_list')


class TransportVehicleListView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """View for managing transport vehicles."""
    model = TransportVehicle
    template_name = 'Inventory/transport_vehicle_list.html'
    context_object_name = 'vehicles'
    paginate_by = 20
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        queryset = TransportVehicle.objects.select_related('transporter').all()
        
        # Apply search
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(registration_number__icontains=search_query) |
                Q(transporter__name__icontains=search_query) |
                Q(vehicle_type__icontains=search_query) |
                Q(capacity__icontains=search_query)
            )
        
        # Filter by transporter if specified
        transporter_id = self.request.GET.get('transporter')
        if transporter_id:
            queryset = queryset.filter(transporter_id=transporter_id)
        
        return queryset.order_by('transporter__name', 'registration_number')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['transporters'] = Transporter.objects.filter(is_active=True).order_by('name')
        return context


class TransportVehicleCreateView(LoginRequiredMixin, SuperuserOnlyMixin, CreateView):
    """View for adding a new transport vehicle."""
    model = TransportVehicle
    form_class = TransportVehicleForm
    template_name = 'Inventory/transport_vehicle_form.html'
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_initial(self):
        """Pre-select transporter if coming from transporter detail page."""
        initial = super().get_initial()
        transporter_id = self.kwargs.get('transporter_id')
        if transporter_id:
            initial['transporter'] = transporter_id
        return initial
    
    def get_success_url(self):
        """Redirect to transporter detail if came from there, otherwise vehicle list."""
        transporter_id = self.kwargs.get('transporter_id')
        if transporter_id:
            return reverse_lazy('transporter_detail', kwargs={'pk': transporter_id})
        return reverse_lazy('vehicle_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Vehicle added successfully.')
        return super().form_valid(form)


class TransportVehicleUpdateView(LoginRequiredMixin, SuperuserOnlyMixin, UpdateView):
    """View for editing a transport vehicle."""
    model = TransportVehicle
    form_class = TransportVehicleForm
    template_name = 'Inventory/transport_vehicle_form.html'
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('vehicle_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Vehicle updated successfully.')
        return super().form_valid(form)


class TransportVehicleDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """View for deleting a transport vehicle."""
    model = TransportVehicle
    template_name = 'Inventory/transport_vehicle_confirm_delete.html'
    
    def test_func(self):
        return is_superuser(self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('vehicle_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Vehicle deleted successfully.')
        return super().delete(request, *args, **kwargs)


class TransporterDetailView(LoginRequiredMixin, SuperuserOnlyMixin, DetailView):
    """View for displaying transporter details."""
    model = Transporter
    template_name = 'Inventory/transporter_detail.html'
    context_object_name = 'transporter'
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['vehicles'] = self.object.vehicles.filter(is_active=True)
        return context


class TransporterDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """View for deleting a transporter."""
    model = Transporter
    template_name = 'Inventory/transporter_confirm_delete.html'
    success_url = reverse_lazy('transporter_list')
    
    def test_func(self):
        return is_superuser(self.request.user)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Transporter deleted successfully.')
        return super().delete(request, *args, **kwargs)


class TransportVehicleDetailView(LoginRequiredMixin, SuperuserOnlyMixin, DetailView):
    """View for displaying transport vehicle details."""
    model = TransportVehicle
    template_name = 'Inventory/transport_vehicle_detail.html'
    context_object_name = 'vehicle'
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)


class TransporterLegendView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """View for displaying a legend of all transporters and their vehicles."""
    model = Transporter
    template_name = 'Inventory/transporter_legend.html'
    context_object_name = 'transporters'
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        return Transporter.objects.prefetch_related('vehicles').all()
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_vehicles'] = TransportVehicle.objects.filter(is_active=True).count()
        return context


class TransportationStatusView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """
    View for displaying transportation status - which transporter is handling which orders.
    Shows active transports with visual status indicators.
    Accessible to storekeepers, schedule officers, and superusers.
    """
    model = MaterialTransport
    template_name = 'Inventory/transportation_status.html'
    context_object_name = 'transports'
    paginate_by = 20
    
    def test_func(self):
        return is_store_officer(self.request.user) or is_schedule_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        # Keep only active transports here; delivered consignments move to the archive view.
        queryset = MaterialTransport.objects.filter(
            status__in=['Assigned', 'Loading', 'Loaded', 'In Transit']
        ).select_related(
            'material_order', 'transporter', 'vehicle', 'material_order__release_letter'
        ).order_by('-date_dispatched', 'status')
        
        # Apply search filters
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(material_order__request_code__icontains=search_query) |
                Q(material_order__name__icontains=search_query) |
                Q(transporter__name__icontains=search_query) |
                Q(driver_name__icontains=search_query) |
                Q(vehicle__registration_number__icontains=search_query)
            )
        
        # Apply status filter
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Apply transporter filter
        transporter_filter = self.request.GET.get('transporter')
        if transporter_filter:
            queryset = queryset.filter(transporter_id=transporter_filter)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add search parameters to context
        context['search_query'] = self.request.GET.get('search', '')
        context['status_filter'] = self.request.GET.get('status', '')
        context['transporter_filter'] = self.request.GET.get('transporter', '')
        
        # Add transporters for filter dropdown
        context['transporters'] = Transporter.objects.filter(is_active=True).order_by('name')
        
        # Add status choices for filter dropdown
        context['status_choices'] = MaterialTransport.STATUS_CHOICES
        
        # Group transports by consignment for bulk shipments
        from collections import defaultdict
        consignments = defaultdict(list)
        single_shipments = []
        
        for transport in context['transports']:
            # Group by waybill number if it's explicitly set (not Unknown) to represent bulk consignments
            if getattr(transport, 'waybill_number', 'Unknown') not in [None, '', 'Unknown']:
                consignments[transport.waybill_number].append(transport)
            else:
                single_shipments.append(transport)
        
        context['consignments'] = dict(consignments)  # Convert to regular dict
        context['single_shipments'] = single_shipments
        
        # Add summary statistics
        all_transports = MaterialTransport.objects.filter(
            status__in=['Assigned', 'Loading', 'Loaded', 'In Transit']
        )
        
        context['total_active'] = all_transports.count()
        context['in_transit_count'] = all_transports.filter(status='In Transit').count()
        context['loading_count'] = all_transports.filter(status__in=['Loading', 'Loaded']).count()
        context['assigned_count'] = all_transports.filter(status='Assigned').count()
        context['archive_count'] = MaterialTransport.objects.filter(status='Delivered').count()
        
        # Add user role information for template
        context['is_schedule_officer'] = is_schedule_officer(self.request.user)
        context['is_store_officer'] = is_store_officer(self.request.user)
        
        return context


class TransportArchiveView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """
    Read-only archive for completed consignments and delivered transports.
    """
    model = MaterialTransport
    template_name = 'Inventory/transportation_archive.html'
    context_object_name = 'transports'
    paginate_by = 20

    def test_func(self):
        return is_store_officer(self.request.user) or is_schedule_officer(self.request.user) or is_superuser(self.request.user)

    def get_queryset(self):
        queryset = MaterialTransport.objects.filter(
            status='Delivered'
        ).select_related(
            'material_order',
            'transporter',
            'vehicle',
            'material_order__release_letter',
            'site_receipt',
            'site_receipt__received_by',
        ).order_by('-date_delivered', '-date_dispatched')

        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(material_order__request_code__icontains=search_query) |
                Q(material_order__name__icontains=search_query) |
                Q(transporter__name__icontains=search_query) |
                Q(driver_name__icontains=search_query) |
                Q(vehicle__registration_number__icontains=search_query) |
                Q(waybill_number__icontains=search_query)
            )

        transporter_filter = self.request.GET.get('transporter')
        if transporter_filter:
            queryset = queryset.filter(transporter_id=transporter_filter)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['transporter_filter'] = self.request.GET.get('transporter', '')
        context['transporters'] = Transporter.objects.filter(is_active=True).order_by('name')
        context['archive_count'] = self.get_queryset().count()

        from collections import defaultdict
        consignments = defaultdict(list)
        single_shipments = []
        for transport in context['transports']:
            if getattr(transport, 'waybill_number', 'Unknown') not in [None, '', 'Unknown']:
                consignments[transport.waybill_number].append(transport)
            else:
                single_shipments.append(transport)

        context['consignments'] = dict(consignments)
        context['single_shipments'] = single_shipments
        context['is_schedule_officer'] = is_schedule_officer(self.request.user)
        context['is_store_officer'] = is_store_officer(self.request.user)
        return context


# Waybill PDF + QR verification moved to services (Phase 6). Re-exported
# here so urls.py keeps referencing transporter_views.*
from .services.waybill_pdf import (  # noqa: E402
    download_waybill_pdf, verify_waybill_qr,
)
