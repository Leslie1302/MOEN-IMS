from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.db.models import Q, Count, Sum, F
from django.utils import timezone
import pandas as pd
import json

from .models import (
    MaterialOrder, ReleaseLetter, MaterialTransport, Transporter, TransportVehicle, 
    MaterialOrderAudit, SiteReceipt
    # Note: Notification, Project, ProjectSite, ProjectPhase will be available after migration
)
from .forms import TransporterForm, TransportVehicleForm, TransportAssignmentForm, TransporterImportForm
from Inventory.utils import is_storekeeper, is_superuser

class ReleaseLetterListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    View for storekeepers and superusers to see all release letters with their associated orders.
    """
    model = ReleaseLetter
    template_name = 'Inventory/release_letter_list.html'
    context_object_name = 'release_letters'
    paginate_by = 20
    
    def test_func(self):
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
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


class TransporterAssignmentView(LoginRequiredMixin, UserPassesTestMixin, ListView):
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
        queryset = queryset.filter(
            status__in=['Approved', 'In Progress', 'Partially Fulfilled', 'Ready for Pickup', 'Fulfilled']
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
        
        # Exclude orders that have been fully transported
        # Allow partial transports to remain visible for additional assignments
        fully_transported_orders = []
        for order in queryset:
            # Calculate total transported quantity for this order
            total_transported = order.transports.aggregate(
                total=Sum('quantity')
            )['total'] or 0
            
            # If fully transported, exclude from assignment table
            if total_transported >= order.processed_quantity:
                fully_transported_orders.append(order.id)
                logger.info(f"Excluding fully transported order {order.request_code}: {total_transported}/{order.processed_quantity}")
        
        if fully_transported_orders:
            queryset = queryset.exclude(id__in=fully_transported_orders)
            logger.info(f"Excluded {len(fully_transported_orders)} fully transported orders")
        
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
    
    def post(self, request, *args, **kwargs):
        """Handle form submissions for creating/updating transport assignments."""
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
                    
                    # Create a new MaterialTransport record for this specific quantity
                    transport = MaterialTransport.objects.create(
                        material_order=order,
                        release_letter=release_letter,
                        transporter=transporter,
                        vehicle=vehicle,
                        driver_name=request.POST.get('driver_name', ''),
                        driver_phone=request.POST.get('driver_phone', ''),
                        waybill_number=request.POST.get('waybill_number', ''),
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
                        action=f'Transporter assigned: {transporter.name}',
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
    """Update the status of a transport assignment."""
    transport = get_object_or_404(MaterialTransport, pk=pk)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        
        if new_status in dict(MaterialTransport.STATUS_CHOICES):
            transport.status = new_status
            transport.save()
            
            # Update related order status if needed
            if new_status in ['In Transit', 'Delivered', 'Completed']:
                order = transport.material_order
                if new_status == 'In Transit':
                    order.status = 'In Transit'
                elif new_status == 'Delivered':
                    order.status = 'Delivered'
                elif new_status == 'Completed':
                    order.status = 'Completed'
                order.save()
            
            messages.success(request, f'Status updated to {transport.get_status_display()}')
            return JsonResponse({'success': True, 'status': transport.get_status_display()})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})


class TransporterListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
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


class TransporterCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
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


class TransporterUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
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


class TransportVehicleListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
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


class TransportVehicleCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """View for adding a new transport vehicle."""
    model = TransportVehicle
    form_class = TransportVehicleForm
    template_name = 'Inventory/transport_vehicle_form.html'
    
    def test_func(self):
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('vehicle_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Vehicle added successfully.')
        return super().form_valid(form)


class TransportVehicleUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
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


class TransporterDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
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


class TransportVehicleDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """View for displaying transport vehicle details."""
    model = TransportVehicle
    template_name = 'Inventory/transport_vehicle_detail.html'
    context_object_name = 'vehicle'
    
    def test_func(self):
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)


class TransporterLegendView(LoginRequiredMixin, UserPassesTestMixin, ListView):
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


class TransportationStatusView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    View for displaying transportation status - which transporter is handling which orders.
    Shows active transports with visual status indicators.
    """
    model = MaterialTransport
    template_name = 'Inventory/transportation_status.html'
    context_object_name = 'transports'
    paginate_by = 20
    
    def test_func(self):
        return is_storekeeper(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        # Get all active transports (not completed or cancelled)
        queryset = MaterialTransport.objects.filter(
            status__in=['Assigned', 'Loading', 'Loaded', 'In Transit', 'Delivered']
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
        
        # Add summary statistics
        all_transports = MaterialTransport.objects.filter(
            status__in=['Assigned', 'Loading', 'Loaded', 'In Transit', 'Delivered']
        )
        
        context['total_active'] = all_transports.count()
        context['in_transit_count'] = all_transports.filter(status='In Transit').count()
        context['loading_count'] = all_transports.filter(status__in=['Loading', 'Loaded']).count()
        context['assigned_count'] = all_transports.filter(status='Assigned').count()
        context['delivered_count'] = all_transports.filter(status='Delivered').count()
        
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
