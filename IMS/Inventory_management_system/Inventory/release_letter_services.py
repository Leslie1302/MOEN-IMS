"""
Release Letter Tracking Services

Business logic for validating and calculating release letter tracking metrics.
Separates business rules from model layer for cleaner architecture.
"""

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db.models import Sum, F, Q
import logging

logger = logging.getLogger(__name__)



def link_orders_to_release_letter(release_letter):
    """
    Find matching MaterialOrders by request_code and link them to this ReleaseLetter.
    """
    if not release_letter.request_code:
        return 0
        
    from .models import MaterialOrder
    from django.db.models import Q
    
    # Match exact code OR code with suffix (e.g., REQ-123 and REQ-123-1)
    # We filter by prefix + separator to ensure we don't match partial numbers (e.g. REQ-1 vs REQ-10)
    prefix_query = Q(request_code=release_letter.request_code) | \
                   Q(request_code__startswith=f"{release_letter.request_code}-")
                   
    orders = MaterialOrder.objects.filter(prefix_query)
    count = orders.update(release_letter=release_letter)
    return count



def link_order_to_release_letter(material_order):
    """
    Find matching ReleaseLetter by request_code and link this order to it.
    Handles suffixes by checking base codes.
    """
    code = material_order.request_code
    if not code:
        return False
        
    from .models import ReleaseLetter
    
    # Try exact match first
    rl = ReleaseLetter.objects.filter(request_code=code).order_by('-upload_time').first()
    
    # If not found, try stripping suffixes (e.g. REQ-123-1 -> REQ-123)
    # We loop to handle nested suffixes if any, but usually just one level
    while not rl and '-' in code:
        # Strip last segment
        parts = code.rsplit('-', 1)
        if len(parts) < 2:
            break
        code = parts[0]
        # Basic sanity check to avoid matching "REQ" or "REQ-2025"
        if len(code) < 10: # arbitrary safety length
            break
            
        rl = ReleaseLetter.objects.filter(request_code=code).order_by('-upload_time').first()
    
    if rl:
        material_order.release_letter = rl
        material_order.save(update_fields=['release_letter'])
        return True
    return False



def validate_material_request_against_release_letter(material_order, release_letter=None):
    """
    Validate that a MaterialOrder's quantity doesn't exceed the remaining
    balance of its linked ReleaseLetter.
    
    Args:
        material_order: The MaterialOrder instance being validated
        release_letter: Optional ReleaseLetter instance (uses material_order.release_letter if not provided)
    
    Raises:
        ValidationError: If requested quantity exceeds remaining balance
    
    Returns:
        bool: True if validation passes
    """
    # Get the release letter from the material order if not provided
    rl = release_letter or getattr(material_order, 'release_letter', None)
    
    if not rl:
        # No release letter linked, skip validation
        return True
    
    # Calculate the balance excluding the current order (for updates)
    from .models import MaterialOrder
    
    existing_total = Decimal('0')
    if rl.pk:
        orders_query = MaterialOrder.objects.filter(release_letter=rl)
        
        # Exclude current order if it's an update
        if material_order.pk:
            orders_query = orders_query.exclude(pk=material_order.pk)
        
        result = orders_query.aggregate(total=Sum('quantity'))['total']
        existing_total = Decimal(str(result)) if result else Decimal('0')
    
    # Calculate remaining balance
    total_authorized = Decimal(str(rl.total_quantity)) if rl.total_quantity else Decimal('0')
    requested_qty = Decimal(str(material_order.quantity)) if material_order.quantity else Decimal('0')
    
    new_total = existing_total + requested_qty
    remaining_balance = total_authorized - existing_total
    
    if new_total > total_authorized:
        raise ValidationError(
            f"Requested quantity ({requested_qty}) exceeds the remaining balance "
            f"({remaining_balance}) of Release Letter {rl.reference_number or rl.pk}. "
            f"Total authorized: {total_authorized}, Already requested: {existing_total}."
        )
    
    return True


def validate_boq_allocation(release_letter):
    """
    Validate that the total quantity of all Release Letters for a specific 
    BOQ item doesn't exceed the BOQ's contract_quantity.
    
    Args:
        release_letter: The ReleaseLetter instance being validated
    
    Raises:
        ValidationError: If total exceeds BOQ allocation
    
    Returns:
        bool: True if validation passes
    """
    boq = getattr(release_letter, 'boq_item', None)
    
    if not boq:
        # No BOQ linked, skip validation
        return True
    
    from .models import ReleaseLetter
    
    # Get total of all release letters linked to this BOQ
    other_letters_query = ReleaseLetter.objects.filter(boq_item=boq)
    
    # Exclude current release letter if it's an update
    if release_letter.pk:
        other_letters_query = other_letters_query.exclude(pk=release_letter.pk)
    
    result = other_letters_query.aggregate(total=Sum('total_quantity'))['total']
    existing_total = Decimal(str(result)) if result else Decimal('0')
    
    # Calculate new total
    current_qty = Decimal(str(release_letter.total_quantity)) if release_letter.total_quantity else Decimal('0')
    new_total = existing_total + current_qty
    
    # Get BOQ contract quantity
    boq_allocation = Decimal(str(boq.contract_quantity)) if boq.contract_quantity else Decimal('0')
    
    if new_total > boq_allocation:
        remaining = boq_allocation - existing_total
        raise ValidationError(
            f"Total Release Letter quantity ({new_total}) exceeds BOQ allocation ({boq_allocation}) "
            f"for {boq.material_description}. Remaining available: {remaining}."
        )
    
    return True


def get_release_letter_summary(release_letter):
    """
    Get a comprehensive summary of a release letter's tracking metrics.
    
    Args:
        release_letter: The ReleaseLetter instance
    
    Returns:
        dict: Dictionary containing all tracking metrics
    """
    return {
        'reference_number': release_letter.reference_number,
        'title': release_letter.title,
        'material_type': release_letter.material_type,
        'project_phase': release_letter.project_phase,
        'status': release_letter.status,
        
        # Quantities
        'total_authorized': release_letter.total_quantity,
        'total_requested': release_letter.total_requested,
        'total_released': release_letter.total_released,
        'balance_to_request': release_letter.balance_to_request,
        'fulfillment_gap': release_letter.fulfillment_gap,
        
        # Percentages
        'drawdown_percentage': round(float(release_letter.drawdown_percentage), 1),
        'fulfillment_percentage': round(float(release_letter.fulfillment_percentage), 1),
        'alert_threshold': release_letter.alert_threshold_percentage,
        
        # Status flags
        'is_threshold_exceeded': release_letter.is_threshold_exceeded,
        'status_color': release_letter.tracking_status_color,
        
        # Related counts
        'order_count': release_letter.material_orders.count(),
        'transport_count': release_letter.transports.count(),
        'delivered_count': release_letter.transports.filter(status='Delivered').count(),
    }


def get_all_release_letter_stats(filters=None):
    """
    Get tracking statistics for all release letters with optional filtering.
    
    Args:
        filters: Optional dict of filters (e.g., {'status': 'Open', 'material_type': 'Poles'})
    
    Returns:
        list: List of dictionaries with tracking metrics for each release letter
    """
    from .models import ReleaseLetter
    
    queryset = ReleaseLetter.objects.select_related('boq_item', 'uploaded_by')
    
    if filters:
        if 'status' in filters:
            queryset = queryset.filter(status=filters['status'])
        if 'material_type' in filters:
            queryset = queryset.filter(material_type=filters['material_type'])
        if 'project_phase' in filters:
            queryset = queryset.filter(project_phase__icontains=filters['project_phase'])
    
    results = []
    for rl in queryset:
        results.append(get_release_letter_summary(rl))
    
    return results


def check_and_create_threshold_alert(release_letter, notify=True):
    """
    Check if a release letter has exceeded its threshold and create notification if needed.
    
    Args:
        release_letter: The ReleaseLetter instance to check
        notify: Whether to create a notification (default True)
    
    Returns:
        bool: True if threshold was exceeded, False otherwise
    """
    if not release_letter.is_threshold_exceeded:
        return False
    
    if notify:
        try:
            from .models import Notification
            
            # Check if we've already sent an alert for this release letter
            existing_alert = Notification.objects.filter(
                notification_type='release_letter_threshold',
                title__contains=release_letter.reference_number or str(release_letter.pk)
            ).exists()
            
            if not existing_alert:
                drawdown_pct = round(float(release_letter.drawdown_percentage), 1)
                Notification.objects.create(
                    notification_type='staff_prompt',  # Using existing type
                    title=f'Release Letter Threshold Alert: {release_letter.reference_number}',
                    message=(
                        f"Release Letter '{release_letter.title}' ({release_letter.reference_number}) "
                        f"has reached {drawdown_pct}% drawdown, exceeding the {release_letter.alert_threshold_percentage}% threshold. "
                        f"Material Type: {release_letter.material_type}. "
                        f"Remaining balance: {release_letter.balance_to_request}."
                    ),
                    recipient_group='Management',
                    sender=None
                )
                logger.info(f"Created threshold alert for Release Letter {release_letter.reference_number}")
        except Exception as e:
            logger.error(f"Error creating threshold alert: {str(e)}", exc_info=True)
    
    return True


def close_release_letter_if_depleted(release_letter, save=True):
    """
    Automatically close a release letter if it's fully drawn down.
    
    Args:
        release_letter: The ReleaseLetter instance
        save: Whether to save changes (default True)
    
    Returns:
        bool: True if closed, False otherwise
    """
    if release_letter.balance_to_request <= 0 and release_letter.status == 'Open':
        release_letter.status = 'Closed'
        if save:
            release_letter.save(update_fields=['status'])
            logger.info(f"Auto-closed Release Letter {release_letter.reference_number} - fully drawn down")
        return True
    return False
