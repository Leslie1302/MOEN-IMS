"""
Views for Supply Contract Management System
Handles suppliers, price catalogs, contracts, and invoices
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Q, Sum, Count, Avg
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db import transaction

from .models import (
    Supplier, SupplierPriceCatalog, SupplyContract, SupplyContractItem,
    SupplierInvoice, SupplierInvoiceItem, InventoryItem, Warehouse
)
from .forms import (
    SupplierForm, SupplierPriceCatalogForm, BulkPriceCatalogUploadForm,
    SupplyContractForm, SupplyContractItemFormSet,
    SupplierInvoiceForm, SupplierInvoiceItemFormSet,
    InvoiceVerificationForm, InvoiceApprovalForm
)
from .utils import is_management, is_superuser


# =============================================================================
# SUPPLIER MANAGEMENT VIEWS
# =============================================================================

class SupplierListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all suppliers with search and filtering"""
    model = Supplier
    template_name = 'Inventory/suppliers/supplier_list.html'
    context_object_name = 'suppliers'
    paginate_by = 20
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        queryset = Supplier.objects.all()
        
        # Search
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(code__icontains=search) |
                Q(contact_person__icontains=search) |
                Q(contact_email__icontains=search)
            )
        
        # Filter by active status
        is_active = self.request.GET.get('is_active')
        if is_active:
            queryset = queryset.filter(is_active=is_active == 'true')
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_suppliers'] = Supplier.objects.count()
        context['active_suppliers'] = Supplier.objects.filter(is_active=True).count()
        context['search_query'] = self.request.GET.get('search', '')
        return context


class SupplierDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Detailed view of a single supplier"""
    model = Supplier
    template_name = 'Inventory/suppliers/supplier_detail.html'
    context_object_name = 'supplier'
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        supplier = self.get_object()
        
        # Get supplier's price catalog
        context['price_catalog'] = supplier.price_catalog.filter(is_active=True)
        
        # Get supplier's contracts
        context['contracts'] = supplier.contracts.all()[:10]
        context['active_contracts'] = supplier.contracts.filter(status='active').count()
        
        # Get supplier's invoices
        context['invoices'] = supplier.invoices.all()[:10]
        context['pending_invoices'] = supplier.invoices.filter(status__in=['pending', 'verified']).count()
        
        return context


class SupplierCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create a new supplier"""
    model = Supplier
    form_class = SupplierForm
    template_name = 'Inventory/suppliers/supplier_form.html'
    success_url = reverse_lazy('supplier_list')
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def form_valid(self, form):
        messages.success(self.request, f'Supplier "{form.instance.name}" created successfully!')
        return super().form_valid(form)


class SupplierUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update an existing supplier"""
    model = Supplier
    form_class = SupplierForm
    template_name = 'Inventory/suppliers/supplier_form.html'
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_success_url(self):
        return reverse_lazy('supplier_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        messages.success(self.request, f'Supplier "{form.instance.name}" updated successfully!')
        return super().form_valid(form)


# =============================================================================
# PRICE CATALOG VIEWS
# =============================================================================

class PriceCatalogListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all supplier prices with filtering"""
    model = SupplierPriceCatalog
    template_name = 'Inventory/suppliers/price_catalog.html'
    context_object_name = 'prices'
    paginate_by = 30
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        queryset = SupplierPriceCatalog.objects.select_related('supplier', 'material', 'warehouse')
        
        # Filter by supplier
        supplier_id = self.request.GET.get('supplier')
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        
        # Filter by material
        material_id = self.request.GET.get('material')
        if material_id:
            queryset = queryset.filter(material_id=material_id)
        
        # Filter by active status
        is_active = self.request.GET.get('is_active')
        if is_active:
            queryset = queryset.filter(is_active=is_active == 'true')
        
        # Only show valid (not expired) prices by default
        show_expired = self.request.GET.get('show_expired')
        if not show_expired:
            queryset = queryset.filter(
                Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.now().date())
            )
        
        return queryset.order_by('-effective_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['suppliers'] = Supplier.objects.filter(is_active=True)
        context['materials'] = InventoryItem.objects.all()
        return context


class PriceCatalogCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Add a new supplier price"""
    model = SupplierPriceCatalog
    form_class = SupplierPriceCatalogForm
    template_name = 'Inventory/suppliers/price_form.html'
    success_url = reverse_lazy('price_catalog_list')
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, 'Price added successfully!')
        return super().form_valid(form)


# =============================================================================
# CONTRACT VIEWS
# =============================================================================

class ContractListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all supply contracts"""
    model = SupplyContract
    template_name = 'Inventory/contracts/contract_list.html'
    context_object_name = 'contracts'
    paginate_by = 20
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        queryset = SupplyContract.objects.select_related('supplier')
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by supplier
        supplier_id = self.request.GET.get('supplier')
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_contracts'] = SupplyContract.objects.count()
        context['active_contracts'] = SupplyContract.objects.filter(status='active').count()
        context['draft_contracts'] = SupplyContract.objects.filter(status='draft').count()
        context['suppliers'] = Supplier.objects.filter(is_active=True)
        return context


class ContractDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Detailed view of a supply contract"""
    model = SupplyContract
    template_name = 'Inventory/contracts/contract_detail.html'
    context_object_name = 'contract'
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        contract = self.get_object()
        
        # Get contract items
        context['items'] = contract.items.select_related('material', 'warehouse')
        
        # Get related invoices
        context['invoices'] = contract.invoices.all()
        
        # Calculate totals
        context['item_count'] = contract.items.count()
        context['total_value'] = contract.actual_value
        
        return context


class ContractCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create a new supply contract"""
    model = SupplyContract
    form_class = SupplyContractForm
    template_name = 'Inventory/contracts/contract_form.html'
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = SupplyContractItemFormSet(self.request.POST)
        else:
            context['formset'] = SupplyContractItemFormSet()
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        with transaction.atomic():
            form.instance.created_by = self.request.user
            self.object = form.save()
            
            if formset.is_valid():
                for item_form in formset:
                    if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE'):
                        item = item_form.save(commit=False)
                        item.contract = self.object
                        item.save()
                
                # Update contract estimated value
                self.object.total_estimated_value = self.object.actual_value
                self.object.save()
                
                messages.success(self.request, f'Contract "{self.object.contract_number}" created successfully!')
                return redirect('contract_detail', pk=self.object.pk)
            else:
                return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('contract_detail', kwargs={'pk': self.object.pk})


# =============================================================================
# INVOICE VIEWS
# =============================================================================

class InvoiceListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """List all supplier invoices"""
    model = SupplierInvoice
    template_name = 'Inventory/invoices/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_queryset(self):
        queryset = SupplierInvoice.objects.select_related('supplier', 'contract')
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by supplier
        supplier_id = self.request.GET.get('supplier')
        if supplier_id:
            queryset = queryset.filter(supplier_id=supplier_id)
        
        return queryset.order_by('-invoice_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_invoices'] = SupplierInvoice.objects.count()
        context['pending_invoices'] = SupplierInvoice.objects.filter(status='pending').count()
        context['overdue_invoices'] = SupplierInvoice.objects.filter(
            due_date__lt=timezone.now().date(),
            status__in=['pending', 'verified', 'approved']
        ).count()
        context['suppliers'] = Supplier.objects.filter(is_active=True)
        return context


class InvoiceDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Detailed view of a supplier invoice"""
    model = SupplierInvoice
    template_name = 'Inventory/invoices/invoice_detail.html'
    context_object_name = 'invoice'
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = self.get_object()
        
        # Get invoice items
        context['items'] = invoice.items.select_related('material', 'material_order', 'warehouse')
        
        # Calculate totals and discrepancies
        context['item_count'] = invoice.items.count()
        context['calculated_total'] = invoice.calculated_total
        context['has_discrepancies'] = any(item.has_discrepancy for item in invoice.items.all())
        
        # Add verification/approval forms if applicable
        if invoice.status == 'pending':
            context['verification_form'] = InvoiceVerificationForm()
        elif invoice.status == 'verified':
            context['approval_form'] = InvoiceApprovalForm()
        
        return context


class InvoiceCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create a new supplier invoice"""
    model = SupplierInvoice
    form_class = SupplierInvoiceForm
    template_name = 'Inventory/invoices/invoice_form.html'
    
    def test_func(self):
        return is_management(self.request.user) or is_superuser(self.request.user)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['formset'] = SupplierInvoiceItemFormSet(self.request.POST)
        else:
            context['formset'] = SupplierInvoiceItemFormSet()
        return context
    
    def form_valid(self, form):
        context = self.get_context_data()
        formset = context['formset']
        
        with transaction.atomic():
            form.instance.submitted_by = self.request.user
            self.object = form.save()
            
            if formset.is_valid():
                for item_form in formset:
                    if item_form.cleaned_data and not item_form.cleaned_data.get('DELETE'):
                        item = item_form.save(commit=False)
                        item.invoice = self.object
                        item.save()
                
                messages.success(self.request, f'Invoice "{self.object.invoice_number}" created successfully!')
                return redirect('invoice_detail', pk=self.object.pk)
            else:
                return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('invoice_detail', kwargs={'pk': self.object.pk})


@login_required
def verify_invoice(request, pk):
    """Verify an invoice (Storekeeper/Management)"""
    invoice = get_object_or_404(SupplierInvoice, pk=pk)
    
    if not (is_management(request.user) or is_superuser(request.user)):
        messages.error(request, 'You do not have permission to verify invoices.')
        return redirect('invoice_detail', pk=pk)
    
    if invoice.status != 'pending':
        messages.warning(request, 'This invoice cannot be verified at this stage.')
        return redirect('invoice_detail', pk=pk)
    
    if request.method == 'POST':
        form = InvoiceVerificationForm(request.POST)
        if form.is_valid():
            invoice.status = form.cleaned_data['status']
            invoice.verified_by = request.user
            invoice.verified_date = timezone.now()
            if form.cleaned_data['notes']:
                invoice.discrepancy_notes = form.cleaned_data['notes']
            invoice.save()
            
            messages.success(request, f'Invoice {invoice.invoice_number} has been {invoice.status}.')
            return redirect('invoice_detail', pk=pk)
    
    return redirect('invoice_detail', pk=pk)


@login_required
def approve_invoice(request, pk):
    """Approve an invoice for payment (Management only)"""
    invoice = get_object_or_404(SupplierInvoice, pk=pk)
    
    if not (is_management(request.user) or is_superuser(request.user)):
        messages.error(request, 'You do not have permission to approve invoices.')
        return redirect('invoice_detail', pk=pk)
    
    if invoice.status != 'verified':
        messages.warning(request, 'Invoice must be verified before approval.')
        return redirect('invoice_detail', pk=pk)
    
    if request.method == 'POST':
        form = InvoiceApprovalForm(request.POST)
        if form.is_valid():
            if form.cleaned_data['approved']:
                invoice.status = 'approved'
                invoice.approved_by = request.user
                invoice.approved_date = timezone.now()
                if form.cleaned_data['payment_reference']:
                    invoice.payment_reference = form.cleaned_data['payment_reference']
                invoice.save()
                
                messages.success(request, f'Invoice {invoice.invoice_number} approved for payment!')
            else:
                messages.info(request, 'Invoice approval cancelled.')
            
            return redirect('invoice_detail', pk=pk)
    
    return redirect('invoice_detail', pk=pk)


@login_required
def mark_invoice_paid(request, pk):
    """Mark an invoice as paid (Management only)"""
    invoice = get_object_or_404(SupplierInvoice, pk=pk)
    
    if not (is_management(request.user) or is_superuser(request.user)):
        messages.error(request, 'You do not have permission to mark invoices as paid.')
        return redirect('invoice_detail', pk=pk)
    
    if invoice.status != 'approved':
        messages.warning(request, 'Invoice must be approved before marking as paid.')
        return redirect('invoice_detail', pk=pk)
    
    invoice.status = 'paid'
    invoice.payment_date = timezone.now().date()
    invoice.save()
    
    messages.success(request, f'Invoice {invoice.invoice_number} marked as paid!')
    return redirect('invoice_detail', pk=pk)
