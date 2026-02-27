import json
import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import View
from django.http import JsonResponse
from django.urls import reverse

from Inventory.models import ReleaseLetter, MaterialOrder
from Inventory.forms import ReleaseLetterUploadForm

# Configure logger
logger = logging.getLogger(__name__)

class ReleaseLetterUploadView(LoginRequiredMixin, UserPassesTestMixin, View):
    """View for uploading signed release letters.
    
    Only accessible to schedule officers and superusers.
    """
    template_name = 'Inventory/upload_release_letter.html'
    login_url = 'login'
    permission_denied_message = "You don't have permission to upload release letters."
    
    def test_func(self):
        """Only allow schedule officers and superusers."""
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        return self.request.user.groups.filter(name='Schedule Officers').exists()
    
    def get(self, request):
        """Display the upload form with optional order summary."""
        form = ReleaseLetterUploadForm(user=request.user)
        request_code = request.GET.get('request_code')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == 'true'
        
        orders = []
        if request_code:
            try:
                # First, try to find orders with the exact request code
                orders = MaterialOrder.objects.filter(
                    request_code=request_code,
                    release_letter__isnull=True
                ).select_related('unit', 'requested_by')
                
                # If no exact match, try with base request code
                if not orders.exists() and '-' in request_code:
                    # Extract base request code (everything before the last dash)
                    base_code = '-'.join(request_code.split('-')[:-1])
                    if base_code:
                        orders = MaterialOrder.objects.filter(
                            request_code__startswith=base_code,
                            release_letter__isnull=True
                        ).select_related('unit', 'requested_by')
                
                # Debug output
                print(f"Found {orders.count()} orders for request code: {request_code}")
                for order in orders:
                    print(f"- {order.request_code}: {order.name} ({order.quantity} {order.unit})")
            except Exception as e:
                print(f"Error fetching orders: {str(e)}")
                if is_ajax:
                    return JsonResponse({'error': str(e)}, status=400)
        
        context = {
            'form': form,
            'orders': orders,
            'selected_request_code': request_code,
            'is_superuser': request.user.is_superuser,
            'is_schedule_officer': request.user.groups.filter(name='Schedule Officers').exists()
        }
        
        # Handle AJAX requests
        if is_ajax:
            if request_code:
                return render(request, 'Inventory/includes/order_summary.html', context)
            return JsonResponse({'error': 'No request code provided'}, status=400)
        
        # Regular GET request - render full page
        return render(request, self.template_name, context)
    
    def post(self, request):
        """Handle file upload."""
        form = ReleaseLetterUploadForm(request.POST, request.FILES, user=request.user)
        
        if form.is_valid():
            try:
                # Get the base request code and find all matching orders
                base_request_code = form.cleaned_data['request_code']
                # full_request_code = form.cleaned_data.get('full_request_code') or base_request_code # Unused variable
                
                # Find all orders that match the base request code
                matching_orders = MaterialOrder.objects.filter(
                    request_code__startswith=base_request_code,
                    release_letter__isnull=True  # Only include orders without release letters
                )
                
                if not matching_orders.exists():
                    # If no matching orders with the base code, try exact match
                    matching_orders = MaterialOrder.objects.filter(
                        request_code=base_request_code,
                        release_letter__isnull=True
                    )
                
                if not matching_orders.exists():
                    raise ValueError(f"No pending orders found for request code: {base_request_code}")
                
                # Create a release letter for these orders
                release_letter = form.save(commit=False)
                release_letter.uploaded_by = request.user
                release_letter.request_code = base_request_code
                release_letter.save()
                
                # Update all matching orders to point to this release letter
                matching_orders.update(release_letter=release_letter)
                
                messages.success(
                    request, 
                    f'Release letter for {matching_orders.count()} order(s) with request code {base_request_code} uploaded successfully!',
                    extra_tags='alert-success'
                )
                return redirect('material_orders')
                
            except Exception as e:
                logger.error(f"Error uploading release letter: {str(e)}", exc_info=True)
                messages.error(
                    request, 
                    f'Error uploading release letter: {str(e)}',
                    extra_tags='alert-danger'
                )
        
        # If form is invalid or there was an error, re-render the form with errors
        return render(request, self.template_name, {
            'form': form,
            'selected_request_code': request.POST.get('request_code'),
            'is_superuser': request.user.is_superuser,
            'is_schedule_officer': request.user.groups.filter(name='Schedule Officers').exists()
        })


class AdjustReleaseLetterQuantityView(LoginRequiredMixin, UserPassesTestMixin, View):
    """View for adjusting the total authorized quantity of a release letter."""
    
    def test_func(self):
        return self.request.user.is_superuser or self.request.user.groups.filter(name='Schedule Officers').exists()
        
    def post(self, request, pk):
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)
            
        release_letter = get_object_or_404(ReleaseLetter, pk=pk)
        try:
            data = json.loads(request.body)
            new_quantity = Decimal(str(data.get('total_quantity')))
            
            if new_quantity < 0:
                return JsonResponse({'success': False, 'error': 'Quantity cannot be negative'}, status=400)
                
            old_quantity = release_letter.total_quantity
            release_letter.total_quantity = new_quantity
            release_letter.save()
            
            # Log the change
            logger.info(f"User {request.user.username} adjusted RL {release_letter.reference_number} quantity from {old_quantity} to {new_quantity}")
            
            return JsonResponse({
                'success': True, 
                'new_quantity': float(new_quantity),
                'new_balance': float(release_letter.balance_to_request),
                'new_fulfillment': float(release_letter.fulfillment_percentage)
            })
        except (InvalidOperation, ValueError, TypeError) as e:
            return JsonResponse({'success': False, 'error': f'Invalid quantity format: {str(e)}'}, status=400)
        except Exception as e:
            logger.error(f"Error adjusting RL quantity: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
