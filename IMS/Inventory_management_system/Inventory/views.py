import base64
import io
import json
import logging
from decimal import Decimal, InvalidOperation
from io import BytesIO

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.generic import TemplateView, View, CreateView, UpdateView, DeleteView, FormView, ListView, DetailView
from django.contrib.auth import authenticate, login, update_session_auth_hash
from django.forms import formset_factory
from django.db import transaction
from django.contrib import messages
from django.urls import reverse_lazy
from django.http import JsonResponse, HttpResponse, Http404
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum, F, ExpressionWrapper, DecimalField, Case, When, Value, IntegerField, Prefetch
from django.utils import timezone
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin, UserPassesTestMixin
from django.utils.timezone import now, timedelta
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.template.loader import render_to_string

# Forms
from .forms import (
    MaterialTransportForm, InventoryItemForm, InventoryItemFormSet, MaterialOrderForm,
    UserUpdateForm, ProfileUpdateForm, PasswordChangeForm, ExcelUploadForm,
    ReportSubmissionForm, BulkMaterialRequestForm, ReleaseLetterUploadForm,
    SiteReceiptForm  # Add SiteReceiptForm
)

# Models
from .models import (
    InventoryItem, Category, Unit, MaterialOrder, Profile, BillOfQuantity,
    MaterialOrderAudit, ReportSubmission, MaterialTransport, ReleaseLetter,
    SiteReceipt, Warehouse  # Add Warehouse
)

# Other views
from .auth_views import Dashboard
from .item_views import AddItem, EditItem, DeleteItem

# Transporter views
from .transporter_views import (
    TransporterListView, TransporterCreateView, TransporterUpdateView, TransporterDetailView, TransporterDeleteView,
    TransportVehicleListView, TransportVehicleCreateView, TransportVehicleUpdateView, TransportVehicleDetailView, TransportVehicleDeleteView,
    TransporterAssignmentView, ReleaseLetterListView, TransporterLegendView, import_transporters, update_transport_status
)

__all__ = [
    'Index', 'RequestMaterialView', 'MaterialOrdersView', 'UpdateMaterialStatusView',
    'ProfileView', 'UploadInventoryView', 'UploadCategoriesAndUnitsView',
    'list_categories', 'list_units', 'MaterialReceiptView', 'MaterialLegendView',
    'MaterialHeatmapView', 'LowInventorySummaryView', 'BillOfQuantityView',
    'UploadBillOfQuantityView', 'consultant_dash', 'management_dashboard',
    'ReportSubmissionListView', 'ReportSubmissionCreateView', 'ReportSubmissionUpdateView',
    'ReportSubmissionDetailView', 'submit_report', 'approve_report', 'reject_report',
    'ReleaseLetterUploadView', 'update_material_receipt', 'MaterialTransportView',
    # Transporter views
    'TransporterListView', 'TransporterCreateView', 'TransporterUpdateView', 'TransporterDetailView', 'TransporterDeleteView',
    'TransportVehicleListView', 'TransportVehicleCreateView', 'TransportVehicleUpdateView', 'TransportVehicleDetailView', 'TransportVehicleDeleteView',
    'TransporterAssignmentView', 'ReleaseLetterListView', 'TransporterLegendView', 'import_transporters', 'update_transport_status',
    'MaterialReceiptListView', 'StaffProfileView',
    'ConsultantDeliveriesView', 'SiteReceiptCreateView', 'SiteReceiptListView'  # Add consultant views
]

# Third-party imports
import uuid
import logging
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime, timedelta
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay
from django.conf import settings
from django.template.loader import render_to_string

MaterialOrderFormSet = formset_factory(MaterialOrderForm, extra=1)


class Index(TemplateView):
    template_name = 'Inventory/index.html'

# Superuser-only access mixin that returns 404 for non-superusers
class SuperuserOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        # Hide existence of the page from non-superusers
        raise Http404()


def generate_request_code():
    """Generate a unique request code in the format REQ-YYYYMMDD-XXXXXX"""
    date_str = timezone.now().strftime('%Y%m%d')
    unique_id = str(uuid.uuid4().int)[:6].upper()
    return f"REQ-{date_str}-{unique_id}"


class RequestMaterialView(LoginRequiredMixin, View):
    template_name = 'Inventory/request_material.html'

    def get(self, request):
        # Show all inventory items to all users for transparency
        items = InventoryItem.objects.all()

        formset = MaterialOrderFormSet(form_kwargs={'user': request.user})
        bulk_form = BulkMaterialRequestForm()
        inventory_items = list(items.values('name', 'category__name', 'unit__name', 'code'))

        return render(request, self.template_name, {
            'formset': formset,
            'bulk_form': bulk_form,
            'items': items,
            'inventory_items': json.dumps(inventory_items),
            'active_tab': 'single'  # Default to single request tab
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
                        selected_item = InventoryItem.objects.filter(name=form.cleaned_data['name']).first()
                        if selected_item:
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
                            from .models import ReleaseLetter
                            from django.utils import timezone
                            
                            title = form.cleaned_data.get('release_letter_title') or f"Release Letter for {material_order.name}"
                            
                            release_letter = ReleaseLetter.objects.create(
                                request_code=material_order.request_code,
                                title=title,
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
            'inventory_items': json.dumps(list(items.values('name', 'category__name', 'unit__name', 'code'))),
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
            release_letter_pdf = bulk_form.cleaned_data.get('release_letter_pdf')
            release_letter_title = bulk_form.cleaned_data.get('release_letter_title')
            
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
                    release_letter = ReleaseLetter.objects.create(
                        title=release_letter_title or f"Release Letter - {base_request_code}",
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
            logger.info(f"DataFrame columns: {df.columns.tolist()}")
            logger.info(f"First few rows of data:\n{df.head().to_string()}")
            
            for idx, row in df.iterrows():
                row_dict = row.to_dict()
                logger.info(f"\n{'='*50}")
                logger.info(f"PROCESSING ROW {idx + 1}:")
                logger.info(f"Row data: {row_dict}")
                
                try:
                    # Skip empty rows
                    if not row.get('name'):
                        logger.warning(f"Skipping empty row at index {idx}")
                        continue
                        
                    # Find the inventory item
                    item_name = str(row['name']).strip()
                    logger.info(f"Looking up item: {item_name}")
                    item = self._find_inventory_item(item_name, request.user)
                    
                    if not item:
                        error_msg = f"Item not found or not accessible: {item_name}"
                        error_messages.append(error_msg)
                        logger.warning(error_msg)
                        continue
                        
                    logger.info(f"Found item: {item.name} (ID: {item.id})")
                    
                    # Handle group assignment
                    logger.info(f"Getting group for item: {item_name}")
                    group = self._get_order_group(request.user, item, item_name)
                    logger.info(f"Assigned to group: {group.name if group else 'None'}")
                    
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
                                'request_type': request_type,
                                'request_code': row['request_code'],  # Use the unique request code from the DataFrame
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
                            logger.info(f"Creating order with data: {order_data}")
                            
                            # Create the order with release letter if available
                            order = MaterialOrder.objects.create(**order_data)
                            
                            # Associate with release letter if available
                            if release_letter:
                                order.release_letter = release_letter
                                order.save(update_fields=['release_letter'])
                                logger.info(f"Associated order ID {order.id} with release letter ID {release_letter.id}")
                            
                            success_count += 1
                            logger.info(f"Successfully created order ID {order.id} for {item.name} with request code {row['request_code']}")
                            
                            # Verify the order was saved
                            if not MaterialOrder.objects.filter(id=order.id).exists():
                                raise Exception(f"Failed to verify order {order.id} was saved to database")
                            
                            logger.info(f"✅ SUCCESS: Created order ID {order.id} for {item_name} with quantity {row['quantity']} and request code {row['request_code']}")
                            
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
                    
                finally:
                    logger.info(f"Completed processing row {idx + 1} for {item_name}")
                    logger.info(f"Success count: {success_count}, Error count: {len(error_messages)}")
            
            # Show success/error messages
            if success_count > 0:
                msg = f"Successfully created {success_count} material request(s) with unique request codes starting with {base_request_code}"
                messages.success(request, msg)
                logger.info(msg)
                
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
            'inventory_items': json.dumps(list(items.values('name', 'category__name', 'unit__name', 'code'))),
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

    def get_queryset(self):
        user = self.request.user
        logger = logging.getLogger(__name__)
        
        try:
            # Base queryset with proper ordering and select_related for performance
            # Show all orders to all authenticated users for transparency
            queryset = MaterialOrder.objects.select_related('user', 'unit', 'category').order_by('-date_requested')
            
            logger.info(f"User {user.username} accessing {queryset.count()} total orders")
            
            # Ensure remaining_quantity is calculated correctly
            for order in queryset:
                if order.remaining_quantity is None or order.remaining_quantity < 0:
                    order.remaining_quantity = max(0, order.quantity - (order.processed_quantity or 0))
                    order.save(update_fields=['remaining_quantity'])
            
            return queryset
            
        except Exception as e:
            logger.error(f"Error in MaterialOrdersView for user {user.username}: {str(e)}", exc_info=True)
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


class UpdateMaterialStatusView(View):
    """
    Handle material order status updates and fulfillment processing.
    Supports: Seen, Approved, Rejected, Partial, Full status updates.
    """
    
    def post(self, request, order_id, new_status):
        logger = logging.getLogger(__name__)
        logger.info(f"UpdateMaterialStatusView called: order_id={order_id}, new_status={new_status}")
        
        # Validate status
        allowed_statuses = ["Seen", "Approved", "Rejected", "Partially Fulfilled", "Full"]
        if new_status not in allowed_statuses:
            logger.error(f"Invalid status: {new_status}")
            return JsonResponse({
                "success": False, 
                "error": f"Invalid status '{new_status}'. Allowed: {', '.join(allowed_statuses)}"
            }, status=400)

        try:
            logger.info("Starting transaction")
            with transaction.atomic():
                logger.info(f"Getting order with id: {order_id}")
                order = get_object_or_404(MaterialOrder, id=order_id)
                logger.info(f"Found order: {order.id}, current status: {order.status}, type: {order.request_type}")
                
                # Parse request data
                try:
                    logger.info("Parsing request body")
                    data = json.loads(request.body.decode('utf-8'))
                    logger.info(f"Parsed data: {data}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    return JsonResponse({
                        "success": False, 
                        "error": "Invalid JSON in request body"
                    }, status=400)

                logger.info(f"Processing status update: Order {order_id}, Status: {new_status}, Current: {order.status}, Type: {order.request_type}")

                # Handle simple status changes
                if new_status in ["Seen", "Approved", "Rejected"]:
                    logger.info(f"Simple status change to: {new_status}")
                    order.status = new_status
                    logger.info(f"Updated order {order_id} status to {new_status}")
                
                # Handle quantity processing (Partial/Full)
                elif new_status in ["Partially Fulfilled", "Full"]:
                    logger.info(f"Processing quantity for status: {new_status}")
                    
                    # Validate current status allows quantity processing
                    required_status = 'Approved' if order.request_type == 'Release' else 'Seen'
                    logger.info(f"Required status: {required_status}, Current status: {order.status}")
                    
                    if order.status not in [required_status, 'Partially Fulfilled']:
                        logger.error(f"Invalid status transition: {order.status} -> {new_status}")
                        return JsonResponse({
                            'success': False, 
                            'error': f'Order must be in "{required_status}" or "Partially Fulfilled" status before processing quantities. Current status: "{order.status}"'
                        }, status=400)

                    # Calculate quantity to process
                    if new_status == "Partially Fulfilled":
                        try:
                            logger.info("Processing partial quantity")
                            partial_quantity = Decimal(str(data.get('partial_quantity', 0)))
                            logger.info(f"Partial quantity: {partial_quantity}")
                        except (ValueError, TypeError, InvalidOperation) as e:
                            logger.error(f"Invalid partial quantity: {e}")
                            return JsonResponse({
                                "success": False, 
                                "error": "Invalid partial_quantity value. Must be a valid number."
                            }, status=400)
                    else:  # Full
                        logger.info("Processing full quantity")
                        partial_quantity = order.remaining_quantity
                        logger.info(f"Full quantity: {partial_quantity}")

                    # Validate quantity
                    if partial_quantity <= 0:
                        logger.error(f"Invalid quantity: {partial_quantity}")
                        return JsonResponse({
                            "success": False, 
                            "error": "Quantity must be greater than zero"
                        }, status=400)
                    
                    if partial_quantity > order.remaining_quantity:
                        logger.error(f"Quantity exceeds remaining: {partial_quantity} > {order.remaining_quantity}")
                        return JsonResponse({
                            'success': False, 
                            'error': f'Quantity {partial_quantity} exceeds remaining quantity {order.remaining_quantity}'
                        }, status=400)

                    logger.info("Updating order quantities")
                    # Process the quantity
                    order.processed_quantity = (order.processed_quantity or 0) + partial_quantity
                    order.remaining_quantity = max(0, order.quantity - order.processed_quantity)
                    
                    # Set processing tracking fields
                    order.processed_by = request.user
                    order.processed_at = timezone.now()
                    
                    logger.info(f"New quantities - Processed: {order.processed_quantity}, Remaining: {order.remaining_quantity}")
                    logger.info(f"Processed by: {request.user.username} at {order.processed_at}")

                    # Update inventory
                    try:
                        logger.info(f"Looking for inventory item: {order.name}")
                        inventory_item = InventoryItem.objects.get(name__iexact=order.name)
                        logger.info(f"Found inventory item: {inventory_item.name}, current quantity: {inventory_item.quantity}")
                        
                        if order.request_type == "Release":
                            if inventory_item.quantity < partial_quantity:
                                logger.error(f"Insufficient inventory: {inventory_item.quantity} < {partial_quantity}")
                                return JsonResponse({
                                    'success': False,
                                    'error': f'Insufficient inventory. Available: {inventory_item.quantity}, Requested: {partial_quantity}'
                                }, status=400)
                            inventory_item.quantity -= partial_quantity
                            logger.info(f"Reduced inventory by {partial_quantity}")
                        elif order.request_type == "Receipt":
                            inventory_item.quantity += partial_quantity
                            logger.info(f"Increased inventory by {partial_quantity}")
                        
                        inventory_item.save()
                        logger.info(f"Updated inventory for {inventory_item.name}: {inventory_item.quantity}")
                        
                    except InventoryItem.DoesNotExist:
                        logger.warning(f"Inventory item '{order.name}' not found. Skipping inventory update.")

                    # Update order status based on remaining quantity
                    if order.remaining_quantity <= 0:
                        order.status = 'Completed'
                        logger.info(f"Order {order_id} completed - no remaining quantity")
                    else:
                        order.status = 'Partially Fulfilled'
                        logger.info(f"Order {order_id} partially fulfilled - {order.remaining_quantity} remaining")

                # Update audit fields
                logger.info("Updating audit fields")
                order.last_updated_by = request.user
                order.save()
                order.refresh_from_db()
                logger.info("Order saved successfully")

                # Prepare response data
                try:
                    logger.info("Rendering status HTML")
                    status_html = render_to_string('Inventory/includes/status_cell.html', {'order': order})
                    logger.info("Status HTML rendered successfully")
                except Exception as e:
                    logger.warning(f"Could not render status_html: {e}")
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

        except MaterialOrder.DoesNotExist:
            logger.error(f"Material order {order_id} not found")
            return JsonResponse({
                "success": False, 
                "error": f"Material order with ID {order_id} not found"
            }, status=404)
        except Exception as e:
            logger.error(f"Unexpected error updating material status for order {order_id}: {e}", exc_info=True)
            return JsonResponse({
                "success": False, 
                "error": "An unexpected server error occurred. Please try again."
            }, status=500)


class ProfileView(LoginRequiredMixin, View):
    template_name = 'Inventory/profile.html'
    permission_required = 'Inventory.view_profile'

    def get(self, request, *args, **kwargs):
        profile, created = Profile.objects.get_or_create(user=request.user)
        if not profile.profile_picture:
            profile.profile_picture = None
        context = {
            'user_form': UserUpdateForm(instance=request.user),
            'profile_form': ProfileUpdateForm(instance=profile),
            'password_form': PasswordChangeForm(),
            'profile': profile
        }
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        profile, created = Profile.objects.get_or_create(user=request.user)
        if not profile.profile_picture:
            profile.profile_picture = None
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        password_form = PasswordChangeForm(request.POST)
        
        if 'update_info' in request.POST:
            if user_form.is_valid() and profile_form.is_valid():
                user_form.save()
                profile_form.save()
                messages.success(request, 'Your profile has been updated!')
                return redirect('profile')
        elif 'change_password' in request.POST:
            if password_form.is_valid():
                user = request.user
                if user.check_password(password_form.cleaned_data['old_password']):
                    user.set_password(password_form.cleaned_data['new_password'])
                    user.save()
                    update_session_auth_hash(request, user)
                    messages.success(request, 'Your password has been updated!')
                    return redirect('profile')
                else:
                    messages.error(request, 'Old password is incorrect.')
        
        context = {
            'user_form': user_form,
            'profile_form': profile_form,
            'password_form': password_form,
            'profile': profile
        }
        return render(request, self.template_name, context)


class UploadInventoryView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser  # Only allow admins

    def get(self, request):
        form = ExcelUploadForm()
        return render(request, 'Inventory/upload_inventory.html', {'form': form})

    def post(self, request):
        if not self.request.user.is_superuser:
            return JsonResponse({'error': 'Unauthorized access'}, status=403)

        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                # Read Excel File
                df = pd.read_excel(file, engine='openpyxl')

                # Required columns in Excel
                required_columns = ['name', 'quantity', 'category', 'code', 'unit', 'warehouse']
                if not all(col in df.columns for col in required_columns):
                    messages.error(request, "Excel file is missing required columns.")
                    return redirect('dashboard')

                # Load category & unit mappings from DB
                category_mapping = {c.name: c.id for c in Category.objects.all()}
                unit_mapping = {u.name: u.id for u in Unit.objects.all()}
                warehouse_mapping = {w.name: w.id for w in Warehouse.objects.all()}

                for index, row in df.iterrows():
                    # Convert category & unit names to IDs
                    category_id = category_mapping.get(row['category'])
                    unit_id = unit_mapping.get(row['unit'])
                    warehouse_id = warehouse_mapping.get(row['warehouse'])

                    if not category_id or not unit_id or not warehouse_id:
                        messages.error(request, f"Error: Invalid category, unit, or warehouse at row {index + 2}")
                        continue

                    item, created = InventoryItem.objects.get_or_create(
                        code=row['code'],
                        defaults={
                            'name': row['name'],
                            'quantity': row['quantity'],
                            'category_id': category_id,
                            'unit_id': unit_id,
                            'warehouse_id': warehouse_id,
                            'user': request.user
                        }
                    )
                    if not created:
                        item.quantity += row['quantity']
                        item.warehouse_id = warehouse_id
                        item.save()

                messages.success(request, "Inventory updated successfully!")
            except Exception as e:
                messages.error(request, f"Error processing file: {e}")

            return redirect('dashboard')

        return render(request, 'Inventory/upload_inventory.html', {'form': form})

class UploadCategoriesAndUnitsView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser  # Only allow admins

    def get(self, request):
        form = ExcelUploadForm()
        return render(request, 'Inventory/upload_categories_units.html', {'form': form})

    def post(self, request):
        if not self.request.user.is_superuser:
            return JsonResponse({'error': 'Unauthorized access'}, status=403)

        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                # Read Excel File
                df = pd.read_excel(file, engine='openpyxl')

                # Column Mapping: Convert Excel Columns to Match Model Fields
                column_mapping = {
                    'CATEGORY': 'category',
                    'UNIT': 'unit'
                }
                df.rename(columns=column_mapping, inplace=True)

                # Add Categories to Database
                unique_categories = df['category'].dropna().unique()
                for category_name in unique_categories:
                    Category.objects.get_or_create(name=category_name)

                # Add Units to Database
                unique_units = df['unit'].dropna().unique()
                for unit_name in unique_units:
                    Unit.objects.get_or_create(name=unit_name)

                messages.success(request, "Categories and Units uploaded successfully!")
            except Exception as e:
                messages.error(request, f"Error processing file: {e}")

            return redirect('dashboard')

        return render(request, 'Inventory/upload_categories_units.html', {'form': form})



def list_categories(request):
    categories = list(Category.objects.values('id', 'name'))
    return JsonResponse({'categories': categories})


def list_units(request):
    units = list(Unit.objects.values('id', 'name'))
    return JsonResponse({'units': units})


class MaterialReceiptView(LoginRequiredMixin, View):
    template_name = 'Inventory/receive_material.html'

    def get(self, request):
        # Show all inventory items to all users for transparency
        items = InventoryItem.objects.all()

        inventory_items = list(items.values('name', 'category__name', 'unit__name', 'code'))
        formset = MaterialOrderFormSet(form_kwargs={'user': request.user})
        bulk_form = BulkMaterialRequestForm()
        orders = self._get_receipt_orders(request.user)

        return render(request, self.template_name, {
            'formset': formset,
            'bulk_form': bulk_form,
            'items': items,
            'inventory_items': json.dumps(inventory_items),
            'active_tab': 'single',
            'orders': orders,
        })

    def post(self, request):
        formset = MaterialOrderFormSet(request.POST, form_kwargs={'user': request.user})
        if formset.is_valid():
            for form in formset:
                if form.cleaned_data:
                    material_order = form.save(commit=False)
                    selected_item = InventoryItem.objects.filter(name=form.cleaned_data['name']).first()
                    if selected_item:
                        material_order.category = selected_item.category
                        material_order.code = selected_item.code
                        material_order.unit = selected_item.unit
                    material_order.user = request.user
                    material_order.group = request.user.groups.first() if request.user.groups.exists() else None
                    material_order.request_type = 'Receipt'  # Set as Receipt Request
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
            'inventory_items': json.dumps(list(items.values('name', 'category__name', 'unit__name', 'code'))),
            'active_tab': 'single',
            'orders': self._get_receipt_orders(request.user),
        })

    def _find_inventory_item(self, item_name, user):
        logger = logging.getLogger(__name__)
        item = InventoryItem.objects.filter(name=item_name).first()
        if item:
            return item

    def _get_receipt_orders(self, user):
        """Return MaterialOrder queryset for receipts - show all to all users for transparency."""
        try:
            # Show all receipt orders to all users for transparency
            return MaterialOrder.objects.filter(request_type='Receipt').order_by('-date_requested')
        except Exception:
            return MaterialOrder.objects.filter(request_type='Receipt').order_by('-date_requested')


class MaterialLegendView(LoginRequiredMixin, ListView):
    template_name = 'Inventory/material_legend.html'
    context_object_name = 'materials'
    paginate_by = 25  # Show 25 items per page

    def get_queryset(self):
        # Show all materials to all users for transparency
        queryset = InventoryItem.objects.all().order_by('code')
        return queryset.select_related('category', 'unit', 'warehouse')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Material Code Legend'
        return context


class MaterialHeatmapView(LoginRequiredMixin, View):
    template_name = 'Inventory/material_heatmap.html'

    def get(self, request):
        try:
            # Show all orders and items to all authenticated users
            orders = MaterialOrder.objects.all()
            items = InventoryItem.objects.all()

            period = request.GET.get('period', 'month')
            report_type = request.GET.get('type', 'release')

            if report_type in ['release', 'receipt']:
                orders = orders.filter(request_type=report_type.capitalize())
                df = pd.DataFrame.from_records(orders.values('code', 'name', 'processed_quantity', 'date_requested'))
                if df.empty:
                    df = pd.DataFrame(columns=['code', 'name', 'processed_quantity', 'date_requested'])
                else:
                    df['date'] = pd.to_datetime(df['date_requested'])
                    if period == 'day':
                        df['period'] = df['date'].dt.strftime('%Y-%m-%d')
                    elif period == 'week':
                        df['period'] = df['date'].dt.strftime('Week %U, %Y')
                    else:  # month
                        df['period'] = df['date'].dt.strftime('%b %Y')
                    
                    # Create pivot table with material names for better readability
                    pivot = pd.pivot_table(
                        df, 
                        values='processed_quantity', 
                        index=['code', 'name'], 
                        columns='period', 
                        aggfunc='sum', 
                        fill_value=0
                    )
                    
                    # Reset index to get code and name as columns
                    pivot = pivot.reset_index()
                    
                    # Create a combined label for code and name
                    pivot['material'] = pivot.apply(
                        lambda x: f"{x['code']} - {x['name']}", 
                        axis=1
                    )
                    
                    # Set the combined label as index
                    pivot = pivot.set_index('material').drop(['code', 'name'], axis=1, errors='ignore')
            else:
                # For stock view, show current quantities
                df = pd.DataFrame.from_records(items.values('code', 'name', 'quantity'))
                if not df.empty:
                    df['material'] = df.apply(
                        lambda x: f"{x['code']} - {x['name']}", 
                        axis=1
                    )
                    # Create a DataFrame with material as index and quantity as value
                    pivot = df[['material', 'quantity']].set_index('material').T
                    # Ensure all materials are included as columns
                    for material in df['material'].tolist():
                        if material not in pivot.columns:
                            pivot[material] = 0
                else:
                    pivot = pd.DataFrame()

            # Initialize pivot if empty (for cases with no data)
            if 'pivot' not in locals() or pivot is None:
                pivot = pd.DataFrame()

            # Generate Plotly figure
            if not pivot.empty:
                import plotly.express as px
                import plotly.graph_objects as go
                
                # Convert pivot to long format for Plotly
                df_plot = pivot.reset_index().melt(
                    id_vars='material', 
                    var_name='period', 
                    value_name='quantity'
                )
                
                # Create the heatmap
                fig = px.imshow(
                    pivot.values,
                    labels=dict(x="Time Period", y="Material", color="Quantity"),
                    x=pivot.columns.tolist(),
                    y=pivot.index.tolist(),
                    aspect="auto",
                    color_continuous_scale='Viridis',
                    text_auto=True
                )
                
                # Customize layout
                title = f"{report_type.capitalize()} Heatmap ({period.capitalize()})"
                fig.update_layout(
                    title={
                        'text': title,
                        'y':0.95,
                        'x':0.5,
                        'xanchor': 'center',
                        'yanchor': 'top',
                        'font': {'size': 20, 'family': 'Arial, sans-serif'}
                    },
                    xaxis_title="Time Period",
                    yaxis_title="Material",
                    height=600 + (len(pivot) * 15),  # Adjust height based on number of materials
                    margin=dict(l=150, r=50, b=150, t=100, pad=4),
                    coloraxis_colorbar=dict(
                        title="Quantity",
                        thicknessmode="pixels", thickness=20,
                        lenmode="pixels", len=300,
                        yanchor="top", y=1,
                        ticks="outside"
                    )
                )
                
                # Customize hover text
                fig.update_traces(
                    hovertemplate='<b>Material</b>: %{y}<br>' +
                                 '<b>Period</b>: %{x}<br>' +
                                 '<b>Quantity</b>: %{z}<extra></extra>',
                    texttemplate="%{z}",
                    textfont={"size": 10}
                )
                
                # Convert the plot to HTML
                plot_div = fig.to_html(
                    full_html=False, 
                    include_plotlyjs='cdn',  # Use CDN for Plotly.js
                    config={
                        'displayModeBar': True,
                        'scrollZoom': True,
                        'responsive': True
                    }
                )
                
                has_data = True
            else:
                plot_div = ""
                has_data = False
            
            context = {
                'plot_div': plot_div,
                'report_type': report_type,
                'period': period,
                'has_data': has_data
            }
            return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"Error generating heatmap: {str(e)}", exc_info=True)
            messages.error(request, f"Error generating heatmap: {str(e)}")
            return render(request, self.template_name, {'has_data': False})

    def post(self, request):
        # Show all orders and items to all users for transparency
        orders = MaterialOrder.objects.all()
        items = InventoryItem.objects.all()

        period = request.POST.get('period', 'month')
        report_type = request.POST.get('type', 'release')

        if report_type in ['release', 'receipt']:
            orders = orders.filter(request_type=report_type.capitalize())
            df = pd.DataFrame.from_records(orders.values('code', 'processed_quantity', 'date_requested'))
            if df.empty:
                df = pd.DataFrame(columns=['code', 'processed_quantity', 'date_requested'])
            else:
                df['date'] = pd.to_datetime(df['date_requested'])
                if period == 'day':
                    df['period'] = df['date'].dt.date
                elif period == 'week':
                    df['period'] = df['date'].dt.to_period('W').apply(lambda r: r.start_time.date())
                else:  # month
                    df['period'] = df['date'].dt.to_period('M').apply(lambda r: r.start_time.date())
                pivot = pd.pivot_table(df, values='processed_quantity', index='code', columns='period', aggfunc='sum', fill_value=0)
        else:
            df = pd.DataFrame.from_records(items.values('code', 'quantity'))
            pivot = df.set_index('code').T

        # Set up a professional, modern style heatmap for PDF
        plt.figure(figsize=(15, 10))
        sns.set_style("whitegrid")
        heatmap = sns.heatmap(
            pivot,
            cmap="Blues",
            annot=True,
            fmt='.0f',
            cbar_kws={'label': 'Quantity', 'shrink': 0.8, 'pad': 0.02, 'orientation': 'vertical'},
            linewidths=0.5,
            annot_kws={'size': 10, 'weight': 'bold'},
            square=True,
            vmin=0,
            vmax=pivot.max().max() * 1.1
        )
        plt.title(f"{report_type.capitalize()} Heatmap ({period.capitalize()})", fontsize=16, pad=20, fontweight='bold', color='#2c3e50')
        plt.xlabel("Time Period", fontsize=12, color='#2c3e50')
        plt.ylabel("Material Code", fontsize=12, color='#2c3e50')

        plt.xticks(rotation=45, ha='right', fontsize=10)
        plt.yticks(fontsize=10)
        plt.tight_layout()

        # Save to PDF buffer
        buffer = BytesIO()
        plt.savefig(buffer, format='pdf', bbox_inches='tight', dpi=300)
        plt.close()
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{report_type}_heatmap_{period}.pdf"'
        return response
    
class LowInventorySummaryView(LoginRequiredMixin, ListView):
    """
    View for displaying low inventory items.
    Accessible to all authenticated users.
    Shows all low inventory items regardless of group.
    """
    template_name = 'Inventory/low_inventory_summary.html'
    context_object_name = 'low_items'

    def get_queryset(self):
        """
        Return all low inventory items.
        Accessible to all authenticated users.
        """
        LOW_QUANTITY = 5  # Match the threshold used in Dashboard view
        return InventoryItem.objects.filter(quantity__lte=LOW_QUANTITY).select_related('category', 'unit', 'warehouse').order_by('name')

class BillOfQuantityView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """
    View for displaying Bill of Quantities.
    Accessible to superusers only.
    Shows all BOQ items.
    """
    template_name = 'Inventory/bill_of_quantity.html'
    context_object_name = 'boq_items'

    def get_queryset(self):
        """
        Return all BOQ items.
        Accessible to superusers only.
        """
        return BillOfQuantity.objects.all().order_by('package_number', 'material_description')

    
logger = logging.getLogger(__name__)

class UploadBillOfQuantityView(LoginRequiredMixin, SuperuserOnlyMixin, View):

    def get(self, request):
        form = ExcelUploadForm()
        return render(request, 'Inventory/upload_bill_of_quantity.html', {'form': form})

    def post(self, request):
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            try:
                df = pd.read_excel(file, engine='openpyxl')
                required_columns = [
                    'region', 'district', 'community', 'consultant', 'contractor', 
                    'package_number', 'material_description', 'item_code', 
                    'contract_quantity', 'quantity_received'
                ]
                if not all(col in df.columns for col in required_columns):
                    missing_cols = [col for col in required_columns if col not in df.columns]
                    messages.error(request, f"Excel file is missing required columns: {', '.join(missing_cols)}")
                    return redirect('bill_of_quantity')

                for index, row in df.iterrows():
                    try:
                        # Handle NaN or empty values
                        contract_qty = int(float(row['contract_quantity'])) if pd.notna(row['contract_quantity']) else 0
                        qty_received = int(float(row['quantity_received'])) if pd.notna(row['quantity_received']) else 0
                        item_code = str(row['item_code']) if pd.notna(row['item_code']) else f"Unknown-{index}"

                        boq, created = BillOfQuantity.objects.get_or_create(
                            item_code=item_code,
                            package_number=row['package_number'],
                            defaults={
                                'region': row['region'],
                                'district': row['district'],
                                'community': row['community'] if pd.notna(row['community']) else None,
                                'consultant': row['consultant'],
                                'contractor': row['contractor'],
                                'material_description': row['material_description'],
                                'contract_quantity': contract_qty,
                                'quantity_received': qty_received,
                                'user': request.user,
                            }
                        )
                        if not created:
                            boq.region = row['region']
                            boq.district = row['district']
                            boq.community = row['community'] if pd.notna(row['community']) else None
                            boq.consultant = row['consultant']
                            boq.contractor = row['contractor']
                            boq.material_description = row['material_description']
                            boq.contract_quantity = contract_qty
                            boq.quantity_received = qty_received
                            boq.save()

                    except Exception as e:
                        logger.error(f"Error processing row {index}: {str(e)}")
                        messages.error(request, f"Error at row {index + 2}: {str(e)}")
                        continue  # Skip problematic rows but continue processing others

                messages.success(request, "Bill of Quantity updated successfully!")
            except Exception as e:
                logger.error(f"Error processing Excel file: {str(e)}")
                messages.error(request, f"Error processing file: {str(e)}")
            return redirect('bill_of_quantity')

        return render(request, 'Inventory/upload_bill_of_quantity.html', {'form': form})
    


def consultant_dash(request):
    orders = MaterialOrder.objects.all().order_by('-date_requested')
    profile, created = Profile.objects.get_or_create(user=request.user)  # Ensure profile exists
    context = {
        'orders': orders,
        'profile': profile  # Pass profile to the context
    }
    return render(request, 'Inventory/receive_material.html', context)

logger = logging.getLogger(__name__)

@login_required
def management_dashboard(request):
    # Check if user is in Management group or is superuser
    if not (request.user.groups.filter(name='Management').exists() or request.user.is_superuser):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('dashboard')
        
    # Log the total number of orders
    total_orders = MaterialOrder.objects.count()
    logger.debug(f"Total Orders: {total_orders}")
    
    # Get all users with their groups and permissions
    users = User.objects.prefetch_related('groups').all()
    user_grades = {}
    
    # Calculate grades for each user (example: based on activity)
    for user in users:
        user_orders = MaterialOrder.objects.filter(user=user)
        total_orders = user_orders.count()
        completed_orders = user_orders.filter(status='Completed').count()
        
        # Performance Calculation (based on order completion rate)
        if total_orders > 0:
            completion_rate = (completed_orders / total_orders) * 100
            if completion_rate >= 90:
                grade_letter = 'A'
                grade_color = 'success'
            elif completion_rate >= 80:
                grade_letter = 'B'
                grade_color = 'info'
            elif completion_rate >= 70:
                grade_letter = 'C'
                grade_color = 'warning'
            else:
                grade_letter = 'D'
                grade_color = 'danger'
        else:
            completion_rate = 0
            grade_letter = 'N/A'
            grade_color = 'secondary'
        
        user_grades[user.id] = {
            'username': user.username,
            'groups': ", ".join([g.name for g in user.groups.all()]),
            'grade': completion_rate,
            'grade_letter': grade_letter,
            'grade_color': grade_color,
            'total_orders': total_orders,
            'completed_orders': completed_orders
        }
    
    # Debug: Check if groups exist
    consultants_group = Group.objects.filter(name='Consultants').first()
    storekeepers_group = Group.objects.filter(name='Storekeepers').first()
    logger.debug(f"Consultants Group Exists: {consultants_group is not None}")
    logger.debug(f"Storekeepers Group Exists: {storekeepers_group is not None}")

    # Debug: Count users in each group
    consultants_users = User.objects.filter(groups__name='Consultants').count()
    storekeepers_users = User.objects.filter(groups__name='Storekeepers').count()
    logger.debug(f"Users in Consultants Group: {consultants_users}")
    logger.debug(f"Users in Storekeepers Group: {storekeepers_users}")

    # Debug: Check orders for each condition
    received_by_consultants = MaterialOrder.objects.filter(
        status='Received', user__groups__name='Consultants'
    )
    logger.debug(f"Received Orders by Consultants: {received_by_consultants.count()}")
    total_received_by_consultants = received_by_consultants.aggregate(total=Sum('quantity'))['total'] or 0
    logger.debug(f"Total Received by Consultants (Sum): {total_received_by_consultants}")

    received_by_storekeepers = MaterialOrder.objects.filter(
        status='Received', user__groups__name='Storekeepers'
    )
    logger.debug(f"Received Orders by Storekeepers: {received_by_storekeepers.count()}")
    total_received_by_storekeepers = received_by_storekeepers.aggregate(total=Sum('quantity'))['total'] or 0
    logger.debug(f"Total Received by Storekeepers (Sum): {total_received_by_storekeepers}")

    released_by_storekeepers = MaterialOrder.objects.filter(
        request_type='Release', user__groups__name='Storekeepers'
    )
    logger.debug(f"Released Orders by Storekeepers: {released_by_storekeepers.count()}")
    total_released_by_storekeepers = released_by_storekeepers.aggregate(total=Sum('quantity'))['total'] or 0
    logger.debug(f"Total Released by Storekeepers (Sum): {total_released_by_storekeepers}")

    total_on_site = MaterialOrder.objects.filter(status='On Site').count()
    logger.debug(f"Total On Site: {total_on_site}")

    pending_orders = MaterialOrder.objects.filter(status='Pending').count()
    logger.debug(f"Pending Orders: {pending_orders}")

    orders = MaterialOrder.objects.all().order_by('-date_requested')
    receipts = MaterialOrder.objects.filter(status__in=['Received', 'On Site']).order_by('-date_requested')
    audit_trail = MaterialOrderAudit.objects.all().order_by('-date')
    profile, created = Profile.objects.get_or_create(user=request.user)

    # Get system-wide notifications
    notifications = []
    
    # Low inventory items - using a default reorder level of 10 since the field doesn't exist
    # TODO: Add reorder_level field to InventoryItem model for better inventory management
    low_inventory = InventoryItem.objects.filter(quantity__lt=10)  # Default reorder level of 10
    if low_inventory.exists():
        notifications.append({
            'type': 'warning',
            'message': f'{low_inventory.count()} items are below reorder level',
            'url': reverse('low_inventory_summary')
        })
    
    # Pending orders
    if pending_orders > 0:
        notifications.append({
            'type': 'info',
            'message': f'{pending_orders} pending material orders',
            'url': reverse('material_orders')
        })
    
    # Recent activities (last 10)
    recent_activities = MaterialOrderAudit.objects.all().order_by('-date')[:10]
    
    context = {
        'total_orders': total_orders,
        'total_received_by_consultants': total_received_by_consultants,
        'total_received_by_storekeepers': total_received_by_storekeepers,
        'total_released_by_storekeepers': total_released_by_storekeepers,
        'total_on_site': total_on_site,
        'pending_orders': pending_orders,
        'orders': orders[:10],  # Only show recent 10 orders
        'audit_trail': recent_activities,
        'notifications': notifications,
        'user_grades': user_grades,
        'low_inventory_count': low_inventory.count(),
        'profile': profile,
    }
    return render(request, 'Inventory/management_dashboard.html', context)


    if request.method == 'POST':
        if new_status not in ['Received', 'On Site']:  # Restrict to valid statuses
            return JsonResponse({'success': False, 'error': 'Invalid status.'}, status=400)

        try:
            order = MaterialOrder.objects.get(id=order_id)
            # Validate status transition
            if new_status == 'On Site' and order.status != 'Received':
                return JsonResponse({'success': False, 'error': 'Order must be marked as Received before On Site.'}, status=400)

            order.status = new_status
            order.last_updated_by = request.user
            order.save()

            # Log the action
            MaterialOrderAudit.objects.create(
                order=order,
                action=f'Set to {new_status}',
                performed_by=request.user
            )

            return JsonResponse({
                'success': True,
                'new_status': new_status,
                'last_updated_by': request.user.username
            })
        except MaterialOrder.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)

class ReportSubmissionListView(LoginRequiredMixin, ListView):
    model = ReportSubmission
    template_name = 'inventory/report_submission_list.html'
    context_object_name = 'reports'
    
    def get_queryset(self):
        # Show all reports to all users for transparency
        return ReportSubmission.objects.all()

class ReportSubmissionCreateView(LoginRequiredMixin, CreateView):
    model = ReportSubmission
    form_class = ReportSubmissionForm
    template_name = 'Inventory/report_submission_form.html'
    success_url = reverse_lazy('report-submission-list')

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

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.group = self.request.user.groups.first()
        return super().form_valid(form)

class ReportSubmissionUpdateView(LoginRequiredMixin, UpdateView):
    model = ReportSubmission
    form_class = ReportSubmissionForm
    template_name = 'inventory/report_submission_form.html'
    success_url = reverse_lazy('report-submission-list')

    def get_queryset(self):
        # Only allow editing of draft reports
        if self.request.user.is_superuser:
            return ReportSubmission.objects.all()
        return ReportSubmission.objects.filter(
            user=self.request.user,
            status='Draft'
        )

class ReportSubmissionDetailView(LoginRequiredMixin, DetailView):
    model = ReportSubmission
    template_name = 'inventory/report_submission_detail.html'
    context_object_name = 'report'

    def get_queryset(self):
        # Show all reports to all users for transparency
        return ReportSubmission.objects.all()

def submit_report(request, pk):
    """View to handle report submission"""
    report = ReportSubmission.objects.get(pk=pk)
    if request.user == report.user and report.status == 'Draft':
        report.status = 'Submitted'
        report.save()
    return redirect('report-submission-list')

def approve_report(request, pk):
    """View to handle report approval"""
    if request.user.is_superuser:
        report = ReportSubmission.objects.get(pk=pk)
        if report.status == 'Submitted':
            report.status = 'Approved'
            report.save()
            # Create or update corresponding BOQ
            report.create_or_update_boq()
    return redirect('report-submission-list')

def reject_report(request, pk):
    """View to handle report rejection"""
    if request.user.is_superuser:
        report = ReportSubmission.objects.get(pk=pk)
        if report.status == 'Submitted':
            report.status = 'Rejected'
            report.save()
    return redirect('report-submission-list')


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
                full_request_code = form.cleaned_data.get('full_request_code') or base_request_code
                
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


def update_material_receipt(request, order_id, new_status):
    """
    Handle AJAX updates for material receipts.
    Mirrors the release actions but adds to stock instead.
    URL carries new_status: Seen | Partial | Full
    If Partial, expects JSON body with 'partial_quantity' or form-encoded fallback.
    """
    if request.method != 'POST' or request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    if new_status not in ["Seen", "Partially Fulfilled", "Full"]:
        return JsonResponse({"success": False, "error": "Invalid status."}, status=400)

    try:
        with transaction.atomic():
            order = get_object_or_404(MaterialOrder, id=order_id)

            if order.request_type != 'Receipt':
                return JsonResponse({"success": False, "error": "This endpoint only handles receipt orders."}, status=400)

            is_partial = new_status == "Partially Fulfilled"

            # Parse body as JSON first, fallback to POST for form-encoded
            data = {}
            if request.body:
                try:
                    data = json.loads(request.body.decode('utf-8'))
                except Exception:
                    data = {}

            # Parse partial quantity safely
            partial_quantity = 0
            if is_partial:
                raw_pq = data.get('partial_quantity', request.POST.get('partial_quantity', 0))
                try:
                    partial_quantity = int(float(raw_pq))
                except (TypeError, ValueError):
                    partial_quantity = 0

            # Ensure remaining up-to-date
            if order.remaining_quantity is None:
                order.remaining_quantity = (order.quantity or 0) - (order.processed_quantity or 0)
            try:
                remaining_int = int(float(order.remaining_quantity))
            except Exception:
                remaining_int = 0

            qty_to_process = partial_quantity if is_partial else remaining_int

            # Validate partial
            if is_partial and (partial_quantity <= 0 or partial_quantity > remaining_int):
                return JsonResponse({"success": False, "error": "Invalid partial quantity."}, status=400)

            inventory_item = InventoryItem.objects.filter(name=order.name).first()
            if not inventory_item:
                return JsonResponse({"success": False, "error": "No matching inventory item found for this order."}, status=400)

            # Initialize quantity if None
            if inventory_item.quantity is None:
                inventory_item.quantity = 0

            if new_status == 'Seen':
                order.status = 'Seen'
            else:
                # Receipt adds to stock
                inventory_item.quantity += qty_to_process
                inventory_item.save()

                # Update order progress
                order.processed_quantity = (order.processed_quantity or 0) + qty_to_process
                # Recompute remaining from source values to avoid drift
                order.remaining_quantity = max(0, int(float(order.quantity or 0)) - int(float(order.processed_quantity or 0)))
                if order.remaining_quantity <= 0:
                    order.status = 'Completed'
                else:
                    order.status = 'Partially Fulfilled'

            order.last_updated_by = request.user
            order.save()

            return JsonResponse({
                'success': True,
                'status': order.status,
                'processed_quantity': float(order.processed_quantity or 0),
                'remaining_quantity': float(order.remaining_quantity or 0),
                'inventory_quantity': inventory_item.quantity,
                'last_updated_by': getattr(request.user, 'username', None),
            })

    except MaterialOrder.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

class MaterialTransportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'Inventory.view_materialtransport'

    def get(self, request, pk=None):
        """Handle GET requests based on the URL path."""
        path = request.path
        if 'transport_detail' in path and pk:
            # Detail view
            transport = get_object_or_404(MaterialTransport, pk=pk)
            return render(request, 'Inventory/transport_detail.html', {'transport': transport})
        elif 'transport_list' in path:
            # List view
            transports = MaterialTransport.objects.all()
            return render(request, 'Inventory/transport_list.html', {'transports': transports})
        elif 'transport_form' in path:
            # Create form view
            form = MaterialTransportForm()
            return render(request, 'Inventory/transport_form.html', {'form': form})
        else:
            # Dashboard view (transport_dash)
            transports = MaterialTransport.objects.all()
            return render(request, 'Inventory/transport_dash.html', {'transports': transports})

    def post(self, request):
        """Handle POST requests for creating a new transport."""
        if 'transport_form' in request.path:
            form = MaterialTransportForm(request.POST)
            if form.is_valid():
                form.save()
                return redirect('transport_list')
            return render(request, 'Inventory/transport_form.html', {'form': form})
        return redirect('transport_list')  # Fallback

class MaterialReceiptListView(LoginRequiredMixin, ListView):
    template_name = 'Inventory/material_receipts.html'
    context_object_name = 'orders'

    def get_queryset(self):
        try:
            # Show all receipt orders to all users for transparency
            return MaterialOrder.objects.filter(request_type='Receipt').order_by('-date_requested')
        except Exception:
            return MaterialOrder.objects.filter(request_type='Receipt').order_by('-date_requested')

class StaffProfileView(LoginRequiredMixin, View):
    """
    Comprehensive staff profile view showing detailed metrics and activities for a specific user.
    Accessible to superusers and management users.
    """
    
    def get(self, request, username):
        # Ensure only superusers and management can access staff profiles
        if not (request.user.is_superuser or request.user.groups.filter(name='Management').exists()):
            return redirect('dashboard')
        
        try:
            # Get the target user
            target_user = get_object_or_404(User, username=username)
            
            # Get or create the user's profile
            try:
                target_profile = target_user.profile
            except Profile.DoesNotExist:
                target_profile = Profile.objects.create(user=target_user)
            
            # Get date range for filtering (default to last 30 days)
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=30)
            
            # Material Orders Statistics
            user_orders = MaterialOrder.objects.filter(user=target_user)
            recent_orders = user_orders.filter(date_requested__date__gte=start_date)
            
            order_stats = {
                'total_orders': user_orders.count(),
                'recent_orders': recent_orders.count(),
                'pending_orders': user_orders.filter(status='Pending').count(),
                'completed_orders': user_orders.filter(status='Completed').count(),
                'draft_orders': user_orders.filter(status='Draft').count(),
                'partially_fulfilled': user_orders.filter(status='Partially Fulfilled').count(),
            }
            
            # Request Type Breakdown
            release_orders = user_orders.filter(request_type='Release').count()
            receipt_orders = user_orders.filter(request_type='Receipt').count()
            
            # Recent Activity (Material Orders)
            recent_material_orders = recent_orders.order_by('-date_requested')[:10]
            
            # Audit Log Activity
            try:
                from audit_log.models import AuditLog
                user_audit_logs = AuditLog.objects.filter(user=target_user).order_by('-timestamp')[:20]
                audit_stats = {
                    'total_actions': AuditLog.objects.filter(user=target_user).count(),
                    'recent_actions': AuditLog.objects.filter(
                        user=target_user, 
                        timestamp__date__gte=start_date
                    ).count(),
                }
            except ImportError:
                user_audit_logs = []
                audit_stats = {'total_actions': 0, 'recent_actions': 0}
            
            # Performance Calculation (based on order completion rate)
            if order_stats['total_orders'] > 0:
                completion_rate = (order_stats['completed_orders'] / order_stats['total_orders']) * 100
                if completion_rate >= 90:
                    performance_grade = 'A'
                    performance_color = 'success'
                elif completion_rate >= 80:
                    performance_grade = 'B'
                    performance_color = 'info'
                elif completion_rate >= 70:
                    performance_grade = 'C'
                    performance_color = 'warning'
                else:
                    performance_grade = 'D'
                    performance_color = 'danger'
            else:
                completion_rate = 0
                performance_grade = 'N/A'
                performance_color = 'secondary'
            
            # User Groups/Roles
            user_groups = target_user.groups.all()
            
            # Activity Timeline (combine orders and audit logs)
            timeline_items = []
            
            # Add recent orders to timeline
            for order in recent_material_orders:
                timeline_items.append({
                    'type': 'order',
                    'timestamp': order.date_requested,
                    'title': f'Material Order: {order.name}',
                    'description': f'{order.get_request_type_display()} - {order.quantity} {order.unit}',
                    'status': order.status,
                    'icon': '📦' if order.request_type == 'Release' else '📥'
                })
            
            # Add recent audit logs to timeline
            for log in user_audit_logs[:10]:
                timeline_items.append({
                    'type': 'audit',
                    'timestamp': log.timestamp,
                    'title': f'{log.action}: {log.model_name}',
                    'description': f'Object ID: {log.object_id}',
                    'status': log.action,
                    'icon': '📝'
                })
            
            # Sort timeline by timestamp (most recent first)
            timeline_items.sort(key=lambda x: x['timestamp'], reverse=True)
            timeline_items = timeline_items[:15]  # Limit to 15 most recent items
            
            # Monthly Activity Chart Data (last 6 months)
            monthly_data = []
            for i in range(6):
                month_start = (end_date.replace(day=1) - timedelta(days=i*30)).replace(day=1)
                month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                
                month_orders = user_orders.filter(
                    date_requested__date__gte=month_start,
                    date_requested__date__lte=month_end
                ).count()
                
                monthly_data.append({
                    'month': month_start.strftime('%b %Y'),
                    'orders': month_orders
                })
            
            monthly_data.reverse()  # Show oldest to newest
            
            context = {
                'target_user': target_user,
                'target_profile': target_profile,
                'user_groups': user_groups,
                'order_stats': order_stats,
                'release_orders': release_orders,
                'receipt_orders': receipt_orders,
                'audit_stats': audit_stats,
                'completion_rate': completion_rate,
                'performance_grade': performance_grade,
                'performance_color': performance_color,
                'recent_material_orders': recent_material_orders,
                'user_audit_logs': user_audit_logs,
                'timeline_items': timeline_items,
                'monthly_data': monthly_data,
                'date_range': f"{start_date.strftime('%B %d, %Y')} - {end_date.strftime('%B %d, %Y')}",
                'start_date': start_date,
                'end_date': end_date,
            }
            
            return render(request, 'Inventory/staff_profile.html', context)
            
        except User.DoesNotExist:
            messages.error(request, f'User "{username}" not found.')
            return redirect('management_dashboard')
        except Exception as e:
            logger.error(f"Error loading staff profile for {username}: {e}", exc_info=True)
            messages.error(request, 'An error occurred while loading the staff profile.')
            return redirect('management_dashboard')


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


class SiteReceiptListView(LoginRequiredMixin, SuperuserOnlyMixin, ListView):
    """
    View for consultants to see their logged site receipts
    """
    model = SiteReceipt
    template_name = 'Inventory/site_receipts.html'
    context_object_name = 'receipts'
    paginate_by = 20
    
    def get_queryset(self):
        # Superusers see all receipts (others 404 via mixin)
        return SiteReceipt.objects.all().select_related('material_transport', 'received_by').order_by('-received_date')



class MaterialOrdersOfficersView(LoginRequiredMixin, ListView):
    """
    View for displaying material orders with proper fulfillment workflow.
    - All authenticated users can see all orders for transparency and collaboration
    """
    template_name = 'Inventory/material_orders_offcicers.html'
    context_object_name = 'orders'
    paginate_by = 50

    def get_queryset(self):
        user = self.request.user
        logger = logging.getLogger(__name__)
        
        try:
            # Base queryset with proper ordering and select_related for performance
            # Show all orders to all authenticated users for transparency
            queryset = MaterialOrder.objects.select_related('user', 'unit', 'category').order_by('-date_requested')
            
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

class DownloadSampleTemplateView(LoginRequiredMixin, View):
    """View to download sample inventory template"""
    
    def get(self, request):
        # Sample data for the template
        sample_data = {
            'name': [
                'Portland Cement',
                'Steel Reinforcement Bars',
                'Sand',
                'Gravel',
                'Timber Planks'
            ],
            'quantity': [
                1000,
                500,
                2000,
                1500,
                800
            ],
            'category': [
                'Construction Materials',
                'Steel Products',
                'Aggregates',
                'Aggregates',
                'Timber Products'
            ],
            'code': [
                'CEM-001',
                'STEEL-001',
                'SAND-001',
                'GRAVEL-001',
                'TIMBER-001'
            ],
            'unit': [
                'Bags',
                'Tons',
                'Cubic Meters',
                'Cubic Meters',
                'Pieces'
            ],
            'warehouse': [
                'Main Warehouse',
                'Main Warehouse',
                'Northern Regional Warehouse',
                'Western Regional Warehouse',
                'Eastern Regional Warehouse'
            ]
        }
        
        # Create DataFrame
        df = pd.DataFrame(sample_data)
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Inventory Template')
        
        output.seek(0)
        
        # Create HTTP response
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="sample_inventory_template.xlsx"'
        
        return response