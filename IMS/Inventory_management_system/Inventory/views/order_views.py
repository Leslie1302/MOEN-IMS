import json
import logging
import uuid
from decimal import Decimal, InvalidOperation

import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Count, Sum, F
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.decorators import login_required
from django.views.generic import View, ListView
from django.http import JsonResponse, Http404
from django.forms import formset_factory
from django.utils import timezone
from django.template.loader import render_to_string
from django.core.exceptions import ValidationError

from Inventory.models import (
    InventoryItem, MaterialOrder, MaterialOrderAudit, 
    ReleaseLetter, Warehouse, MaterialTransport, SiteReceipt
)
from Inventory.forms import (
    MaterialOrderForm, BulkMaterialRequestForm, MaterialReceiptFormSet
)

# Define MaterialOrderFormSet locally if not imported
MaterialOrderFormSet = formset_factory(MaterialOrderForm, extra=1)

# Configure logger
logger = logging.getLogger(__name__)


def generate_request_code():
    """Generate a unique request code in the format REQ-YYYYMMDD-XXXXXX"""
    date_str = timezone.now().strftime('%Y%m%d')
    unique_id = str(uuid.uuid4().int)[:6].upper()
    return f"REQ-{date_str}-{unique_id}"


class RequestMaterialView(LoginRequiredMixin, View):
    template_name = 'Inventory/request_material.html'

    def get(self, request):
        # Filter items based on user permissions
        if request.user.is_superuser:
            items = InventoryItem.objects.all()
        else:
            items = InventoryItem.objects.filter(group__in=request.user.groups.all())

        formset = MaterialOrderFormSet(form_kwargs={'user': request.user})
        bulk_form = BulkMaterialRequestForm()
        inventory_items = list(items.values('id', 'name', 'category__name', 'unit__name', 'code', 'warehouse__name'))

        # Non-superusers default to bulk tab, superusers default to single tab
        default_tab = 'single' if request.user.is_superuser else 'bulk'

        return render(request, self.template_name, {
            'formset': formset,
            'bulk_form': bulk_form,
            'items': items,
            'inventory_items': json.dumps(inventory_items),
            'active_tab': default_tab
        })

    def post(self, request):
        # Check which form was submitted
        if 'bulk_submit' in request.POST:
            return self.handle_bulk_request(request)
        else:
            return self.handle_single_request(request)

    def handle_single_request(self, request):
        formset = MaterialOrderFormSet(request.POST, request.FILES, form_kwargs={'user': request.user})
        if formset.is_valid():
            request_code = generate_request_code()
            with transaction.atomic():
                for form in formset:
                    if form.cleaned_data:
                        material_order = form.save(commit=False)
                        selected_item = form.cleaned_data['name']  # This is an InventoryItem object
                        selected_warehouse = form.cleaned_data.get('warehouse')
                        
                        # Look up the specific inventory item by name and warehouse
                        if selected_item and selected_warehouse:
                            try:
                                inventory_item = InventoryItem.objects.get(
                                    name=selected_item.name,
                                    warehouse=selected_warehouse
                                )
                                material_order.name = inventory_item.name
                                material_order.category = inventory_item.category
                                material_order.code = inventory_item.code
                                material_order.unit = inventory_item.unit
                            except InventoryItem.DoesNotExist:
                                # Fallback to selected item if specific warehouse combo doesn't exist
                                material_order.name = selected_item.name
                                material_order.category = selected_item.category
                                material_order.code = selected_item.code
                                material_order.unit = selected_item.unit
                        elif selected_item:
                            material_order.name = selected_item.name
                            material_order.category = selected_item.category
                            material_order.code = selected_item.code
                            material_order.unit = selected_item.unit
                        
                        material_order.user = request.user
                        material_order.group = request.user.groups.first() if request.user.groups.exists() else None
                        material_order.request_type = 'Release'
                        material_order.request_code = request_code
                        # Ensure newly created requests start as Draft
                        material_order.status = 'Draft'
                        # Initialize quantities so remaining is not zero
                        material_order.processed_quantity = 0
                        material_order.remaining_quantity = material_order.quantity
                        
                        # Set current user for release letter creation
                        material_order._current_user = request.user
                        
                        # Save the material order first to get the ID and proper request_code
                        material_order.save()
                        
                        # Now handle release letter creation if file was uploaded
                        if form.cleaned_data.get('release_letter_pdf'):
                            title = form.cleaned_data.get('release_letter_title') or f"Release Letter for {material_order.name}"
                            auth_qty = form.cleaned_data.get('release_letter_quantity') or material_order.quantity
                            material_type = form.cleaned_data.get('release_letter_material_type') or 'Other'
                            phase = form.cleaned_data.get('release_letter_project_phase')
                            
                            release_letter = ReleaseLetter.objects.create(
                                request_code=material_order.request_code,
                                title=title,
                                total_quantity=auth_qty,
                                material_type=material_type,
                                project_phase=phase,
                                pdf_file=form.cleaned_data['release_letter_pdf'],
                                upload_time=timezone.now(),
                                uploaded_by=request.user,
                                notes=f"Uploaded with material request {material_order.request_code}"
                            )
                            
                            # Link the release letter to the material order
                            material_order.release_letter = release_letter
                            material_order.save()
                            
            messages.success(request, "Material requests submitted successfully!")
            return redirect('material_orders')
        else:
            print("Formset errors:", formset.errors)
            messages.error(request, "There was an error with your submission.")

        # Prepare context for re-rendering the form with errors
        # Show all inventory items to all users for transparency
        items = InventoryItem.objects.all()

        return render(request, self.template_name, {
            'formset': formset,
            'bulk_form': BulkMaterialRequestForm(),
            'items': items,
            'inventory_items': json.dumps(list(items.values('id', 'name', 'category__name', 'unit__name', 'code', 'warehouse__name'))),
            'active_tab': 'single'
        })

    def handle_bulk_request(self, request):
        logger = logging.getLogger(__name__)
        logger.info("Starting bulk request processing...")
        
        bulk_form = BulkMaterialRequestForm(request.POST, request.FILES)
        if not bulk_form.is_valid():
            logger.error(f"Bulk form validation failed: {bulk_form.errors}")
            for field, errors in bulk_form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            return self._render_request_form(request, bulk_form=bulk_form)
        
        # Initialize variables outside the transaction
        success_count = 0
        error_messages = []
        
        try:
            df = bulk_form.cleaned_data['df']
            request_type = bulk_form.cleaned_data['request_type']
            priority = bulk_form.cleaned_data['priority']  # Get priority from form
            release_letter_pdf = bulk_form.cleaned_data.get('release_letter_pdf')
            release_letter_title = bulk_form.cleaned_data.get('release_letter_title')
            
            # Inform user if rows were filtered out
            filtered_count = bulk_form.cleaned_data.get('filtered_rows', 0)
            if filtered_count > 0:
                messages.info(request, f"Note: {filtered_count} row(s) with zero or negative quantities were automatically skipped.")
            
            logger.info(f"Processing bulk request with {len(df)} rows")
            
            # Generate a base request code for reference
            base_request_code = generate_request_code()
            logger.info(f"Base request code for this batch: {base_request_code}")
            
            # Add a request code column to the DataFrame
            df['request_code'] = [f"{base_request_code}-{i+1}" for i in range(len(df))]
            
            # Create release letter if PDF is uploaded
            release_letter = None
            if release_letter_pdf:
                try:
                    total_batch_quantity = bulk_form.cleaned_data.get('release_letter_quantity') or df['quantity'].sum()
                    material_type = bulk_form.cleaned_data.get('release_letter_material_type') or 'Other'
                    phase = bulk_form.cleaned_data.get('release_letter_project_phase')
                    
                    release_letter = ReleaseLetter.objects.create(
                        title=release_letter_title or f"Release Letter - {base_request_code}",
                        total_quantity=Decimal(str(total_batch_quantity)),
                        material_type=material_type,
                        project_phase=phase,
                        pdf_file=release_letter_pdf,
                        uploaded_by=request.user,
                        request_code=base_request_code
                    )
                    logger.info(f"Created release letter ID {release_letter.id} for request code {base_request_code}")
                except Exception as e:
                    error_msg = f"Error creating release letter: {str(e)}"
                    messages.error(request, error_msg)
                    logger.error(error_msg, exc_info=True)
                    return self._render_request_form(request, bulk_form=bulk_form)
            
            # Process each row in the Excel file
            logger.info(f"Starting to process {len(df)} rows from Excel")
            
            for idx, row in df.iterrows():
                row_dict = row.to_dict()
                
                try:
                    # Skip empty rows
                    if not row.get('name'):
                        continue
                        
                    # Find the inventory item
                    item_name = str(row['name']).strip()
                    item = self._find_inventory_item(item_name, request.user)
                    
                    if not item:
                        error_msg = f"Item not found or not accessible: {item_name}"
                        error_messages.append(error_msg)
                        continue
                        
                    # Handle group assignment
                    group = self._get_order_group(request.user, item, item_name)
                    
                    # Handle warehouse lookup
                    warehouse = None
                    warehouse_name = row.get('warehouse')
                    if warehouse_name and pd.notna(warehouse_name):
                        warehouse_name_str = str(warehouse_name).strip()
                        try:
                            warehouse = Warehouse.objects.filter(name__iexact=warehouse_name_str).first()
                        except Exception as wh_error:
                            logger.error(f"Error looking up warehouse: {str(wh_error)}")
                    
                    # Create the order in a new transaction for each item
                    try:
                        with transaction.atomic():
                            order_data = {
                                'name': item.name,
                                'quantity': row['quantity'],
                                'category': item.category,
                                'code': item.code,
                                'unit': item.unit,
                                'user': request.user,
                                'group': group,
                                'warehouse': warehouse,
                                'request_type': request_type,
                                'request_code': row['request_code'],  # Use the unique request code from the DataFrame
                                'priority': priority,  # Use priority from form (applies to all items)
                                'region': row.get('region', ''),
                                'district': row.get('district', ''),
                                'community': row.get('community', ''),
                                'consultant': row.get('consultant', ''),
                                'contractor': row.get('contractor', ''),
                                'package_number': row.get('package_number', ''),
                                'last_updated_by': request.user,
                                # Ensure bulk-created requests start as Draft
                                'status': 'Draft',
                                # Initialize quantities so remaining is not zero
                                'processed_quantity': 0,
                                'remaining_quantity': row['quantity']
                            }
                            
                            # Create the order
                            order = MaterialOrder.objects.create(**order_data)
                            
                            # Associate with release letter if available
                            if release_letter:
                                order.release_letter = release_letter
                                order.save(update_fields=['release_letter'])
                            
                            success_count += 1
                            
                    except Exception as e:
                        error_msg = f"❌ ERROR saving order for {item_name}: {str(e)}"
                        error_messages.append(error_msg)
                        logger.error(error_msg, exc_info=True)
                        continue
                        
                except Exception as e:
                    error_msg = f"❌ ERROR processing row for {row.get('name', 'unknown')}: {str(e)}"
                    error_messages.append(error_msg)
                    logger.error(error_msg, exc_info=True)
                    continue
            
            # Show success/error messages
            if success_count > 0:
                msg = f"Successfully created {success_count} material request(s) with unique request codes starting with {base_request_code}"
                messages.success(request, msg)
                
                # Add an info message about how to track related requests
                if success_count > 1:
                    messages.info(request, 
                        "Each item in the bulk upload has been assigned a unique request code. "
                        "You can find related requests by searching for the base code."
                    )
                
                # Only redirect if we had any successful saves
                return redirect('material_orders')
                
            # If we got here, there were no successful saves
            if error_messages:
                for error in error_messages[:5]:  # Show first 5 errors to avoid flooding
                    messages.error(request, error)
                if len(error_messages) > 5:
                    messages.warning(request, f"... and {len(error_messages) - 5} more errors occurred.")
                    
            return self._render_request_form(request, bulk_form=bulk_form)
                    
        except Exception as e:
            error_msg = f"Unexpected error processing bulk request: {str(e)}"
            messages.error(request, error_msg)
            logger.error(error_msg, exc_info=True)
            return self._render_request_form(request, bulk_form=bulk_form)
            
        return self._render_request_form(request, bulk_form=bulk_form)
        
    def _find_inventory_item(self, item_name, user):
        """Helper method to find an inventory item by name with proper permissions"""
        logger = logging.getLogger(__name__)
        try:
            # First try exact match
            if user.is_superuser:
                item = InventoryItem.objects.filter(name__iexact=item_name).first()
            else:
                item = InventoryItem.objects.filter(
                    name__iexact=item_name,
                    group__in=user.groups.all()
                ).first()
                
            if item:
                return item
                
            # If no exact match, try case-insensitive contains
            if user.is_superuser:
                item = InventoryItem.objects.filter(name__icontains=item_name).first()
            else:
                item = InventoryItem.objects.filter(
                    name__icontains=item_name,
                    group__in=user.groups.all()
                ).first()
                
            if item:
                return item
                
            return None
            
        except Exception as e:
            logger.error(f"Error finding inventory item {item_name}: {str(e)}", exc_info=True)
            return None

    def _get_order_group(self, user, item, item_name):
        """Helper method to determine the appropriate group for an order"""
        # First try to get the group from the item
        if item.group:
            return item.group
            
        # If item has no group, try to find a matching group from the user's groups
        # that has the same name as the item's category
        if item.category and user.groups.exists():
            matching_group = user.groups.filter(name__iexact=item.category.name).first()
            if matching_group:
                return matching_group
                
        # Default to the user's first group if available
        if user.groups.exists():
            return user.groups.first()
            
        return None

    def _render_request_form(self, request, bulk_form=None):
        """Helper method to render the request form with the current context"""
        if request.user.is_superuser:
            items = InventoryItem.objects.all()
        else:
            items = InventoryItem.objects.filter(group__in=request.user.groups.all())
            
        context = {
            'formset': MaterialOrderFormSet(form_kwargs={'user': request.user}),
            'bulk_form': bulk_form or BulkMaterialRequestForm(),
            'items': items,
            'inventory_items': json.dumps(list(items.values('id', 'name', 'category__name', 'unit__name', 'code', 'warehouse__name'))),
            'active_tab': 'bulk' if bulk_form else 'single'
        }
        return render(request, self.template_name, context)


class MaterialOrdersView(LoginRequiredMixin, ListView):
    """
    View for displaying material orders with proper fulfillment workflow.
    - All authenticated users can see all orders for transparency and collaboration
    """
    template_name = 'Inventory/material_orders.html'
    context_object_name = 'orders'
    paginate_by = 50
    paginate_orphans = 5  # Include last page items if fewer than 5
    allow_empty = True  # Allow empty querysets

    def get_queryset(self):
        try:
            # Base queryset with proper ordering and select_related for performance
            # Show all orders to all authenticated users for transparency
            queryset = MaterialOrder.objects.select_related('user', 'unit', 'category', 'warehouse').order_by('-date_requested')
            return queryset
        except Exception as e:
            logger.error(f"Error in MaterialOrdersView: {str(e)}", exc_info=True)
            # Fallback to empty queryset to prevent crashes
            return MaterialOrder.objects.none()

    def paginate_queryset(self, queryset, page_size):
        """Override to handle invalid page numbers gracefully"""
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        
        paginator = Paginator(queryset, page_size, orphans=self.paginate_orphans)
        page_number = self.request.GET.get('page', 1)
        
        try:
            page = paginator.page(page_number)
        except PageNotAnInteger:
            # If page is not an integer, deliver first page
            page = paginator.page(1)
        except EmptyPage:
            # If page is out of range, deliver last page
            page = paginator.page(paginator.num_pages)
        
        return (paginator, page, page.object_list, page.has_other_pages())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Use aggregation for statistics
        stats = MaterialOrder.objects.aggregate(
            total_orders=Count('id'),
            pending_orders=Count('id', filter=Q(status='Pending')),
            completed_orders=Count('id', filter=Q(status='Completed')),
            partial_orders=Count('id', filter=Q(status='Partially Fulfilled'))
        )
        
        context.update(stats)
        return context


class MaterialOrdersOfficersView(LoginRequiredMixin, ListView):
    """
    View for displaying material orders with proper fulfillment workflow.
    - All authenticated users can see all orders for transparency and collaboration
    """
    template_name = 'Inventory/material_orders_officers.html'
    context_object_name = 'orders'
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        logger = logging.getLogger(__name__)
        
        try:
            # Base queryset: Show orders that have been assigned OR are in processing/completed states
            # This handles both new workflow (assigned) and legacy orders (no assignment)
            # Exclude only Draft and Pending (awaiting assignment)
            queryset = MaterialOrder.objects.select_related(
                'user', 'unit', 'category', 'assigned_to', 'assigned_by'
            ).exclude(
                status__in=['Draft', 'Pending']
            ).order_by('-date_requested')
            
            logger.info(f"User {user.username} accessing {queryset.count()} total orders")
            
            # Ensure remaining_quantity is calculated correctly
            for order in queryset:
                if order.remaining_quantity is None or order.remaining_quantity < 0:
                    order.remaining_quantity = max(0, order.quantity - (order.processed_quantity or 0))
                    order.save(update_fields=['remaining_quantity'])
            
            return queryset
            
        except Exception as e:
            logger.error(f"Error in MaterialOrdersOfficersView for user {user.username}: {str(e)}", exc_info=True)
            # Fallback to empty queryset to prevent crashes
            return MaterialOrder.objects.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the full queryset for statistics (not paginated)
        full_queryset = self.get_queryset()
        
        # Add summary statistics using the full queryset
        if full_queryset.exists():
            context.update({
                'total_orders': full_queryset.count(),
                'pending_orders': full_queryset.filter(status='Pending').count(),
                'completed_orders': full_queryset.filter(status='Completed').count(),
                'partial_orders': full_queryset.filter(status='Partially Fulfilled').count(),
            })
        else:
            context.update({
                'total_orders': 0,
                'pending_orders': 0,
                'completed_orders': 0,
                'partial_orders': 0,
            })
        
        return context


class UpdateMaterialStatusView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Handle material order status updates and fulfillment processing.
    Supports: Seen, Approved, Rejected, Partial, Full status updates.
    """

    def test_func(self):
        """Ensure only staff/superusers or explicitly assigned users can update status."""
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return True
        return user.groups.exists() 
    
    def post(self, request, order_id, new_status):
        logger = logging.getLogger(__name__)
        
        # Validate status
        allowed_statuses = ["Seen", "Approved", "Rejected", "Partially Fulfilled", "Full"]
        if new_status not in allowed_statuses:
            return JsonResponse({
                "success": False, 
                "error": f"Invalid status '{new_status}'. Allowed: {', '.join(allowed_statuses)}"
            }, status=400)

        try:
            with transaction.atomic():
                order = get_object_or_404(MaterialOrder, id=order_id)
                
                # Parse request data
                try:
                    data = json.loads(request.body.decode('utf-8'))
                except json.JSONDecodeError as e:
                    return JsonResponse({
                        "success": False, 
                        "error": "Invalid JSON in request body"
                    }, status=400)

                # Handle simple status changes
                if new_status in ["Seen", "Approved", "Rejected"]:
                    order.status = new_status
                
                # Handle quantity processing (Partial/Full)
                elif new_status in ["Partially Fulfilled", "Full"]:
                    
                    # SECURITY: Check if order is assigned to current user
                    if order.assigned_to and order.assigned_to != request.user:
                        return JsonResponse({
                            'success': False, 
                            'error': f'This order is assigned to {order.assigned_to.get_full_name() or order.assigned_to.username}. Only the assigned user can process this order.'
                        }, status=403)
                    
                    # Validate current status allowing quantity processing
                    required_status = 'Approved' if order.request_type == 'Release' else 'Seen'
                    
                    if order.status not in [required_status, 'Partially Fulfilled']:
                        return JsonResponse({
                            'success': False, 
                            'error': f'Order must be in "{required_status}" or "Partially Fulfilled" status before processing quantities. Current status: "{order.status}"'
                        }, status=400)

                    # Calculate quantity to process
                    if new_status == "Partially Fulfilled":
                        try:
                            partial_quantity = Decimal(str(data.get('partial_quantity', 0)))
                        except (ValueError, TypeError, InvalidOperation) as e:
                            return JsonResponse({
                                "success": False, 
                                "error": "Invalid partial_quantity value. Must be a valid number."
                            }, status=400)
                    else:  # Full
                        partial_quantity = order.remaining_quantity

                    # Validate quantity
                    if partial_quantity <= 0:
                        return JsonResponse({
                            "success": False, 
                            "error": "Quantity must be greater than zero"
                        }, status=400)
                    
                    if partial_quantity > order.remaining_quantity:
                        return JsonResponse({
                            'success': False, 
                            'error': f'Quantity {partial_quantity} exceeds remaining quantity {order.remaining_quantity}'
                        }, status=400)

                    # Update order quantities
                    order.processed_quantity = (order.processed_quantity or 0) + partial_quantity
                    order.remaining_quantity = max(0, order.quantity - order.processed_quantity)
                    
                    # Set processing tracking fields
                    order.processed_by = request.user
                    order.processed_at = timezone.now()
                    
                    # Update inventory
                    try:
                        # Match by code and warehouse (unique_together constraint)
                        if order.warehouse:
                            inventory_item = InventoryItem.objects.get(
                                code=order.code,
                                warehouse=order.warehouse
                            )
                        else:
                            # Fallback: match by code only if no warehouse specified
                            inventory_item = InventoryItem.objects.get(code=order.code)
                            
                        if order.request_type == "Release":
                            if inventory_item.quantity < partial_quantity:
                                return JsonResponse({
                                    'success': False,
                                    'error': f'Insufficient inventory. Available: {inventory_item.quantity}, Requested: {partial_quantity}'
                                }, status=400)
                            inventory_item.quantity -= partial_quantity
                        elif order.request_type == "Receipt":
                            inventory_item.quantity += partial_quantity
                        
                        inventory_item.save()
                        
                    except InventoryItem.DoesNotExist:
                        logger.warning(f"Inventory item with code '{order.code}' not found in warehouse '{order.warehouse}'. Skipping inventory update.")
                    except InventoryItem.MultipleObjectsReturned:
                        return JsonResponse({
                            'success': False,
                            'error': f'Multiple inventory items found with code "{order.code}". Please contact administrator to resolve duplicate items.'
                        }, status=500)

                    # Update order status based on remaining quantity
                    if order.remaining_quantity <= 0:
                        order.status = 'Completed'
                    else:
                        order.status = 'Partially Fulfilled'

                # Update audit fields
                order.last_updated_by = request.user
                order.save()
                order.refresh_from_db()

                # Prepare response data
                try:
                    status_html = render_to_string('Inventory/includes/status_cell.html', {'order': order})
                except Exception as e:
                    status_html = f'<span class="badge bg-secondary">{order.status}</span>'

                response_data = {
                    'success': True,
                    'new_status': order.get_status_display(),
                    'status_html': status_html.strip(),
                    'processed_quantity': float(order.processed_quantity or 0),
                    'remaining_quantity': float(order.remaining_quantity or 0),
                    'is_completed': order.status in ['Completed', 'Rejected'] or order.remaining_quantity <= 0,
                    'last_updated_by': order.last_updated_by.username if order.last_updated_by else 'System',
                    'message': f'Order {order.request_code or order.id} status updated to {order.get_status_display()}'
                }

                logger.info(f"Successfully processed order {order_id}: {response_data}")
                return JsonResponse(response_data)

        except (MaterialOrder.DoesNotExist, Http404):
            return JsonResponse({
                "success": False, 
                "error": f"Material order with ID {order_id} not found"
            }, status=404)
        except ValidationError as e:
            return JsonResponse({
                "success": False, 
                "error": str(e.message) if hasattr(e, 'message') else str(e)
            }, status=400)
        except Exception as e:
            logger.error(f"Unexpected error updating material status for order {order_id}: {e}", exc_info=True)
            return JsonResponse({
                "success": False, 
                "error": "An unexpected server error occurred. Please try again."
            }, status=500)


@login_required
def update_material_receipt(request, order_id, new_status):
    """
    Wrapper for updating material receipt status.
    Reuses the logic from UpdateMaterialStatusView.
    """
    return UpdateMaterialStatusView.as_view()(request, order_id=order_id, new_status=new_status)


class MaterialReceiptView(LoginRequiredMixin, View):
    template_name = 'Inventory/receive_material.html'

    def get(self, request):
        # Show all inventory items to all users for transparency
        items = InventoryItem.objects.all()
        inventory_items = list(items.values('id', 'name', 'category__name', 'unit__name', 'code', 'warehouse__name'))
        
        formset = MaterialReceiptFormSet(form_kwargs={'user': request.user})
        bulk_form = BulkMaterialRequestForm()
        # Mocking or fetching receipt orders if needed for context
        orders = MaterialOrder.objects.filter(request_type='Receipt').order_by('-date_requested')

        return render(request, self.template_name, {
            'formset': formset,
            'bulk_form': bulk_form,
            'items': items,
            'inventory_items': json.dumps(inventory_items),
            'active_tab': 'single',
            'orders': orders,
        })

    def post(self, request):
        # Check which form was submitted
        if 'bulk_submit' in request.POST:
            return self.handle_bulk_receipt(request)
        else:
            return self.handle_single_receipt(request)

    def handle_single_receipt(self, request):
        formset = MaterialReceiptFormSet(request.POST, form_kwargs={'user': request.user})
        if formset.is_valid():
            for form in formset:
                if form.cleaned_data:
                    material_order = form.save(commit=False)
                    selected_item = form.cleaned_data['name']  # This is an InventoryItem object
                    selected_warehouse = form.cleaned_data.get('warehouse')
                    
                    # Look up the specific inventory item by name and warehouse
                    if selected_item and selected_warehouse:
                        try:
                            inventory_item = InventoryItem.objects.get(
                                name=selected_item.name,
                                warehouse=selected_warehouse
                            )
                            material_order.name = inventory_item.name
                            material_order.category = inventory_item.category
                            material_order.code = inventory_item.code
                            material_order.unit = inventory_item.unit
                        except InventoryItem.DoesNotExist:
                            # Fallback to selected item if specific warehouse combo doesn't exist
                            material_order.name = selected_item.name
                            material_order.category = selected_item.category
                            material_order.code = selected_item.code
                            material_order.unit = selected_item.unit
                    elif selected_item:
                        material_order.name = selected_item.name
                        material_order.category = selected_item.category
                        material_order.code = selected_item.code
                        material_order.unit = selected_item.unit
                    
                    material_order.user = request.user
                    material_order.group = request.user.groups.first() if request.user.groups.exists() else None
                    material_order.request_type = 'Receipt'  # Set as Receipt Request
                    material_order.status = 'Draft'
                    material_order.processed_quantity = 0
                    material_order.remaining_quantity = material_order.quantity
                    material_order.save()
            messages.success(request, "Material receipts submitted successfully!")
            return redirect('material_receipt')
        else:
            print("Formset errors:", formset.errors)
            messages.error(request, "There was an error with your submission.")

        # Show all inventory items to all users for transparency
        items = InventoryItem.objects.all()
        return render(request, self.template_name, {
            'formset': formset,
            'bulk_form': BulkMaterialRequestForm(),
            'items': items,
            'inventory_items': json.dumps(list(items.values('id', 'name', 'category__name', 'unit__name', 'code', 'warehouse__name'))),
            'active_tab': 'single',
            'orders': MaterialOrder.objects.filter(request_type='Receipt').order_by('-date_requested'),
        })

    def handle_bulk_receipt(self, request):
        """Handle bulk receipt uploads from Excel"""
        logger = logging.getLogger(__name__)
        
        bulk_form = BulkMaterialRequestForm(request.POST, request.FILES)
        if not bulk_form.is_valid():
            logger.error(f"Bulk form validation failed: {bulk_form.errors}")
            messages.error(request, "Bulk upload validation failed.")
            return self._render_receipt_form(request, bulk_form=bulk_form)
        
        success_count = 0
        
        try:
            df = bulk_form.cleaned_data['df']
            request_type = 'Receipt'
            priority = bulk_form.cleaned_data['priority']
            
            # Generate a base request code
            base_request_code = generate_request_code()
            df['request_code'] = [f"{base_request_code}-{i+1}" for i in range(len(df))]
            
            for idx, row in df.iterrows():
                try:
                    if not row.get('name'):
                        continue
                        
                    item_name = str(row['name']).strip()
                    item = InventoryItem.objects.filter(name__iexact=item_name).first()
                    
                    if not item:
                        logger.warning(f"Item not found: {item_name}")
                        continue
                    
                    warehouse = None
                    if 'warehouse' in row and pd.notna(row['warehouse']):
                        warehouse = Warehouse.objects.filter(name__iexact=str(row['warehouse']).strip()).first()
                    
                    with transaction.atomic():
                        order_data = {
                            'name': item.name,
                            'quantity': row['quantity'],
                            'category': item.category,
                            'code': item.code,
                            'unit': item.unit,
                            'user': request.user,
                            'group': request.user.groups.first() if request.user.groups.exists() else None,
                            'request_type': request_type,
                            'request_code': row['request_code'],
                            'warehouse': warehouse,
                            'priority': priority,
                            'status': 'Draft',
                            'processed_quantity': 0,
                            'remaining_quantity': row['quantity']
                        }
                        
                        MaterialOrder.objects.create(**order_data)
                        success_count += 1
                        
                except Exception as e:
                    logger.error(f"Error processing row {idx}: {str(e)}")
                    continue
            
            if success_count > 0:
                messages.success(request, f"Successfully created {success_count} material receipt(s)")
                return redirect('material_receipt')
                    
        except Exception as e:
            messages.error(request, f"Error processing bulk receipt: {str(e)}")
            
        return self._render_receipt_form(request, bulk_form=bulk_form)

    def _render_receipt_form(self, request, bulk_form=None):
        items = InventoryItem.objects.all()
        context = {
            'formset': MaterialReceiptFormSet(form_kwargs={'user': request.user}),
            'bulk_form': bulk_form or BulkMaterialRequestForm(),
            'items': items,
            'inventory_items': json.dumps(list(items.values('id', 'name', 'category__name', 'unit__name', 'code', 'warehouse__name'))),
            'active_tab': 'bulk' if bulk_form else 'single',
            'orders': MaterialOrder.objects.filter(request_type='Receipt').order_by('-date_requested'),
        }
        return render(request, self.template_name, context)

class MaterialReceiptListView(LoginRequiredMixin, ListView):
    template_name = 'Inventory/material_receipts.html'
    context_object_name = 'orders'

    def get_queryset(self):
        try:
            # Show all receipt orders to all users for transparency
            return MaterialOrder.objects.filter(request_type='Receipt').order_by('-date_requested')
        except Exception:
            return MaterialOrder.objects.filter(request_type='Receipt').order_by('-date_requested')
