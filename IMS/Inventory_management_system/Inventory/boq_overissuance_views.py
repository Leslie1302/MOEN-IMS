"""
Views for managing Bill of Quantity overissuances
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView
from django.contrib import messages
from django.db.models import Q, Sum, Count, F
from django.urls import reverse_lazy, reverse
from django.http import JsonResponse
from django.utils import timezone
from collections import defaultdict

from .models import BillOfQuantity, BoQOverissuanceJustification
from .forms import BoQOverissuanceJustificationForm


class BoQOverissuanceSummaryView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Display a summary of all projects with BoQ overissuances (negative balances)
    """
    model = BillOfQuantity
    template_name = 'Inventory/boq_overissuance_summary.html'
    context_object_name = 'overissuance_data'
    permission_required = 'Inventory.can_view_overissuance_summary'
    
    def get_queryset(self):
        """Get all BoQ items with overissuances"""
        # Get all BoQ items where quantity_received > contract_quantity
        return BillOfQuantity.objects.filter(
            quantity_received__gt=F('contract_quantity')
        ).select_related('warehouse', 'user', 'group').order_by('package_number', 'material_description')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Group overissuances by package number (project)
        overissuances = self.get_queryset()
        projects_data = defaultdict(lambda: {
            'package_number': '',
            'contractor': '',
            'consultant': '',
            'region': '',
            'district': '',
            'items': [],
            'total_overissuance_items': 0,
            'total_overissuance_value': 0,
            'has_justifications': False,
            'pending_justifications': 0,
            'approved_justifications': 0,
        })
        
        for item in overissuances:
            pkg = item.package_number
            overissuance_amt = item.quantity_received - item.contract_quantity
            
            # Get justifications for this item
            justifications = item.overissuance_justifications.all()
            has_justification = justifications.exists()
            pending_count = justifications.filter(status='Pending').count()
            approved_count = justifications.filter(status='Approved').count()
            
            projects_data[pkg]['package_number'] = pkg
            projects_data[pkg]['contractor'] = item.contractor
            projects_data[pkg]['consultant'] = item.consultant
            projects_data[pkg]['region'] = item.region
            projects_data[pkg]['district'] = item.district
            projects_data[pkg]['items'].append({
                'id': item.id,
                'material_description': item.material_description,
                'item_code': item.item_code,
                'contract_quantity': item.contract_quantity,
                'quantity_received': item.quantity_received,
                'overissuance_amount': overissuance_amt,
                'balance': item.balance,
                'has_justification': has_justification,
                'justifications': justifications,
            })
            projects_data[pkg]['total_overissuance_items'] += 1
            projects_data[pkg]['total_overissuance_value'] += overissuance_amt
            
            if has_justification:
                projects_data[pkg]['has_justifications'] = True
            projects_data[pkg]['pending_justifications'] += pending_count
            projects_data[pkg]['approved_justifications'] += approved_count
        
        # Convert to list for template
        context['projects_with_overissuance'] = list(projects_data.values())
        context['total_projects_affected'] = len(projects_data)
        context['total_overissuance_items'] = sum(p['total_overissuance_items'] for p in projects_data.values())
        
        return context


class BoQOverissuanceJustificationCreateView(LoginRequiredMixin, CreateView):
    """
    Allow authorized users to submit justification for a BoQ overissuance
    """
    model = BoQOverissuanceJustification
    form_class = BoQOverissuanceJustificationForm
    template_name = 'Inventory/boq_overissuance_justification_form.html'
    success_url = reverse_lazy('boq_overissuance_summary')
    
    def dispatch(self, request, *args, **kwargs):
        """Ensure the BoQ item exists and has overissuance"""
        self.boq_item = get_object_or_404(BillOfQuantity, id=self.kwargs['boq_id'])
        
        if not self.boq_item.has_overissuance:
            messages.error(request, "This BoQ item does not have an overissuance.")
            return redirect('boq_overissuance_summary')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        """Pass the BoQ item to the form"""
        kwargs = super().get_form_kwargs()
        kwargs['boq_item'] = self.boq_item
        return kwargs
    
    def form_valid(self, form):
        """Save the justification with proper fields"""
        justification = form.save(commit=False)
        justification.boq_item = self.boq_item
        justification.package_number = self.boq_item.package_number
        justification.project_name = f"{self.boq_item.contractor} - {self.boq_item.package_number}"
        justification.overissuance_quantity = self.boq_item.overissuance_amount
        justification.submitted_by = self.request.user
        justification.save()
        
        messages.success(
            self.request, 
            f"Justification submitted successfully for {self.boq_item.material_description}."
        )
        return super().form_valid(form)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['boq_item'] = self.boq_item
        context['overissuance_amount'] = self.boq_item.overissuance_amount
        return context


class BoQOverissuanceJustificationListView(LoginRequiredMixin, ListView):
    """
    List all overissuance justifications
    """
    model = BoQOverissuanceJustification
    template_name = 'Inventory/boq_overissuance_justification_list.html'
    context_object_name = 'justifications'
    paginate_by = 20
    
    def get_queryset(self):
        """Get justifications based on user permissions"""
        queryset = BoQOverissuanceJustification.objects.select_related(
            'boq_item', 'submitted_by', 'reviewed_by'
        )
        
        # Filter by status if provided
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by package if provided
        package = self.request.GET.get('package')
        if package:
            queryset = queryset.filter(package_number__icontains=package)
        
        return queryset.order_by('-submitted_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = BoQOverissuanceJustification.JUSTIFICATION_STATUS_CHOICES
        context['selected_status'] = self.request.GET.get('status', '')
        context['selected_package'] = self.request.GET.get('package', '')
        return context


class BoQOverissuanceJustificationDetailView(LoginRequiredMixin, DetailView):
    """
    View details of a specific overissuance justification
    """
    model = BoQOverissuanceJustification
    template_name = 'Inventory/boq_overissuance_justification_detail.html'
    context_object_name = 'justification'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_review'] = self.request.user.has_perm('Inventory.can_review_overissuance')
        return context


@login_required
@permission_required('Inventory.can_review_overissuance', raise_exception=True)
def review_overissuance_justification(request, pk):
    """
    Review and approve/reject an overissuance justification
    """
    justification = get_object_or_404(BoQOverissuanceJustification, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        review_comments = request.POST.get('review_comments', '')
        
        if action in ['Approved', 'Rejected', 'Under Review']:
            justification.status = action
            justification.review_comments = review_comments
            justification.reviewed_by = request.user
            justification.reviewed_at = timezone.now()
            justification.save()
            
            messages.success(request, f"Justification {action.lower()} successfully.")
        else:
            messages.error(request, "Invalid action.")
    
    return redirect('boq_overissuance_justification_detail', pk=pk)


@login_required
def boq_overissuance_stats(request):
    """
    AJAX endpoint to get overissuance statistics
    """
    # Count total overissuance items
    overissuance_items = BillOfQuantity.objects.filter(
        quantity_received__gt=F('contract_quantity')
    )
    
    total_items = overissuance_items.count()
    
    # Count projects affected (unique package numbers)
    projects_affected = overissuance_items.values('package_number').distinct().count()
    
    # Count justifications by status
    pending_justifications = BoQOverissuanceJustification.objects.filter(status='Pending').count()
    approved_justifications = BoQOverissuanceJustification.objects.filter(status='Approved').count()
    rejected_justifications = BoQOverissuanceJustification.objects.filter(status='Rejected').count()
    
    data = {
        'total_overissuance_items': total_items,
        'projects_affected': projects_affected,
        'pending_justifications': pending_justifications,
        'approved_justifications': approved_justifications,
        'rejected_justifications': rejected_justifications,
    }
    
    return JsonResponse(data)
