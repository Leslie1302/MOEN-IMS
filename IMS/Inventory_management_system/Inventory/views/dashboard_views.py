import logging
import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Sum, Avg, Count, Q, F, Prefetch
from django.urls import reverse
from django.utils import timezone

from Inventory.models import (
    MaterialOrder, Profile, MaterialTransport, BillOfQuantity, 
    ReleaseLetter, SiteReceipt, InventoryItem, MaterialOrderAudit
)
# Try to import AuditLog, but handle if it doesn't exist or is in a different app
try:
    from audit_log.models import AuditLog
except ImportError:
    AuditLog = None

# Configure logger
logger = logging.getLogger(__name__)

def consultant_dash(request):
    orders = MaterialOrder.objects.all().order_by('-date_requested')
    profile, created = Profile.objects.get_or_create(user=request.user)  # Ensure profile exists
    context = {
        'orders': orders,
        'profile': profile  # Pass profile to the context
    }
    return render(request, 'Inventory/receive_material.html', context)

@login_required
def management_dashboard(request):
    logger = logging.getLogger(__name__)
    logger.info("Entering management_dashboard view")
    
    try:
        # Check if user is in Management group or is superuser
        if not (request.user.groups.filter(name='Management').exists() or request.user.is_superuser):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('dashboard')
            
        # Initialize context with default values
        context = {
            'total_orders': 0,
            'total_received_by_consultants': 0,
            'total_received_by_store_officers': 0,
            'total_released_by_store_officers': 0,
            'total_on_site': 0,
            'pending_orders': 0,
            'orders': [],
            'audit_trail': [],
            'notifications': [],
            'user_grades': {},
            'low_inventory_count': 0,
            'profile': None,
            # New metrics with defaults
            'transport_in_transit': 0,
            'transport_pending': 0,
            'transport_completed_today': 0,
            'boq_total_entries': 0,
            'boq_active_projects': 0,
            'boq_packages': 0,
            'active_users': 0,
            'today_activities': 0,
        }
        
        # Get or create user profile
        try:
            profile, created = Profile.objects.get_or_create(user=request.user)
            context['profile'] = profile
        except Exception as e:
            logger.error(f"Error getting user profile: {str(e)}", exc_info=True)
        
        # Calculate comprehensive user performance grades
        try:
            users = User.objects.prefetch_related('groups').all()
            user_grades = {}
            
            user_count = users.count()
            logger.info(f"Calculating comprehensive grades for {user_count} users")
            
            if user_count == 0:
                logger.warning("No users found in the system!")
            
            for user in users:
                try:
                    # Initialize metrics
                    total_tasks = 0
                    completed_tasks = 0
                    avg_completion_days = 0
                    role_name = ", ".join([g.name for g in user.groups.all()]) or "No Role"
                    
                    # Get user's primary role
                    user_groups = [g.name for g in user.groups.all()]
                    
                    # Schedule Officers - Material requests they created
                    # Completed = Site receipt logged for the order
                    if 'Schedule Officers' in user_groups or not user_groups:
                        requests_created = MaterialOrder.objects.filter(user=user)
                        total_tasks += requests_created.count()
                        
                        # Count completed tasks: orders with site receipts
                        completed_requests = requests_created.filter(
                            site_receipt__isnull=False
                        ).distinct()
                        completed_tasks += completed_requests.count()
                        
                        # Calculate avg days to completion (request to site receipt)
                        if completed_requests.exists():
                            total_days = 0
                            count_with_dates = 0
                            for order in completed_requests:
                                if order.date_requested:
                                    # Get the site receipt for this order
                                    receipt = SiteReceipt.objects.filter(material_order=order).order_by('-receipt_date').first()
                                    if receipt and receipt.receipt_date:
                                        days = (receipt.receipt_date - order.date_requested).days
                                        total_days += days
                                        count_with_dates += 1
                            
                            if count_with_dates > 0:
                                avg_completion_days = total_days / count_with_dates
                    
                    # Store Officers - Materials they processed
                    # Completed = When transport status is "In Transit"
                    if 'Store Officers' in user_groups:
                        processed_orders = MaterialOrder.objects.filter(last_updated_by=user)
                        total_tasks += processed_orders.count()
                        
                        # Count completed: orders with transport in "In Transit" status
                        completed_store_officer_orders = processed_orders.filter(
                            materialtransport__status='In Transit'
                        ).distinct()
                        completed_tasks += completed_store_officer_orders.count()
                        
                        # Calculate processing efficiency (request to in transit)
                        if completed_store_officer_orders.exists():
                            total_days = 0
                            count_with_dates = 0
                            for order in completed_store_officer_orders:
                                if order.date_requested:
                                    # Get the transport for this order
                                    transport = MaterialTransport.objects.filter(
                                        material_order=order,
                                        status='In Transit'
                                    ).order_by('date_dispatched').first()
                                    if transport and transport.date_dispatched:
                                        days = (transport.date_dispatched.date() - order.date_requested).days
                                        total_days += days
                                        count_with_dates += 1
                            
                            if count_with_dates > 0:
                                avg_completion_days = total_days / count_with_dates
                    
                    # Transporters - Deliveries they were assigned
                    # Completed = Status is "Delivered" AND site receipt is logged
                    if 'Transporters' in user_groups:
                        transports = MaterialTransport.objects.filter(transporter_name=user.username)
                        total_tasks += transports.count()
                        
                        # Count completed: delivered with site receipt
                        completed_transports = transports.filter(
                            status='Delivered',
                            site_receipt__isnull=False
                        ).distinct()
                        completed_tasks += completed_transports.count()
                        
                        # Calculate delivery efficiency (assignment to site receipt)
                        if completed_transports.exists():
                            total_days = 0
                            count_with_dates = 0
                            for transport in completed_transports:
                                if transport.date_dispatched:
                                    # Get the site receipt for this transport
                                    receipt = SiteReceipt.objects.filter(
                                        material_transport=transport
                                    ).order_by('-receipt_date').first()
                                    if receipt and receipt.receipt_date:
                                        days = (receipt.receipt_date - transport.date_dispatched.date()).days
                                        total_days += days
                                        count_with_dates += 1
                            
                            if count_with_dates > 0:
                                avg_completion_days = total_days / count_with_dates
                    
                    # Consultants - Site receipts they logged
                    if 'Consultants' in user_groups:
                        site_receipts = SiteReceipt.objects.filter(received_by=user.username)
                        total_tasks += site_receipts.count()
                        completed_tasks += site_receipts.filter(receipt_status='Received').count()
                        
                        # All logged receipts count as timely work
                        if site_receipts.exists():
                            avg_completion_days = 1  # Same-day logging is ideal
                    
                    # Management - Oversight and approvals
                    if 'Management' in user_groups:
                        # Count orders they've reviewed/updated
                        managed_orders = MaterialOrder.objects.filter(last_updated_by=user)
                        total_tasks += managed_orders.count()
                        completed_tasks += managed_orders.filter(
                            status__in=['Approved', 'Completed']
                        ).count()
                    
                    # Calculate overall performance score
                    # 1. Completion Rate (40%)
                    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
                    completion_score = (completion_rate / 100) * 40
                    
                    # 2. Efficiency/Timeliness (30%) - lower days is better
                    # Scoring: <2 days = 30pts, 2-5 days = 20pts, 5-10 days = 10pts, >10 days = 0pts
                    if avg_completion_days == 0:
                        efficiency_score = 15  # Neutral score if no data
                    elif avg_completion_days < 2:
                        efficiency_score = 30
                    elif avg_completion_days < 5:
                        efficiency_score = 20
                    elif avg_completion_days < 10:
                        efficiency_score = 10
                    else:
                        efficiency_score = 0
                    
                    # 3. Volume/Productivity (30%)
                    # Scoring: >50 tasks = 30pts, 30-50 = 25pts, 10-30 = 15pts, <10 = 5pts
                    if completed_tasks >= 50:
                        volume_score = 30
                    elif completed_tasks >= 30:
                        volume_score = 25
                    elif completed_tasks >= 10:
                        volume_score = 15
                    elif completed_tasks > 0:
                        volume_score = 5
                    else:
                        volume_score = 0
                    
                    # Total performance score (out of 100)
                    performance_score = completion_score + efficiency_score + volume_score
                    
                    # Assign grade letter based on performance score
                    if performance_score >= 90:
                        grade_letter = 'A+'
                        grade_color = 'success'
                    elif performance_score >= 85:
                        grade_letter = 'A'
                        grade_color = 'success'
                    elif performance_score >= 80:
                        grade_letter = 'B+'
                        grade_color = 'info'
                    elif performance_score >= 75:
                        grade_letter = 'B'
                        grade_color = 'info'
                    elif performance_score >= 70:
                        grade_letter = 'C+'
                        grade_color = 'warning'
                    elif performance_score >= 65:
                        grade_letter = 'C'
                        grade_color = 'warning'
                    elif performance_score >= 60:
                        grade_letter = 'D'
                        grade_color = 'danger'
                    elif total_tasks > 0:
                        grade_letter = 'F'
                        grade_color = 'danger'
                    else:
                        grade_letter = 'N/A'
                        grade_color = 'secondary'
                        performance_score = 0
                    
                    user_grades[user.id] = {
                        'username': user.username,
                        'groups': role_name,
                        'grade': performance_score,
                        'grade_letter': grade_letter,
                        'grade_color': grade_color,
                        'total_tasks': total_tasks,
                        'completed_tasks': completed_tasks,
                        'completion_rate': completion_rate,
                        'avg_completion_days': round(avg_completion_days, 1),
                        'efficiency_score': efficiency_score,
                        'volume_score': volume_score,
                    }
                    logger.info(f"✓ User {user.username}: Grade={grade_letter}, Score={performance_score:.1f}, Tasks={completed_tasks}/{total_tasks}, Efficiency={avg_completion_days:.1f} days")
                except Exception as e:
                    logger.error(f"✗ Error calculating grade for user {user.username}: {str(e)}", exc_info=True)
                    # Still add user with default values - ALWAYS show users
                    try:
                        role_name = ", ".join([g.name for g in user.groups.all()]) or "No Role"
                    except:
                        role_name = "No Role"
                    
                    user_grades[user.id] = {
                        'username': user.username,
                        'groups': role_name,
                        'grade': 0,
                        'grade_letter': 'N/A',
                        'grade_color': 'secondary',
                        'total_tasks': 0,
                        'completed_tasks': 0,
                        'completion_rate': 0,
                        'avg_completion_days': 0,
                        'efficiency_score': 0,
                        'volume_score': 0,
                    }
                    logger.info(f"✓ User {user.username}: Added with default values (error occurred)")
            
            # Sort users by performance score for "Worker of the Month"
            sorted_grades = sorted(
                user_grades.items(), 
                key=lambda x: x[1]['grade'], 
                reverse=True
            )
            
            # Mark top performer as "Worker of the Month"
            if sorted_grades and sorted_grades[0][1]['grade'] > 0:
                sorted_grades[0][1]['worker_of_month'] = True
                logger.info(f"🏆 Worker of the Month: {sorted_grades[0][1]['username']} (Score: {sorted_grades[0][1]['grade']:.1f})")
            
            context['user_grades'] = dict(sorted_grades)
            logger.info(f"✓ Successfully calculated grades for {len(user_grades)} users. Top score: {sorted_grades[0][1]['grade']:.1f if sorted_grades else 0}")
            
        except Exception as e:
            logger.error(f"✗ CRITICAL: Error calculating user grades: {str(e)}", exc_info=True)
            # Last resort - ensure ALL users are shown even if calculation completely fails
            try:
                users = User.objects.all()
                user_grades = {}
                for user in users:
                    try:
                        role_name = ", ".join([g.name for g in user.groups.all()]) or "No Role"
                    except:
                        role_name = "No Role"
                    
                    user_grades[user.id] = {
                        'username': user.username,
                        'groups': role_name,
                        'grade': 0,
                        'grade_letter': 'N/A',
                        'grade_color': 'secondary',
                        'total_tasks': 0,
                        'completed_tasks': 0,
                        'completion_rate': 0,
                        'avg_completion_days': 0,
                        'efficiency_score': 0,
                        'volume_score': 0,
                    }
                context['user_grades'] = user_grades
                logger.warning(f"⚠ Using fallback: Added {len(user_grades)} users with default values")
            except Exception as fallback_error:
                logger.critical(f"✗ FALLBACK FAILED: {str(fallback_error)}", exc_info=True)
                context['user_grades'] = {}
        
        # Get order statistics with error handling
        try:
            context['total_orders'] = MaterialOrder.objects.count()
            
            # Received by Consultants
            received_by_consultants = MaterialOrder.objects.filter(
                status='Received', 
                user__groups__name='Consultants'
            )
            context['total_received_by_consultants'] = received_by_consultants.aggregate(
                total=Sum('processed_quantity')
            )['total'] or 0
            
            # Received by Store Officers
            received_by_store_officers = MaterialOrder.objects.filter(
                user__groups__name='Store Officers'
            )
            # Check if unit_price field exists, otherwise default to 0
            # Assuming quantity * unit_price is desired, but checking if models support it
            # To be safe, we'll wrap in try-except for field access
            try:
                context['total_received_by_store_officers'] = received_by_store_officers.aggregate(
                    total=Sum(F('quantity') * F('unit_price'), output_field=F('quantity').output_field)
                )['total'] or 0
            except:
                context['total_received_by_store_officers'] = 0

            # Released by Store Officers
            released_by_store_officers = MaterialOrder.objects.filter(
                user__groups__name='Store Officers'
            )
            try:
                context['total_released_by_store_officers'] = released_by_store_officers.aggregate(
                    total=Sum(F('quantity') * F('unit_price'), output_field=F('quantity').output_field)
                )['total'] or 0
            except:
                context['total_released_by_store_officers'] = 0
            
            # Other metrics
            context['total_on_site'] = MaterialOrder.objects.filter(status='On Site').count()
            context['pending_orders'] = MaterialOrder.objects.filter(status='Pending').count()
            
            # Get recent orders and audit trail
            context['orders'] = MaterialOrder.objects.all().order_by('-date_requested')[:10]
            context['audit_trail'] = MaterialOrderAudit.objects.all().order_by('-date')[:10]
            
        except Exception as e:
            logger.error(f"Error fetching order statistics: {str(e)}", exc_info=True)
            messages.error(request, 'Error loading dashboard statistics. Please try again.')
        
        # Get low inventory count
        try:
            low_inventory = InventoryItem.objects.filter(quantity__lt=10)
            context['low_inventory_count'] = low_inventory.count()
            
            # Add low inventory notification if needed
            if low_inventory.exists():
                context['notifications'].append({
                    'type': 'warning',
                    'message': f'{low_inventory.count()} items are below reorder level',
                    'url': reverse('low_inventory_summary')
                })
            
            # Add pending orders notification if needed
            if context['pending_orders'] > 0:
                context['notifications'].append({
                    'type': 'info',
                    'message': f"{context['pending_orders']} pending material orders",
                    'url': reverse('material_orders')
                })
            
        except Exception as e:
            logger.error(f"Error fetching inventory data: {str(e)}", exc_info=True)
        
        # Add Transport metrics
        try:
            today = datetime.now().date()
            
            context['transport_in_transit'] = MaterialTransport.objects.filter(status='In Transit').count()
            context['transport_pending'] = MaterialTransport.objects.filter(status='Pending').count()
            context['transport_completed_today'] = MaterialTransport.objects.filter(
                status='Delivered',
                date_delivered=today
            ).count()
        except Exception as e:
            logger.error(f"Error fetching transport data: {str(e)}", exc_info=True)
            context['transport_in_transit'] = 0
            context['transport_pending'] = 0
            context['transport_completed_today'] = 0
        
        # Add BOQ metrics
        try:
            context['boq_total_entries'] = BillOfQuantity.objects.count()
            context['boq_active_projects'] = BillOfQuantity.objects.values('district').distinct().count()
            context['boq_packages'] = BillOfQuantity.objects.values('package_number').distinct().count()
        except Exception as e:
            logger.error(f"Error fetching BOQ data: {str(e)}", exc_info=True)
            context['boq_total_entries'] = 0
            context['boq_active_projects'] = 0
            context['boq_packages'] = 0
        
        # Add System Health metrics
        try:
            today = datetime.now().date()
            yesterday = datetime.now() - timedelta(days=1)
            context['active_users'] = User.objects.filter(
                last_login__gte=yesterday
            ).count()
            
            if AuditLog:
                today_start = datetime.combine(today, datetime.min.time())
                today_end = datetime.combine(today, datetime.max.time())
                context['today_activities'] = AuditLog.objects.filter(
                    timestamp__range=(today_start, today_end)
                ).count()
            else:
                context['today_activities'] = 0
        except Exception as e:
            logger.error(f"Error fetching system health data: {str(e)}", exc_info=True)
            context['active_users'] = 0
            context['today_activities'] = 0
        
        logger.info("Successfully prepared dashboard context")
        return render(request, 'Inventory/management_dashboard.html', context)
            
    except Exception as e:
        logger.error(f"Unexpected error in management dashboard: {str(e)}", exc_info=True)
        messages.error(request, 'An unexpected error occurred while loading the dashboard.')
        return render(request, 'Inventory/management_dashboard.html', context)


@login_required
def release_letter_tracking_dashboard(request):
    """
    Dashboard view showing all release letters with tracking metrics.
    Displays drawdown and fulfillment status with color-coded indicators.
    """
    # Get filter parameters
    filter_status = request.GET.get('status', '')
    filter_material_type = request.GET.get('material_type', '')
    filter_threshold = request.GET.get('threshold', '')
    search_query = request.GET.get('search', '')
    
    # Base queryset
    queryset = ReleaseLetter.objects.select_related('boq_item', 'uploaded_by').prefetch_related(
        'material_orders',
        'material_orders__transports',
    )
    
    # Apply filters
    if filter_status:
        queryset = queryset.filter(status=filter_status)
    
    if filter_material_type:
        queryset = queryset.filter(material_type=filter_material_type)
    
    if search_query:
        queryset = queryset.filter(
            Q(reference_number__icontains=search_query) |
            Q(title__icontains=search_query) |
            Q(request_code__icontains=search_query)
        )
    
    # Get all release letters 
    release_letters = list(queryset.order_by('-upload_time'))
    
    # Enrich each release letter with additional tracking data
    for rl in release_letters:
        # Add order count
        rl.order_count = rl.material_orders.count()
        
        # Gather transports via material_orders → transports
        all_transports = []
        for order in rl.material_orders.all():
            all_transports.extend(order.transports.all())
        
        # Add transport status counts
        rl.delivered_count = sum(1 for t in all_transports if t.status == 'Delivered')
        rl.in_transit_count = sum(1 for t in all_transports if t.status == 'In Transit')
        
        # Attach list to object for template access
        rl.all_transports = all_transports
        
        # Calculate pending count
        total_transports = len(all_transports)
        rl.pending_count = total_transports - rl.delivered_count - rl.in_transit_count
    
    # Filter by threshold if needed
    if filter_threshold == 'exceeded':
        release_letters = [rl for rl in release_letters if rl.is_threshold_exceeded]
    elif filter_threshold == 'normal':
        release_letters = [rl for rl in release_letters if not rl.is_threshold_exceeded]
    
    # Calculate summary statistics
    total_letters = len(release_letters)
    open_letters = sum(1 for rl in release_letters if rl.status == 'Open')
    threshold_alerts = sum(1 for rl in release_letters if rl.is_threshold_exceeded)
    
    # Calculate average fulfillment
    fulfillment_values = [float(rl.fulfillment_percentage) for rl in release_letters if rl.total_quantity > 0]
    avg_fulfillment = sum(fulfillment_values) / len(fulfillment_values) if fulfillment_values else 0
    
    # Calculate material type statistics
    material_type_stats = {}
    for rl in release_letters:
        if rl.material_type not in material_type_stats:
            material_type_stats[rl.material_type] = {'count': 0, 'total_drawdown': Decimal('0')}
        material_type_stats[rl.material_type]['count'] += 1
        material_type_stats[rl.material_type]['total_drawdown'] += rl.drawdown_percentage
    
    material_stats = [
        {
            'type': mtype,
            'count': stats['count'],
            'avg_drawdown': float(stats['total_drawdown'] / stats['count']) if stats['count'] > 0 else 0
        }
        for mtype, stats in material_type_stats.items()
    ]
    material_stats.sort(key=lambda x: x['avg_drawdown'], reverse=True)
    
    context = {
        'release_letters': release_letters,
        'summary': {
            'total_letters': total_letters,
            'open_letters': open_letters,
            'threshold_alerts': threshold_alerts,
            'avg_fulfillment': avg_fulfillment,
        },
        'material_stats': material_stats,
        'material_types': ReleaseLetter.MATERIAL_TYPE_CHOICES,
        
        # Filter values for template
        'filter_status': filter_status,
        'filter_material_type': filter_material_type,
        'filter_threshold': filter_threshold,
        'search_query': search_query,
    }
    
    return render(request, 'Inventory/release_letter_tracking_dashboard.html', context)


def get_stores_phase_label(status):
    """Helper function to get stores phase label based on order status."""
    labels = {
        'Draft': '📝 Draft',
        'Pending': '⏳ Pending Approval',
        'Approved': '✅ Approved',
        'In Progress': '🔄 In Progress',
        'Partially Fulfilled': '📊 Partially Fulfilled',
        'Ready for Pickup': '📦 Ready for Pickup',
        'Rejected': '❌ Rejected',
        'Cancelled': '🚫 Cancelled',
    }
    return labels.get(status, f'📋 {status}')


@login_required
def requisition_status(request):
    """
    View for displaying requisition status with filters and summary statistics.
    Shows full material lifecycle from stores to project site delivery.
    """
    
    # Prefetch transports with site receipts for efficiency
    transports_prefetch = Prefetch(
        'transports',
        queryset=MaterialTransport.objects.select_related('transporter', 'vehicle').prefetch_related('site_receipt')
    )
    
    # Get all material orders with related data
    orders = MaterialOrder.objects.select_related(
        'user', 'unit', 'category', 'warehouse'
    ).prefetch_related(
        transports_prefetch
    ).order_by('-date_requested')
    
    # Apply filters
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    region_filter = request.GET.get('region', '')
    date_from = request.GET.get('date_from', '')
    lifecycle_filter = request.GET.get('lifecycle', '')
    
    if search_query:
        orders = orders.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(request_code__icontains=search_query)
        )
    
    if status_filter:
        orders = orders.filter(status=status_filter)
    
    if region_filter:
        orders = orders.filter(region=region_filter)
    
    if date_from:
        orders = orders.filter(date_requested__gte=date_from)
    
    # Convert to list to add computed properties
    orders_list = list(orders)
    
    # Add lifecycle stage data to each order
    for order in orders_list:
        transports = list(order.transports.all())
        
        if not transports:
            # No transports yet - still in stores phase
            order.lifecycle_stage = 'stores'
            order.lifecycle_label = get_stores_phase_label(order.status)
            order.transport_status = None
            order.has_site_receipt = False
            order.latest_transport = None
        else:
            # Has transports - check transport phase
            delivered_transports = [t for t in transports if t.status == 'Delivered']
            in_transit_transports = [t for t in transports if t.status == 'In Transit']
            loading_transports = [t for t in transports if t.status in ['Loading', 'Loaded']]
            
            # Check for site receipts
            site_confirmed = any(hasattr(t, 'site_receipt') and t.site_receipt for t in delivered_transports)
            
            # Determine latest transport for waybill download
            order.latest_transport = transports[0] if transports else None
            for t in transports:
                if t.status == 'Delivered':
                    order.latest_transport = t
                    break
            
            if site_confirmed:
                order.lifecycle_stage = 'site_confirmed'
                order.lifecycle_label = '✅ Site Confirmed'
                order.has_site_receipt = True
            elif delivered_transports:
                order.lifecycle_stage = 'delivered'
                order.lifecycle_label = '📦 Delivered to Site'
                order.has_site_receipt = False
            elif in_transit_transports:
                order.lifecycle_stage = 'in_transit'
                order.lifecycle_label = '🚚 In Transit'
                order.has_site_receipt = False
            elif loading_transports:
                order.lifecycle_stage = 'loading'
                order.lifecycle_label = '📦 Loading'
                order.has_site_receipt = False
            else:
                order.lifecycle_stage = 'transport_assigned'
                order.lifecycle_label = '🚛 Transport Assigned'
                order.has_site_receipt = False
            
            # Get latest transport status
            order.transport_status = transports[0].status if transports else None
    
    # Filter by lifecycle stage if requested
    if lifecycle_filter:
        orders_list = [o for o in orders_list if o.lifecycle_stage == lifecycle_filter]
    
    # Get statistics from MaterialOrder
    order_stats = MaterialOrder.objects.aggregate(
        pending_count=Count('id', filter=Q(status='Pending')),
        approved_count=Count('id', filter=Q(status='Approved')),
        in_progress_count=Count('id', filter=Q(status='In Progress')),
        partially_fulfilled_count=Count('id', filter=Q(status='Partially Fulfilled')),
        completed_count=Count('id', filter=Q(status='Completed')),
        rejected_count=Count('id', filter=Q(status='Rejected')),
    )
    
    # Get transport-phase statistics
    transport_stats = MaterialTransport.objects.aggregate(
        transport_in_transit_count=Count('id', filter=Q(status='In Transit')),
        transport_delivered_count=Count('id', filter=Q(status='Delivered')),
        transport_loading_count=Count('id', filter=Q(status__in=['Loading', 'Loaded'])),
    )
    
    # Count site-confirmed deliveries
    site_confirmed_count = SiteReceipt.objects.count()
    
    # Get unique regions for filter dropdown
    regions = MaterialOrder.objects.values_list('region', flat=True).distinct().order_by('region')
    regions = [r for r in regions if r]  # Filter out empty values
    
    # Lifecycle stage choices for filter dropdown
    lifecycle_choices = [
        ('stores', '📋 Stores Phase'),
        ('transport_assigned', '🚛 Transport Assigned'),
        ('loading', '📦 Loading'),
        ('in_transit', '🚚 In Transit'),
        ('delivered', '📦 Delivered to Site'),
        ('site_confirmed', '✅ Site Confirmed'),
    ]
    
    context = {
        'orders': orders_list,
        'search_query': search_query,
        'status_filter': status_filter,
        'region_filter': region_filter,
        'date_from': date_from,
        'lifecycle_filter': lifecycle_filter,
        'status_choices': MaterialOrder.STATUS_CHOICES,
        'lifecycle_choices': lifecycle_choices,
        'regions': regions,
        'site_confirmed_count': site_confirmed_count,
        **order_stats,
        **transport_stats,
    }
    
    return render(request, 'Inventory/requisition_status.html', context)
