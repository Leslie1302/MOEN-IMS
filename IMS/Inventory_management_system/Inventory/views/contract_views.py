"""
Views for supply contract management and fulfillment tracking.
"""

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView
from django.db.models import Sum, F, Case, When, DecimalField, Q
from decimal import Decimal

from Inventory.models.suppliers import SupplyContract, SupplierInvoice
from Inventory.models import MaterialOrder


class ContractFulfillmentListView(LoginRequiredMixin, ListView):
    """List all contracts with fulfillment progress"""
    model = SupplyContract
    template_name = 'Inventory/contracts/contract_fulfillment_list.html'
    context_object_name = 'contracts'
    paginate_by = 20

    def get_queryset(self):
        """Get contracts with calculated fulfillment progress"""
        return SupplyContract.objects.select_related('supplier').filter(
            status__in=['active', 'completed']
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Add fulfillment data for each contract
        for contract in context['contracts']:
            # Calculate total quantity contracted across all items
            total_contracted = contract.items.aggregate(
                total=Sum('quantity')
            )['total'] or Decimal('0')

            # Calculate total quantity received for this contract
            total_received = MaterialOrder.objects.filter(
                supply_contract=contract,
                request_type='Receipt',
                status='Completed'
            ).aggregate(
                total=Sum('quantity')
            )['total'] or Decimal('0')

            # Calculate remaining balance
            remaining = total_contracted - total_received

            # Calculate fulfillment percentage
            if total_contracted > 0:
                fulfillment_percent = int((total_received / total_contracted) * 100)
            else:
                fulfillment_percent = 0

            # Add to contract object
            contract.total_contracted = total_contracted
            contract.total_received = total_received
            contract.remaining = remaining
            contract.fulfillment_percent = fulfillment_percent
            contract.is_complete = remaining <= 0

        return context


class ContractDetailView(LoginRequiredMixin, DetailView):
    """Detailed view of a single contract with fulfillment breakdown"""
    model = SupplyContract
    template_name = 'Inventory/contracts/contract_detail.html'
    context_object_name = 'contract'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contract = self.get_object()

        # Get all items in this contract
        context['items'] = contract.items.select_related('material')

        # For each item, calculate fulfillment
        for item in context['items']:
            received = MaterialOrder.objects.filter(
                supply_contract=contract,
                name=item.material,
                request_type='Receipt',
                status='Completed'
            ).aggregate(
                total=Sum('quantity')
            )['total'] or Decimal('0')

            item.received = received
            item.remaining = item.quantity - received
            item.percent = int((received / item.quantity) * 100) if item.quantity > 0 else 0

        # Get receipts for this contract
        context['receipts'] = MaterialOrder.objects.filter(
            supply_contract=contract,
            request_type='Receipt'
        ).order_by('-date_requested')

        # Get invoices for this contract
        context['invoices'] = SupplierInvoice.objects.filter(
            contract=contract
        ).order_by('-invoice_date')

        return context
