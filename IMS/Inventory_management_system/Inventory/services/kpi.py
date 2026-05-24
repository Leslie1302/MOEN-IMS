"""
KPI Service Module — Performance metrics calculation by role

Provides functions to compute key performance indicators for different user roles:
- Store Officers: Stock management & order fulfillment
- Schedule Officers: Transport & delivery coordination
- Management: Oversight & compliance metrics
- Consultants: Site delivery & receipt logging
"""

from django.db.models import Count, Q, F, Avg, ExpressionWrapper, DurationField, Sum
from django.utils import timezone
from datetime import timedelta
from Inventory.models import (
    MaterialOrder, MaterialTransport, SiteReceipt,
    BillOfQuantity, InventoryItem
)


def get_store_officer_kpis(user):
    """
    Calculate KPIs for Store Officers
    Metrics: Orders processed, average processing time, fulfillment rate
    """
    now = timezone.now()
    last_30_days = now - timedelta(days=30)

    # Get orders assigned to or created by this user in last 30 days
    orders = MaterialOrder.objects.filter(
        Q(user=user) | Q(assigned_to=user),
        created_at__gte=last_30_days
    )

    total_orders = orders.count()
    completed_orders = orders.filter(status='Completed').count()
    pending_orders = orders.filter(status__in=['Pending', 'In Progress']).count()

    # Calculate average processing time for completed orders
    completed = orders.filter(status='Completed').annotate(
        processing_time=ExpressionWrapper(
            F('updated_at') - F('created_at'),
            output_field=DurationField()
        )
    )

    avg_processing_time = 0
    if completed.exists():
        avg_duration = completed.aggregate(
            avg_time=Avg('processing_time')
        )['avg_time']
        if avg_duration:
            avg_processing_time = int(avg_duration.total_seconds() / 3600)  # Convert to hours

    # Calculate fulfillment rate
    fulfillment_rate = 0
    if total_orders > 0:
        fulfillment_rate = int((completed_orders / total_orders) * 100)

    # Get items released by this user
    items_released = orders.aggregate(
        total_qty=Sum('quantity')
    )['total_qty'] or 0

    return {
        'role': 'Store Officer',
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'pending_orders': pending_orders,
        'fulfillment_rate': fulfillment_rate,
        'avg_processing_hours': avg_processing_time,
        'items_released': float(items_released),
        'status': 'Good' if fulfillment_rate >= 80 else ('Fair' if fulfillment_rate >= 50 else 'Needs Improvement'),
    }


def get_schedule_officer_kpis(user):
    """
    Calculate KPIs for Schedule Officers
    Metrics: Transport assignments, delivery rate, on-time performance
    """
    now = timezone.now()
    last_30_days = now - timedelta(days=30)

    # Get transports assigned by this user in last 30 days
    transports = MaterialTransport.objects.filter(
        assigned_by=user,
        date_dispatched__gte=last_30_days
    )

    total_assignments = transports.count()
    delivered = transports.filter(status='Delivered').count()
    in_transit = transports.filter(status='In Transit').count()
    pending = transports.filter(status='Pending').count()

    # Calculate on-time delivery rate (by comparing delivery date with expected)
    on_time = transports.filter(
        status='Delivered',
        date_delivered__lte=F('expected_delivery_date')
    ).count()

    on_time_rate = 0
    if delivered > 0:
        on_time_rate = int((on_time / delivered) * 100)

    delivery_rate = 0
    if total_assignments > 0:
        delivery_rate = int((delivered / total_assignments) * 100)

    return {
        'role': 'Schedule Officer',
        'total_assignments': total_assignments,
        'delivered': delivered,
        'in_transit': in_transit,
        'pending': pending,
        'delivery_rate': delivery_rate,
        'on_time_rate': on_time_rate,
        'status': 'Good' if on_time_rate >= 80 else ('Fair' if on_time_rate >= 60 else 'Needs Improvement'),
    }


def get_management_kpis(user=None):
    """
    Calculate KPIs for Management
    Metrics: Overall order processing, budget utilization, compliance
    """
    now = timezone.now()
    last_30_days = now - timedelta(days=30)

    # Overall metrics (not user-specific)
    total_orders = MaterialOrder.objects.filter(
        created_at__gte=last_30_days
    ).count()

    completed_orders = MaterialOrder.objects.filter(
        status='Completed',
        created_at__gte=last_30_days
    ).count()

    pending_approvals = MaterialOrder.objects.filter(
        status='Pending',
        created_at__gte=last_30_days
    ).count()

    # Calculate average order cycle time
    completed = MaterialOrder.objects.filter(
        status='Completed',
        created_at__gte=last_30_days
    ).annotate(
        cycle_time=ExpressionWrapper(
            F('updated_at') - F('created_at'),
            output_field=DurationField()
        )
    )

    avg_cycle_time = 0
    if completed.exists():
        avg_duration = completed.aggregate(
            avg_time=Avg('cycle_time')
        )['avg_time']
        if avg_duration:
            avg_cycle_time = int(avg_duration.total_seconds() / 3600)  # Convert to hours

    # Calculate budget utilization
    total_budget = BillOfQuantity.objects.aggregate(
        total=Sum('contract_quantity')
    )['total'] or 0

    total_received = BillOfQuantity.objects.aggregate(
        total=Sum('quantity_received')
    )['total'] or 0

    budget_utilization = 0
    if total_budget > 0:
        budget_utilization = int((total_received / total_budget) * 100)

    # Count transports with delays
    delayed_transports = MaterialTransport.objects.filter(
        status='In Transit',
        expected_delivery_date__lt=now,
        date_dispatched__gte=last_30_days
    ).count()

    return {
        'role': 'Management',
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'pending_approvals': pending_approvals,
        'completion_rate': int((completed_orders / total_orders * 100) if total_orders > 0 else 0),
        'avg_cycle_hours': avg_cycle_time,
        'budget_utilization': budget_utilization,
        'delayed_transports': delayed_transports,
        'status': 'Good' if budget_utilization >= 80 else ('Fair' if budget_utilization >= 50 else 'Needs Attention'),
    }


def get_consultant_kpis(user):
    """
    Calculate KPIs for Project Consultants
    Metrics: Site receipts logged, delivery confirmations, receipt accuracy
    """
    now = timezone.now()
    last_30_days = now - timedelta(days=30)

    # Get site receipts logged by this user in last 30 days
    receipts = SiteReceipt.objects.filter(
        received_by=user,
        received_date__gte=last_30_days
    )

    total_receipts = receipts.count()
    total_quantity_received = receipts.aggregate(
        total=Sum('received_quantity')
    )['total'] or 0

    # Get condition breakdown
    good_condition = receipts.filter(condition='Good').count()
    damaged = receipts.filter(condition='Damaged').count()
    partial = receipts.filter(condition='Partial').count()

    # Calculate quality rate (non-damaged rate)
    quality_rate = 0
    if total_receipts > 0:
        quality_rate = int(((good_condition) / total_receipts) * 100)

    # Get linked transports
    related_transports = MaterialTransport.objects.filter(
        site_receipts__received_by=user,
        date_dispatched__gte=last_30_days
    ).distinct().count()

    return {
        'role': 'Consultant',
        'total_receipts': total_receipts,
        'total_quantity_received': float(total_quantity_received),
        'good_condition': good_condition,
        'damaged': damaged,
        'partial_delivery': partial,
        'quality_rate': quality_rate,
        'related_deliveries': related_transports,
        'status': 'Good' if quality_rate >= 90 else ('Fair' if quality_rate >= 70 else 'Needs Improvement'),
    }


def get_user_performance_summary(user):
    """
    Get overall performance summary for a user based on their groups/roles
    """
    kpis = {}
    groups = user.groups.values_list('name', flat=True)

    if 'Store Officers' in groups:
        kpis['store_officer'] = get_store_officer_kpis(user)

    if 'Schedule Officers' in groups:
        kpis['schedule_officer'] = get_schedule_officer_kpis(user)

    if 'Management' in groups:
        kpis['management'] = get_management_kpis(user)

    # Consultants group (ProjectConsultant role)
    if 'Consultants' in groups or user.is_superuser:
        kpis['consultant'] = get_consultant_kpis(user)

    return kpis


def get_management_dashboard_summary():
    """
    Get top-level KPIs for the management dashboard
    Shows aggregate metrics across all users and operations
    """
    now = timezone.now()
    last_30_days = now - timedelta(days=30)

    # Summary counts
    total_orders = MaterialOrder.objects.filter(
        created_at__gte=last_30_days
    ).count()

    completed_orders = MaterialOrder.objects.filter(
        status='Completed',
        created_at__gte=last_30_days
    ).count()

    total_deliveries = MaterialTransport.objects.filter(
        date_dispatched__gte=last_30_days
    ).count()

    delivered = MaterialTransport.objects.filter(
        status='Delivered',
        date_delivered__gte=last_30_days
    ).count()

    # Get top performing users by orders completed
    top_store_officers = MaterialOrder.objects.filter(
        status='Completed',
        created_at__gte=last_30_days,
        user__groups__name='Store Officers'
    ).values('user__username', 'user__first_name', 'user__last_name').annotate(
        completed=Count('id')
    ).order_by('-completed')[:5]

    # Get top performing transporters by deliveries
    top_transporters = MaterialTransport.objects.filter(
        status='Delivered',
        date_delivered__gte=last_30_days
    ).values('transporter__name').annotate(
        delivered=Count('id')
    ).order_by('-delivered')[:5]

    return {
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'order_completion_rate': int((completed_orders / total_orders * 100) if total_orders > 0 else 0),
        'total_deliveries': total_deliveries,
        'delivered': delivered,
        'delivery_rate': int((delivered / total_deliveries * 100) if total_deliveries > 0 else 0),
        'top_store_officers': list(top_store_officers),
        'top_transporters': list(top_transporters),
        'period': 'Last 30 days',
    }
