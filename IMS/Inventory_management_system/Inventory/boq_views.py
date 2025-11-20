"""
Views for Bill of Quantity management and bulk editing.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.db import transaction
import logging

from .models import BillOfQuantity
from .forms import BillOfQuantityFormSet
from .utils import is_superuser

logger = logging.getLogger(__name__)


class BulkEditBOQView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View for bulk editing Bill of Quantity items.
    Only accessible to superusers.
    """
    template_name = 'Inventory/boq_bulk_edit.html'
    
    def test_func(self):
        """Only superusers can bulk edit BOQ items"""
        return is_superuser(self.request.user)
    
    def get(self, request):
        """Display the bulk edit form"""
        # Get the selected BOQ IDs from the query parameters
        boq_ids = request.GET.getlist('boq_ids')
        
        if not boq_ids:
            messages.warning(request, 'No Bill of Quantity items selected for editing.')
            return redirect('bill_of_quantity')
        
        # Get the BOQ items
        queryset = BillOfQuantity.objects.filter(id__in=boq_ids).order_by('package_number', 'material_description')
        
        if not queryset.exists():
            messages.error(request, 'Selected Bill of Quantity items not found.')
            return redirect('bill_of_quantity')
        
        # Create the formset
        formset = BillOfQuantityFormSet(queryset=queryset)
        
        context = {
            'formset': formset,
            'boq_count': queryset.count(),
            'page_title': 'Bulk Edit Bill of Quantities'
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request):
        """Process the bulk edit form submission"""
        # Get the formset with POST data
        formset = BillOfQuantityFormSet(request.POST)
        
        if formset.is_valid():
            try:
                with transaction.atomic():
                    # Save all forms
                    instances = formset.save()
                    
                    messages.success(
                        request, 
                        f'Successfully updated {len(instances)} Bill of Quantity item(s).'
                    )
                    logger.info(
                        f"User {request.user.username} bulk edited {len(instances)} BOQ items"
                    )
                    
                return redirect('bill_of_quantity')
                
            except Exception as e:
                logger.error(f"Error during bulk BOQ edit: {str(e)}", exc_info=True)
                messages.error(
                    request, 
                    f'An error occurred while updating Bill of Quantity items: {str(e)}'
                )
        else:
            # If formset is invalid, show errors
            messages.error(
                request, 
                'Please correct the errors below.'
            )
            logger.warning(f"BOQ bulk edit form validation failed: {formset.errors}")
        
        # Re-render the form with errors
        context = {
            'formset': formset,
            'boq_count': len(formset.forms),
            'page_title': 'Bulk Edit Bill of Quantities'
        }
        
        return render(request, self.template_name, context)


class SingleEditBOQView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View for editing a single Bill of Quantity item.
    Only accessible to superusers.
    """
    template_name = 'Inventory/boq_single_edit.html'
    
    def test_func(self):
        """Only superusers can edit BOQ items"""
        return is_superuser(self.request.user)
    
    def get(self, request, pk):
        """Display the edit form for a single BOQ item"""
        boq_item = get_object_or_404(BillOfQuantity, pk=pk)
        
        # Create a formset with just one item
        queryset = BillOfQuantity.objects.filter(pk=pk)
        formset = BillOfQuantityFormSet(queryset=queryset)
        
        context = {
            'formset': formset,
            'boq_item': boq_item,
            'page_title': f'Edit BOQ: {boq_item.material_description}'
        }
        
        return render(request, self.template_name, context)
    
    def post(self, request, pk):
        """Process the edit form submission"""
        boq_item = get_object_or_404(BillOfQuantity, pk=pk)
        
        # Get the formset with POST data
        formset = BillOfQuantityFormSet(request.POST)
        
        if formset.is_valid():
            try:
                with transaction.atomic():
                    instances = formset.save()
                    
                    messages.success(
                        request, 
                        f'Successfully updated Bill of Quantity item: {boq_item.material_description}'
                    )
                    logger.info(
                        f"User {request.user.username} edited BOQ item {boq_item.id}: {boq_item.material_description}"
                    )
                    
                return redirect('bill_of_quantity')
                
            except Exception as e:
                logger.error(f"Error editing BOQ item {pk}: {str(e)}", exc_info=True)
                messages.error(
                    request, 
                    f'An error occurred while updating the Bill of Quantity item: {str(e)}'
                )
        else:
            messages.error(request, 'Please correct the errors below.')
            logger.warning(f"BOQ edit form validation failed for item {pk}: {formset.errors}")
        
        # Re-render the form with errors
        context = {
            'formset': formset,
            'boq_item': boq_item,
            'page_title': f'Edit BOQ: {boq_item.material_description}'
        }
        
        return render(request, self.template_name, context)


