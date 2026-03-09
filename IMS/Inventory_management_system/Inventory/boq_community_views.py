"""
Views for community-based Bill of Quantity bulk editing.
Provides Excel-like grid interface grouped by community.
"""
from django.shortcuts import render
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.db.models import Count, Q
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator

import json
import logging

from .models import BillOfQuantity
from .utils import is_superuser

logger = logging.getLogger(__name__)


class CommunityBOQBulkEditView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    View for community-based bulk editing of Bill of Quantity items.
    Groups BOQ items by community for easier management.
    Only accessible to superusers.
    """
    template_name = 'Inventory/boq_community_bulk_edit.html'
    permission_denied_message = "You must be a superuser to access the community bulk edit feature."
    raise_exception = True  # Return 403 instead of redirecting
    
    def test_func(self):
        """Only superusers can bulk edit BOQ items"""
        user = self.request.user
        is_super = is_superuser(user)
        logger.info(f"Community BOQ access attempt by {user.username}: is_superuser={is_super}")
        return is_super
    
    def get(self, request):
        """Display the community-based bulk edit interface"""
        logger.info(f"GET request to community bulk edit by {request.user.username}")
        
        # Get all unique communities with BOQ counts
        communities = (
            BillOfQuantity.objects
            .values('community')
            .annotate(count=Count('id'))
            .filter(community__isnull=False)
            .exclude(community='')
            .order_by('community')
        )
        
        # Get selected community from query params
        selected_community = request.GET.get('community', None)
        logger.info(f"Selected community: {selected_community}")
        
        # If a community is selected, get its BOQ items
        boq_items = []
        if selected_community:
            boq_items = BillOfQuantity.objects.filter(
                community=selected_community
            ).order_by('package_number', 'material_description')
            logger.info(f"Found {len(boq_items)} BOQ items for community {selected_community}")
        
        context = {
            'communities': communities,
            'selected_community': selected_community,
            'boq_items': boq_items,
            'page_title': 'Community-Based BOQ Bulk Edit'
        }
        
        return render(request, self.template_name, context)


class CommunityListAPIView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    API endpoint to get list of communities with BOQ counts.
    """
    def test_func(self):
        """Only superusers can access"""
        return is_superuser(self.request.user)
    
    def get(self, request):
        """Return communities as JSON"""
        communities = (
            BillOfQuantity.objects
            .values('community')
            .annotate(count=Count('id'))
            .filter(community__isnull=False)
            .exclude(community='')
            .order_by('community')
        )
        
        return JsonResponse({
            'communities': list(communities)
        })


class CommunityBOQDataAPIView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    API endpoint to get BOQ items for a specific community.
    """
    def test_func(self):
        """Only superusers can access"""
        return is_superuser(self.request.user)
    
    def get(self, request):
        """Return BOQ items for specified community as JSON"""
        community = request.GET.get('community', None)
        
        if not community:
            return JsonResponse({'error': 'Community parameter is required'}, status=400)
        
        boq_items = BillOfQuantity.objects.filter(
            community=community
        ).order_by('package_number', 'material_description')
        
        # Serialize BOQ items
        data = []
        for item in boq_items:
            data.append({
                'id': item.id,
                'package_number': item.package_number,
                'material_description': item.material_description,
                'item_code': item.item_code,
                'contract_quantity': float(item.contract_quantity),
                'quantity_received': float(item.quantity_received),
                'balance': float(item.balance),
                'region': item.region,
                'district': item.district,
                'community': item.community,
                'consultant': item.consultant,
                'contractor': item.contractor,
            })
        
        return JsonResponse({
            'community': community,
            'items': data
        })


class BulkUpdateBOQAPIView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    API endpoint to bulk update BOQ contract quantities.
    """
    def test_func(self):
        """Only superusers can update"""
        return is_superuser(self.request.user)
    
    def post(self, request):
        """Process bulk update of contract quantities"""
        try:
            # Parse JSON data
            data = json.loads(request.body)
            updates = data.get('updates', [])
            
            if not updates:
                return JsonResponse({'error': 'No updates provided'}, status=400)
            
            # Validate updates
            errors = []
            success_count = 0
            
            with transaction.atomic():
                for update in updates:
                    boq_id = update.get('id')
                    contract_quantity = update.get('contract_quantity')
                    
                    # Validation
                    if not boq_id:
                        errors.append({'error': 'Missing BOQ ID'})
                        continue
                    
                    if contract_quantity is None:
                        errors.append({'id': boq_id, 'error': 'Missing contract quantity'})
                        continue
                    
                    try:
                        contract_quantity = float(contract_quantity)
                        if contract_quantity < 0:
                            errors.append({'id': boq_id, 'error': 'Contract quantity cannot be negative'})
                            continue
                    except (ValueError, TypeError):
                        errors.append({'id': boq_id, 'error': 'Invalid contract quantity value'})
                        continue
                    
                    # Update BOQ item
                    try:
                        boq_item = BillOfQuantity.objects.get(id=boq_id)
                        boq_item.contract_quantity = contract_quantity
                        boq_item.save()
                        success_count += 1
                        
                        logger.info(
                            f"User {request.user.username} updated BOQ {boq_id}: "
                            f"contract_quantity = {contract_quantity}"
                        )
                    except BillOfQuantity.DoesNotExist:
                        errors.append({'id': boq_id, 'error': 'BOQ item not found'})
                        continue
            
            return JsonResponse({
                'success': True,
                'updated_count': success_count,
                'errors': errors
            })
            
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            logger.error(f"Error in bulk BOQ update: {str(e)}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)
