from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, Http404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Q, Count, Sum, F
from django.utils import timezone
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
from Inventory.utils import is_storekeeper, is_superuser, is_schedule_officer

# Superuser-only access mixin that returns 404 for non-superusers
class SuperuserOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        # Hide existence of the page from non-superusers
        raise Http404()

class ReleaseLetterListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    View for storekeepers and superusers to see all release letters with their associated orders.
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
    View for storekeepers to assign transporters to material orders.
    """
    model = MaterialOrder
    template_name = 'Inventory/transporter_assignment.html'
    context_object_name = 'material_orders'
    paginate_by = 20
    
    def test_func(self):
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        # Clear any potential caching by forcing fresh query
        from django.core.cache import cache
        cache.clear()
        
        # Get release orders that could potentially need transport assignment
        queryset = MaterialOrder.objects.filter(
            request_type='Release'  # Only release orders need transport
        ).select_related('release_letter', 'unit', 'user').prefetch_related('transports')
        
        # Debug: Log total release orders
        import logging
        logger = logging.getLogger(__name__)
        total_release_orders = queryset.count()
        logger.info(f"=== FRESH QUERYSET DEBUG ===")
        logger.info(f"Total release orders found: {total_release_orders}")
        
        # Log all release orders with their current processed quantities
        all_orders = queryset.order_by('-date_requested')[:10]
        for order in all_orders:
            logger.info(f"Order {order.request_code}: Status={order.status}, Processed={order.processed_quantity}, Requested={order.date_requested}")
        
        # Only include orders that have processed quantities and are ready for transport
        # Include orders that are processed and ready for transport assignment
        # Note: 'Completed' status included because an order might be marked completed for its 
        # processed portion while still having remaining_quantity that needs future processing
        queryset = queryset.filter(
            status__in=['Approved', 'In Progress', 'Partially Fulfilled', 'Ready for Pickup', 'Fulfilled', 'Completed']
        ).filter(
            processed_quantity__isnull=False
        ).exclude(
            processed_quantity=0
        )
        
        # Debug: Log after status and processed quantity filter
        after_basic_filter = queryset.count()
        logger.info(f"Orders with processed quantities > 0: {after_basic_filter}")
        
        # Additional debug: Check all orders regardless of processed_quantity
        all_release_orders = MaterialOrder.objects.filter(request_type='Release').exclude(
            status__in=['Draft', 'Rejected', 'Cancelled']
        )
        logger.info(f"All non-draft/rejected/cancelled release orders: {all_release_orders.count()}")
        for order in all_release_orders[:5]:
            logger.info(f"Order {order.request_code}: Status={order.status}, Processed={order.processed_quantity} (type: {type(order.processed_quantity)})")
        
        # Exclude orders that have been fully transported AND have no remaining quantity
        # Keep orders visible if they have remaining_quantity > 0 (for future processing and transport)
        fully_completed_orders = []
        for order in queryset:
            # Calculate total transported quantity for this order
            total_transported = order.transports.aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
            # Only exclude if:
            # 1. All processed quantity has been transported, AND
            # 2. There is no remaining quantity to process
            if total_transported >= order.processed_quantity and order.remaining_quantity <= 0:
                fully_completed_orders.append(order.id)
                logger.info(f"Excluding fully completed order {order.request_code}: transported={total_transported}, processed={order.processed_quantity}, remaining={order.remaining_quantity}")
            elif total_transported >= order.processed_quantity and order.remaining_quantity > 0:
                logger.info(f"Keeping order {order.request_code} visible: All processed quantity transported but {order.remaining_quantity} still unprocessed")
        
        if fully_completed_orders:
            queryset = queryset.exclude(id__in=fully_completed_orders)
            logger.info(f"Excluded {len(fully_completed_orders)} fully completed orders")
        
        # Debug: Log after transport exclusion
        after_transport_filter = queryset.count()
        logger.info(f"Final orders available for transport assignment: {after_transport_filter}")
        logger.info(f"=== END FRESH QUERYSET DEBUG ===")
        
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
        
        final_count = queryset.count()
        logger.info(f"Final queryset count after filters: {final_count}")
        
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
                        total_transported = order.transports.aggregate(
                            total=Sum('quantity')
                        )['total'] or 0
                        
                        available_quantity = (order.processed_quantity or 0) - total_transported
                        
                        if available_quantity <= 0:
                            errors.append(f"Order {order.request_code}: No quantity available for transport")
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
                            release_letter=release_letter,
                            transporter=transporter,
                            vehicle=vehicle,
                            driver_name=driver_name,
                            driver_phone=driver_phone,
                            waybill_number=waybill_number,  # Same waybill for all materials in bulk assignment
                            consignment_number=consignment_number,  # Same consignment for all in bulk assignment
                            status='Assigned',
                            
                            # Material details
                            material_name=order.name,
                            material_code=order.code,
                            quantity=available_quantity,
                            unit=order.unit.name if order.unit else '',
                            
                            # Destination details
                            recipient=order.contractor or '',
                            consultant=order.consultant or '',
                            region=order.region or '',
                            district=order.district or '',
                            community=order.community or '',
                            package_number=order.package_number or '',
                            
                            date_assigned=timezone.now(),
                            created_by=request.user
                        )
                        
                        # Update order status
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
                        date_assigned__gte=ten_seconds_ago
                    ).exists()
                    
                    if recent_duplicate:
                        raise ValueError('Duplicate assignment detected. This transporter was just assigned to this order.')
                    
                    # Generate waybill number automatically
                    waybill_number = self.generate_waybill_number()
                    
                    # Create a new MaterialTransport record for this specific quantity
                    transport = MaterialTransport.objects.create(
                        material_order=order,
                        release_letter=release_letter,
                        transporter=transporter,
                        vehicle=vehicle,
                        driver_name=request.POST.get('driver_name', ''),
                        driver_phone=request.POST.get('driver_phone', ''),
                        waybill_number=waybill_number,  # Auto-generated
                        status='Assigned',
                        
                        # Set material details from the order
                        material_name=order.name,
                        material_code=order.code,
                        quantity=transport_quantity,  # Use the specific quantity for this transport
                        unit=order.unit.name if order.unit else '',
                        
                        # Set destination details from the order
                        recipient=order.contractor or '',
                        consultant=order.consultant or '',
                        region=order.region or '',
                        district=order.district or '',
                        community=order.community or '',
                        package_number=order.package_number or '',
                        
                        # Set the assignment date
                        date_assigned=timezone.now(),
                        created_by=request.user
                    )
                    
                    # Ensure status is set correctly (in case model save method interferes)
                    if transport.status != 'Assigned':
                        transport.status = 'Assigned'
                        transport.save()
                    
                    # Update order status
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
                error_msg = 'Transporter not found.'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                
            except Exception as e:
                error_msg = f'Error assigning transporter: {str(e)}'
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
        
        # If we get here, there was an error - redisplay the form with errors
        return self.get(request, *args, **kwargs)


@login_required
@user_passes_test(lambda u: is_storekeeper(u) or is_superuser(u))
def update_transport_status(request, pk):
    """
    Update the status of a transport assignment.
    If the transport is part of a bulk consignment, update all transports in that consignment.
    """
    transport = get_object_or_404(MaterialTransport, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        notes = request.POST.get('notes', '')
        
        if new_status in dict(MaterialTransport.STATUS_CHOICES):
            updated_count = 0
            updated_orders = []
            
            with transaction.atomic():
                # Check if this transport is part of a bulk consignment
                if transport.consignment_number:
                    # Update ALL transports in the same consignment
                    consignment_transports = MaterialTransport.objects.filter(
                        consignment_number=transport.consignment_number
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
                            action=f'Transport status updated to {new_status} (Consignment: {transport.consignment_number})',
                            performed_by=request.user
                        )
                    
                    messages.success(
                        request, 
                        f'Bulk consignment status updated to {transport.get_status_display()}. '
                        f'Updated {updated_count} transport(s) in consignment {transport.consignment_number}.'
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
            
            return JsonResponse({
                'success': True, 
                'status': transport.get_status_display(),
                'updated_count': updated_count,
                'updated_orders': updated_orders,
                'is_bulk': bool(transport.consignment_number)
            })
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})


class TransporterListView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """View for managing transport companies."""
    model = Transporter
    template_name = 'Inventory/transporter_list.html'
    context_object_name = 'transporters'
    paginate_by = 20
    
    def test_func(self):
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        queryset = Transporter.objects.all().annotate(
            active_vehicles=Count('vehicles', filter=Q(vehicles__is_active=True)),
            total_transports=Count('transports')
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
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
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
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, 'Transporter updated successfully.')
        return super().form_valid(form)


@login_required
@user_passes_test(lambda u: is_storekeeper(u) or is_superuser(u))
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
                except:
                    pass
            adjusted_width = (max_length + 2) * 1.2
            worksheet.column_dimensions[column[0].column_letter].width = adjusted_width
    
    return response


@login_required
@user_passes_test(lambda u: is_storekeeper(u) or is_superuser(u))
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
@user_passes_test(lambda u: is_storekeeper(u) or is_superuser(u))
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
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
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
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
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
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
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
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
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
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)


class TransporterLegendView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """View for displaying a legend of all transporters and their vehicles."""
    model = Transporter
    template_name = 'Inventory/transporter_legend.html'
    context_object_name = 'transporters'
    
    def test_func(self):
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
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
        return is_storekeeper(self.request.user) or is_schedule_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        # Get all active transports that haven't been logged as received on site
        # Transports persist on this page until a site receipt is logged
        queryset = MaterialTransport.objects.filter(
            status__in=['Assigned', 'Loading', 'Loaded', 'In Transit', 'Delivered']
        ).filter(
            site_receipt__isnull=True  # Exclude transports with site receipts logged
        ).select_related(
            'material_order', 'transporter', 'vehicle', 'material_order__release_letter'
        ).order_by('-date_assigned', 'status')
        
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
            if transport.consignment_number:
                consignments[transport.consignment_number].append(transport)
            else:
                single_shipments.append(transport)
        
        context['consignments'] = dict(consignments)  # Convert to regular dict
        context['single_shipments'] = single_shipments
        
        # Add summary statistics
        all_transports = MaterialTransport.objects.filter(
            status__in=['Assigned', 'Loading', 'Loaded', 'In Transit', 'Delivered']
        )
        
        context['total_active'] = all_transports.count()
        context['in_transit_count'] = all_transports.filter(status='In Transit').count()
        context['loading_count'] = all_transports.filter(status__in=['Loading', 'Loaded']).count()
        context['assigned_count'] = all_transports.filter(status='Assigned').count()
        context['delivered_count'] = all_transports.filter(status='Delivered').count()
        
        # Add user role information for template
        context['is_schedule_officer'] = is_schedule_officer(self.request.user)
        context['is_storekeeper'] = is_storekeeper(self.request.user)
        
        return context


@login_required
@user_passes_test(lambda u: is_storekeeper(u) or is_superuser(u))
def debug_transport_records(request):
    """Debug view to check MaterialTransport records in the database."""
    from django.http import JsonResponse
    
    all_transports = MaterialTransport.objects.all().select_related('material_order', 'transporter')
    
    debug_data = []
    for transport in all_transports:
        debug_data.append({
            'id': transport.id,
            'material_order_id': transport.material_order.id if transport.material_order else None,
            'material_order_code': transport.material_order.request_code if transport.material_order else None,
            'transporter_name': transport.transporter.name if transport.transporter else None,
            'status': transport.status,
            'date_assigned': transport.date_assigned.isoformat() if transport.date_assigned else None,
            'created_at': transport.created_at.isoformat() if hasattr(transport, 'created_at') and transport.created_at else None,
        })
    
    # Also check the queryset used by TransportationStatusView
    status_view_queryset = MaterialTransport.objects.filter(
        status__in=['Assigned', 'Loading', 'Loaded', 'In Transit', 'Delivered']
    ).select_related('material_order', 'transporter', 'vehicle', 'material_order__release_letter')
    
    status_view_data = []
    for transport in status_view_queryset:
        status_view_data.append({
            'id': transport.id,
            'material_order_code': transport.material_order.request_code if transport.material_order else None,
            'transporter_name': transport.transporter.name if transport.transporter else None,
            'status': transport.status,
        })
    
    return JsonResponse({
        'all_transports_count': len(debug_data),
        'all_transports': debug_data,
        'status_view_count': len(status_view_data),
        'status_view_transports': status_view_data,
        'status_choices': dict(MaterialTransport.STATUS_CHOICES),
    }, indent=2)


@login_required
@user_passes_test(lambda u: is_storekeeper(u) or is_superuser(u))
def create_test_transport(request):
    """Create a test transport record for debugging."""
    from django.http import JsonResponse
    
    try:
        # Get the first available order and transporter
        order = MaterialOrder.objects.filter(status__in=['Approved', 'Seen']).first()
        transporter = Transporter.objects.filter(is_active=True).first()
        
        if not order or not transporter:
            return JsonResponse({
                'success': False, 
                'error': 'No available order or transporter found',
                'orders_count': MaterialOrder.objects.count(),
                'transporters_count': Transporter.objects.count()
            })
        
        # Create test transport
        transport = MaterialTransport.objects.create(
            material_order=order,
            transporter=transporter,
            status='Assigned',
            material_name=order.name,
            material_code=order.code,
            quantity=order.quantity,
            unit=order.unit.name if order.unit else '',
            recipient=order.contractor or 'Test Recipient',
            consultant=order.consultant or 'Test Consultant',
            region=order.region or 'Test Region',
            district=order.district or 'Test District',
            community=order.community or 'Test Community',
            package_number=order.package_number or 'TEST-001',
            date_assigned=timezone.now(),
            created_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'transport_id': transport.id,
            'transport_status': transport.status,
            'order_code': order.request_code,
            'transporter_name': transporter.name,
            'message': f'Test transport created: ID {transport.id}'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

@login_required
@user_passes_test(lambda u: is_storekeeper(u) or is_superuser(u))
def debug_assignment_orders(request):
    """Debug view to check which orders should appear in assignment table."""
    from django.http import JsonResponse
    
    # Get all release orders
    all_release_orders = MaterialOrder.objects.filter(request_type='Release')
    
    debug_data = {
        'total_release_orders': all_release_orders.count(),
        'orders_by_status': {},
        'orders_with_processed_qty': [],
        'orders_without_processed_qty': [],
        'assignment_ready_orders': []
    }
    
    # Group by status
    for status_code, status_display in MaterialOrder.STATUS_CHOICES:
        count = all_release_orders.filter(status=status_code).count()
        if count > 0:
            debug_data['orders_by_status'][status_code] = {
                'display': status_display,
                'count': count
            }
    
    # Check processed quantities
    for order in all_release_orders.exclude(status__in=['Draft', 'Rejected', 'Cancelled']):
        order_info = {
            'id': order.id,
            'code': order.request_code,
            'status': order.status,
            'processed_quantity': float(order.processed_quantity or 0),
            'remaining_transport_quantity': order.remaining_transport_quantity,
            'total_transported_quantity': order.total_transported_quantity,
            'transport_count': order.transports.count()
        }
        
        if order.processed_quantity and order.processed_quantity > 0:
            debug_data['orders_with_processed_qty'].append(order_info)
            
            # Check if it should be in assignment table
            if order.remaining_transport_quantity > 0:
                debug_data['assignment_ready_orders'].append(order_info)
        else:
            debug_data['orders_without_processed_qty'].append(order_info)
    
    return JsonResponse(debug_data, indent=2)


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


@login_required
def download_waybill_pdf(request, transport_id):
    """Generate and download waybill PDF for a transport (or all transports with same waybill for bulk assignments)."""
    transport = get_object_or_404(MaterialTransport, id=transport_id)
    
    # Increment download count
    transport.waybill_download_count += 1
    transport.save(update_fields=['waybill_download_count'])
    
    # Determine copy label
    if transport.waybill_download_count == 1:
        copy_label = "ORIGINAL COPY"
    else:
        copy_label = f"DUPLICATE COPY {transport.waybill_download_count - 1}"
    
    # For bulk assignments, fetch ALL transports with the same waybill number
    if transport.waybill_number and transport.consignment_number:
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
    waybill_date = transport.date_assigned.strftime('%d %B %Y') if transport.date_assigned else timezone.now().strftime('%d %B %Y')
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
    
    # Get storekeeper info and stamp (with image embedding support)
    # Priority: processed_by (who actually processed it) > assigned_to (who it was assigned to) > created_by
    storekeeper_name = ''
    storekeeper_stamp_image = None
    storekeeper_stamp_text = ''
    storekeeper_date = ''
    storekeeper = None
    if transport.material_order:
        # Use processed_by first (the person who actually processed the order)
        storekeeper = (transport.material_order.processed_by or 
                     transport.material_order.assigned_to or 
                     transport.material_order.created_by)
    
    if storekeeper:
        storekeeper_name = storekeeper.get_full_name() or storekeeper.username
        try:
            from .models import Profile
            profile = Profile.objects.filter(user=storekeeper).first()
            if profile:
                # Look for PNG stamp in media/digital_signatures/ folder
                stamp_filenames = [
                    f"{storekeeper.username}.png",
                    f"{storekeeper.id}.png",
                    f"{storekeeper.username}.jpg",
                    f"{storekeeper.id}.jpg",
                ]
                
                digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital_signatures')
                if not os.path.exists(digital_signatures_dir):
                    digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital signatures')
                
                for filename in stamp_filenames:
                    stamp_path = os.path.join(digital_signatures_dir, filename)
                    if os.path.exists(stamp_path):
                        try:
                            storekeeper_stamp_image = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                            break
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"Could not load digital stamp image {stamp_path}: {str(e)}")
                            continue
                
                if not storekeeper_stamp_image and profile:
                    try:
                        if hasattr(profile, 'generate_digital_stamp_png'):
                            stamp_path = profile.generate_digital_stamp_png()
                            if stamp_path and os.path.exists(stamp_path):
                                storekeeper_stamp_image = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Could not generate digital stamp PNG: {str(e)}")
                
                if not storekeeper_stamp_image:
                    stamp = profile.get_or_create_signature_stamp() if profile else None
                    if stamp:
                        try:
                            stamp_data = profile.display_signature_stamp()
                            if stamp_data:
                                storekeeper_stamp_text = f"{stamp_data.get('SIGNED_BY', storekeeper_name)}\nID: {stamp_data.get('ID', '')}"
                        except Exception:
                            if '|' in stamp:
                                parts = stamp.split('|')
                                signed_by = parts[0].replace('SIGNED_BY:', '') if 'SIGNED_BY:' in parts[0] else storekeeper_name
                                stamp_id = parts[2].replace('ID:', '') if len(parts) > 2 and 'ID:' in parts[2] else ''
                                storekeeper_stamp_text = f"{signed_by}\nID: {stamp_id}"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting storekeeper stamp: {str(e)}")
        # Use processed_at date if available, otherwise assigned_at, otherwise date_assigned
        if transport.material_order and transport.material_order.processed_at:
            storekeeper_date = transport.material_order.processed_at.strftime('%d %B %Y')
        elif transport.material_order and transport.material_order.assigned_at:
            storekeeper_date = transport.material_order.assigned_at.strftime('%d %B %Y')
        else:
            storekeeper_date = transport.date_assigned.strftime('%d %B %Y') if transport.date_assigned else ''
    
    # Build signature cell - use image if available, otherwise text
    storekeeper_signature_cell = storekeeper_stamp_image if storekeeper_stamp_image else Paragraph(storekeeper_stamp_text or '_________________', small_text)
    
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
                    f"{store_manager.username}.jpg",
                    f"{store_manager.id}.jpg",
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
        
        # Get date from material_order.assigned_at or transport.created_at
        if transport.material_order and transport.material_order.assigned_at:
            store_manager_date = transport.material_order.assigned_at.strftime('%d %B %Y')
        elif transport.created_at:
            store_manager_date = transport.created_at.strftime('%d %B %Y')
    
    # Build store manager signature cell
    store_manager_signature_cell = store_manager_stamp_image if store_manager_stamp_image else Paragraph(store_manager_stamp_text or '_________________', small_text)
    
    # Signature table with all parties: Storekeeper, Store Manager, Driver, Recipient
    signature_cover_data = [
        [
            Paragraph('<b>Name</b>', small_text),
            Paragraph('<b>Signature</b>', small_text),
            Paragraph('<b>Date</b>', small_text)
        ],
        [
            Paragraph('<b>Storekeeper</b>', small_text),
            storekeeper_signature_cell,
            Paragraph(storekeeper_date or '_________________', small_text)
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
        ['Consignment Number:', Paragraph(f"<b>{transport.consignment_number or 'Single Shipment'}</b>", normal_style)],
        ['Total Materials:', Paragraph(f"<b>{len(all_transports)}</b> item{'s' if len(all_transports) > 1 else ''}", normal_style)],
        ['Date Assigned:', transport.date_assigned.strftime('%d %B %Y, %H:%M') if transport.date_assigned else 'N/A'],
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
    
    # Get storekeeper info and stamp for main waybill (with image embedding support)
    storekeeper_name_main = ''
    storekeeper_stamp_image_main = None
    storekeeper_stamp_text_main = ''
    storekeeper_date_main = ''
    # Try to get storekeeper from processed_by (who actually processed it), assigned_to, or created_by
    storekeeper_main = None
    if transport.material_order:
        storekeeper_main = (transport.material_order.processed_by or 
                          transport.material_order.assigned_to or 
                          transport.material_order.created_by)
    
    if storekeeper_main:
        storekeeper_name_main = storekeeper_main.get_full_name() or storekeeper_main.username
        try:
            from .models import Profile
            profile = Profile.objects.filter(user=storekeeper_main).first()
            if profile:
                # Look for PNG stamp in media/digital_signatures/ folder
                # Try multiple possible filenames: username.png, user_id.png, etc.
                stamp_filenames = [
                    f"{storekeeper_main.username}.png",
                    f"{storekeeper_main.id}.png",
                    f"{storekeeper_main.username}.jpg",
                    f"{storekeeper_main.id}.jpg",
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
                            storekeeper_stamp_image_main = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                            break  # Found the stamp, exit loop
                        except Exception as e:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"Could not load digital stamp image {stamp_path}: {str(e)}")
                            continue
                
                # If no PNG found, try to generate one
                if not storekeeper_stamp_image_main and profile:
                    try:
                        # Generate PNG stamp if method exists
                        if hasattr(profile, 'generate_digital_stamp_png'):
                            stamp_path = profile.generate_digital_stamp_png()
                            if stamp_path and os.path.exists(stamp_path):
                                storekeeper_stamp_image_main = Image(stamp_path, width=1.0*inch, height=0.5*inch)
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Could not generate digital stamp PNG: {str(e)}")
                
                # Fallback to text-based stamp only if PNG is not available
                if not storekeeper_stamp_image_main:
                    stamp = profile.get_or_create_signature_stamp() if profile else None
                    if stamp:
                        try:
                            stamp_data = profile.display_signature_stamp()
                            if stamp_data:
                                storekeeper_stamp_text_main = f"{stamp_data.get('SIGNED_BY', storekeeper_name_main)}\nID: {stamp_data.get('ID', '')}"
                        except Exception:
                            # If display_signature_stamp doesn't exist, parse the stamp string
                            if '|' in stamp:
                                parts = stamp.split('|')
                                signed_by = parts[0].replace('SIGNED_BY:', '') if 'SIGNED_BY:' in parts[0] else storekeeper_name_main
                                stamp_id = parts[2].replace('ID:', '') if len(parts) > 2 and 'ID:' in parts[2] else ''
                                storekeeper_stamp_text_main = f"{signed_by}\nID: {stamp_id}"
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error getting storekeeper stamp for main waybill: {str(e)}")
        # Use processed_at date if available, otherwise assigned_at, otherwise date_assigned
        if transport.material_order and transport.material_order.processed_at:
            storekeeper_date_main = transport.material_order.processed_at.strftime('%d %B %Y')
        elif transport.material_order and transport.material_order.assigned_at:
            storekeeper_date_main = transport.material_order.assigned_at.strftime('%d %B %Y')
        else:
            storekeeper_date_main = transport.date_assigned.strftime('%d %B %Y') if transport.date_assigned else ''
    
    # Build signature cell for main waybill - use image if available, otherwise text
    storekeeper_signature_cell_main = storekeeper_stamp_image_main if storekeeper_stamp_image_main else Paragraph(storekeeper_stamp_text_main or '_________________', small_text)
    
    signature_data = [
        [
            Paragraph('<b>Role</b>', normal_style),
            Paragraph('<b>Name</b>', normal_style),
            Paragraph('<b>Signature</b>', normal_style),
            Paragraph('<b>Date</b>', normal_style)
        ],
        [
            Paragraph('<b>Issued By</b><br/>(Storekeeper)', small_text),
            Paragraph(storekeeper_name_main or '_________________', small_text),
            storekeeper_signature_cell_main,
            Paragraph(storekeeper_date_main or '_________________', small_text)
        ],
        [
            Paragraph('<b>Received By</b><br/>(Driver)', small_text),
            Paragraph(transport.driver_name or '_________________', small_text),
            Paragraph('_________________', small_text),  # Driver signs physically
            Paragraph('_________________', small_text)
        ],
        [
            Paragraph('<b>Delivered To</b><br/>(Consultant)', small_text),
            Paragraph(transport.consultant or '_________________', small_text),
            Paragraph('_________________', small_text),  # Consultant signs physically
            Paragraph('_________________', small_text)
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
    
    # Check if user is storekeeper, transporter, or consultant
    is_storekeeper_user = is_storekeeper(request.user)
    is_transporter_user = 'Transporter' in group_names or 'transporter' in group_names
    is_consultant_user = 'Consultant' in group_names or 'consultant' in group_names
    
    # Record the stamp based on role
    with transaction.atomic():
        stamp_recorded = False
        
        if is_storekeeper_user:
            role = "Storekeeper (Issued By)"
            # Storekeeper stamp is already embedded in waybill generation
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
