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

from .models import MaterialOrder, ReleaseLetter, MaterialTransport, Transporter, TransportVehicle, MaterialOrderAudit
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
        # Get orders that have a release letter but no transport assignment yet
        queryset = MaterialOrder.objects.filter(
            release_letter__isnull=False,
            status__in=['Approved', 'In Progress', 'Ready for Pickup']
        ).exclude(
            transports__status__in=['In Transit', 'Delivered', 'Completed']
        ).select_related('release_letter', 'unit').prefetch_related('transports')
        
        # Apply search filters
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(code__icontains=search_query) |
                Q(request_code__icontains=search_query) |
                Q(release_letter__title__icontains=search_query) |
                Q(contractor__icontains=search_query) |
                Q(consultant__icontains=search_query)
            )
        
        # Apply status filter
        status_filter = self.request.GET.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Apply date filters
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if date_from:
            queryset = queryset.filter(date_requested__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date_requested__date__lte=date_to)
        
        return queryset.order_by('date_required', 'priority')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add search query to context for template
        context['search_query'] = self.request.GET.get('search', '')
        context['status_filter'] = self.request.GET.get('status', '')
        context['date_from'] = self.request.GET.get('date_from', '')
        context['date_to'] = self.request.GET.get('date_to', '')
        
        # Add forms to context
        context['transporter_form'] = TransporterForm()
        context['vehicle_form'] = TransportVehicleForm()
        context['assignment_form'] = TransportAssignmentForm()
        
        # Add summary statistics
        context['total_orders'] = self.get_queryset().count()
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle form submissions for creating/updating transport assignments."""
        if 'assign_transporter' in request.POST:
            order_id = request.POST.get('order_id')
            order = get_object_or_404(MaterialOrder, id=order_id)
            
            form = TransportAssignmentForm(request.POST)
            if form.is_valid():
                with transaction.atomic():
                    transport = form.save(commit=False)
                    transport.material_order = order
                    transport.status = 'Assigned'
                    transport.created_by = request.user
                    
                    # Set material details from the order
                    transport.material_name = order.name
                    transport.material_code = order.code
                    transport.quantity = order.quantity
                    transport.unit = order.unit.name if order.unit else ''
                    
                    # Set destination details from the order
                    transport.recipient = order.contractor or ''
                    transport.consultant = order.consultant or ''
                    transport.region = order.region or ''
                    transport.district = order.district or ''
                    transport.community = order.community or ''
                    transport.package_number = order.package_number or ''
                    
                    # Set the assignment date
                    transport.date_assigned = timezone.now()
                    
                    transport.save()
                    
                    # Update order status
                    order.status = 'In Progress'
                    order.save()
                    
                    # Create audit log entry
                    MaterialOrderAudit.objects.create(
                        order=order,
                        action=f'Transporter assigned: {transport.transporter.name} (Vehicle: {transport.vehicle.registration_number})',
                        performed_by=request.user
                    )
                    
                    messages.success(request, f'Transporter assigned successfully to order {order.request_code}.')
                    return redirect('transporter_assignment')
            else:
                error_messages = []
                for field, errors in form.errors.items():
                    field_label = form.fields[field].label
                    error_messages.append(f'{field_label}: {", ".join(errors)}')
                messages.error(request, 'Error assigning transporter. ' + ' '.join(error_messages))
        
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
        return reverse_lazy('transport_vehicle_list')
    
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
        return reverse_lazy('transport_vehicle_list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Vehicle updated successfully.')
        return super().form_valid(form)


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


class TransportVehicleDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """View for deleting a transport vehicle."""
    model = TransportVehicle
    template_name = 'Inventory/transport_vehicle_confirm_delete.html'
    
    def test_func(self):
        return is_superuser(self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('transport_vehicle_list')
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Vehicle deleted successfully.')
        return super().delete(request, *args, **kwargs)


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
