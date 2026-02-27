import logging
from django.shortcuts import redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, CreateView
from django.urls import reverse_lazy

from Inventory.models import MaterialTransport, SiteReceipt
from Inventory.forms import SiteReceiptForm
from .main_views import SuperuserOnlyMixin

# Configure logger
logger = logging.getLogger(__name__)

class ConsultantDeliveriesView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """
    View for consultants to see materials in transit to their project sites
    """
    model = MaterialTransport
    template_name = 'Inventory/consultant_deliveries.html'
    context_object_name = 'transports'
    paginate_by = 20
    
    def get_queryset(self):
        # Show transports that are in transit or delivered but not yet logged as received
        return MaterialTransport.objects.filter(
            status__in=['In Transit', 'Delivered']
        ).exclude(
            site_receipt__isnull=False  # Exclude those already logged
        ).select_related('material_order', 'transporter').order_by('-created_at')


class SiteReceiptCreateView(LoginRequiredMixin, SuperuserOnlyMixin, CreateView):
    """
    View for consultants to log site receipts
    """
    model = SiteReceipt
    form_class = SiteReceiptForm
    template_name = 'Inventory/site_receipt_form.html'
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        transport_id = self.kwargs.get('transport_id')
        if transport_id:
            try:
                transport = MaterialTransport.objects.get(id=transport_id)
                kwargs['transport'] = transport
            except MaterialTransport.DoesNotExist:
                pass
        return kwargs
    
    def form_valid(self, form):
        transport_id = self.kwargs.get('transport_id')
        try:
            transport = MaterialTransport.objects.get(id=transport_id)
            form.instance.material_transport = transport
            form.instance.received_by = self.request.user
            messages.success(self.request, 'Site receipt logged successfully!')
            return super().form_valid(form)
        except MaterialTransport.DoesNotExist:
            messages.error(self.request, 'Transport not found.')
            return redirect('consultant_deliveries')
    
    def get_success_url(self):
        return reverse_lazy('consultant_deliveries')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transport_id = self.kwargs.get('transport_id')
        if transport_id:
            try:
                context['transport'] = MaterialTransport.objects.get(id=transport_id)
            except MaterialTransport.DoesNotExist:
                pass
        return context


class SiteReceiptListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    View for consultants and schedule officers to see logged site receipts.
    Schedule officers can view receipts to monitor delivery status.
    """
    model = SiteReceipt
    template_name = 'Inventory/site_receipts.html'
    context_object_name = 'receipts'
    paginate_by = 20
    
    def test_func(self):
        # Using absolute import for utils to be safe
        from Inventory.utils import is_schedule_officer, is_superuser
        return is_schedule_officer(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        # Schedule officers and superusers see all receipts
        return SiteReceipt.objects.all().select_related(
            'material_transport', 'material_transport__material_order', 
            'material_transport__transporter', 'material_transport__vehicle',
            'received_by'
        ).order_by('-received_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # For each receipt, determine if its waybill can be downloaded
        # Waybill is downloadable only if ALL transports with the same waybill_number have site receipts
        for receipt in context['receipts']:
            transport = receipt.material_transport
            if transport.waybill_number and transport.consignment_number:
                # Bulk assignment - check if ALL transports with same waybill have receipts
                bulk_transports = MaterialTransport.objects.filter(
                    waybill_number=transport.waybill_number
                ).select_related('site_receipt')
                all_received = all(
                    hasattr(t, 'site_receipt') and t.site_receipt is not None
                    for t in bulk_transports
                )
                receipt.waybill_downloadable = all_received
                receipt.pending_receipts_count = sum(
                    1 for t in bulk_transports 
                    if not (hasattr(t, 'site_receipt') and t.site_receipt)
                )
            else:
                # Single assignment - waybill is downloadable since this receipt exists
                receipt.waybill_downloadable = True
                receipt.pending_receipts_count = 0
        
        return context
