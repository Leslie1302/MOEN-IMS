"""
Release Letter Tracking Signals

Django signals for validating release letter constraints and creating alerts.
Integrates with the existing notification system.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)


# ===== MATERIAL ORDER SIGNALS FOR RELEASE LETTER VALIDATION =====

@receiver(pre_save, sender='Inventory.MaterialOrder')
def validate_release_letter_balance(sender, instance, **kwargs):
    """
    Prevent saving a MaterialOrder if the requested quantity exceeds
    the remaining balance of the linked ReleaseLetter.

    This is the BOQ Guardrail that enforces allocation limits.
    Only applies to Release-type orders — receipts never have release letters.

    Validation is intentionally skipped on updates where neither `quantity`
    nor `release_letter_id` changed. Fulfillment processing (processed_quantity,
    remaining_quantity, status, processed_by, etc.) does not alter the
    authorised allocation, so re-running the check on every fulfillment save
    is both unnecessary and harmful — it blocks legitimate fulfillment when
    the RL's linked order set has ever been corrupted by a stale signal run.
    """
    # Only validate Release orders with a release letter linked
    if getattr(instance, 'request_type', None) != 'Release':
        return
    if not instance.release_letter_id:
        return

    # For existing orders, skip validation when neither quantity nor the RL
    # assignment changed — only quantity and RL changes affect the balance.
    if not instance._state.adding and instance.pk:
        try:
            from .models import MaterialOrder as _MO
            old = _MO.objects.filter(pk=instance.pk).values(
                'quantity', 'release_letter_id'
            ).first()
            if old and (
                old['quantity'] == instance.quantity
                and old['release_letter_id'] == instance.release_letter_id
            ):
                return  # Nothing that affects the RL balance changed
        except Exception as _e:
            logger.warning(
                f"Could not fetch prior order state for RL balance check "
                f"(order pk={instance.pk}): {_e}. Proceeding with validation."
            )

    try:
        from .release_letter_services import validate_material_request_against_release_letter
        validate_material_request_against_release_letter(instance)
    except ValidationError:
        # Re-raise to prevent save
        raise
    except Exception as e:
        # Log but don't block save for unexpected errors
        logger.error(f"Error validating release letter balance: {str(e)}", exc_info=True)


@receiver(post_save, sender='Inventory.MaterialOrder')
def check_release_letter_threshold_on_order(sender, instance, created, **kwargs):
    """
    Check if the linked release letter has exceeded its threshold after
    a MaterialOrder is saved, and create alerts if needed.
    Only applies to Release-type orders.
    """
    if getattr(instance, 'request_type', None) != 'Release':
        return
    if not instance.release_letter_id:
        return
    
    try:
        release_letter = instance.release_letter
        if release_letter:
            from .release_letter_services import check_and_create_threshold_alert, close_release_letter_if_depleted
            
            # Check threshold and create alert if needed
            check_and_create_threshold_alert(release_letter)
            
            # Auto-close if fully drawn down
            close_release_letter_if_depleted(release_letter)
            
    except Exception as e:
        logger.error(f"Error checking release letter threshold: {str(e)}", exc_info=True)


# ===== RELEASE LETTER SIGNALS FOR BOQ VALIDATION =====

@receiver(pre_save, sender='Inventory.ReleaseLetter')
def validate_release_letter_boq_allocation(sender, instance, **kwargs):
    """
    Validate that the total quantity of all Release Letters for a specific 
    BOQ item doesn't exceed the BOQ's contract_quantity.
    
    Raises ValidationError if the total exceeds allocation.
    """
    # Only validate if a BOQ item is linked and total_quantity is set
    if not instance.boq_item_id or not instance.total_quantity:
        return
    
    try:
        from .release_letter_services import validate_boq_allocation
        validate_boq_allocation(instance)
    except ValidationError:
        # Re-raise to prevent save
        raise
    except Exception as e:
        # Log but don't block save for unexpected errors
        logger.error(f"Error validating BOQ allocation: {str(e)}", exc_info=True)


@receiver(post_save, sender='Inventory.ReleaseLetter')
def notify_release_letter_created(sender, instance, created, **kwargs):
    """
    Create notification when a new release letter is created.
    """
    if not created:
        return
    
    try:
        from .models import Notification
        
        Notification.objects.create(
            notification_type='staff_prompt',
            title=f'New Release Letter Created: {instance.reference_number}',
            message=(
                f"Release Letter '{instance.title}' ({instance.reference_number}) has been created. "
                f"Total authorized: {instance.total_quantity}. "
                f"Material Type: {instance.material_type}. "
                f"Project Phase: {instance.project_phase or 'Not specified'}."
            ),
            recipient_group='Management',
            sender=instance.uploaded_by
        )
        logger.info(f"Created notification for new Release Letter {instance.reference_number}")
        
    except Exception as e:
        logger.error(f"Error creating release letter notification: {str(e)}", exc_info=True)


# ===== TRANSPORT SIGNALS FOR FULFILLMENT TRACKING =====

@receiver(post_save, sender='Inventory.MaterialTransport')
def update_release_letter_on_delivery(sender, instance, created, **kwargs):
    """
    When a transport is marked as delivered, check if this affects 
    the release letter's fulfillment metrics and create notifications.
    """
    material_order = getattr(instance, 'material_order', None)
    release_letter = getattr(material_order, 'release_letter', None) if material_order else None

    if not release_letter:
        return
    
    # Only trigger on status change to 'Delivered'
    if instance.status != 'Delivered':
        return
    
    # Check if this was a status change (not just a new record)
    if created:
        return  # Skip new records - they shouldn't be created with 'Delivered' status
    
    if not hasattr(instance, '_transport_status_changed'):
        return  # Status didn't actually change
    
    try:
        from .models import Notification
        
        # Calculate fulfillment percentage
        fulfillment_pct = round(float(release_letter.fulfillment_percentage), 1)
        
        # Create notification for significant fulfillment milestones
        milestones = [25, 50, 75, 100]
        for milestone in milestones:
            if fulfillment_pct >= milestone:
                # Check if we've already notified for this milestone
                existing = Notification.objects.filter(
                    notification_type='staff_prompt',
                    title__contains=release_letter.reference_number,
                    message__contains=f'{milestone}%'
                ).exists()
                
                if not existing:
                    Notification.objects.create(
                        notification_type='staff_prompt',
                        title=f'Release Letter Fulfillment: {release_letter.reference_number}',
                        message=(
                            f"Release Letter '{release_letter.title}' has reached {fulfillment_pct}% fulfillment. "
                            f"Total authorized: {release_letter.total_quantity}, "
                            f"Total released: {release_letter.total_released}."
                        ),
                        recipient_group='Management',
                        sender=None
                    )
                    logger.info(f"Created fulfillment notification for Release Letter {release_letter.reference_number}")
                    break  # Only create one notification per save
        
    except Exception as e:
        logger.error(f"Error updating release letter on delivery: {str(e)}", exc_info=True)


# ===== DATA LINKAGE SIGNALS =====

@receiver(post_save, sender='Inventory.ReleaseLetter')
def auto_link_orders_to_release_letter(sender, instance, created, **kwargs):
    """
    When a Release Letter is first created, automatically link any matching
    Material Orders (by request_code) that aren't already linked.

    This only runs on creation (created=True). Subsequent saves — e.g. when
    GenerateReleaseDocumentsView writes the PDFs back — must NOT re-run the
    link step, because doing so would call link_orders_to_release_letter on
    every save and risk pulling in orders that were correctly assigned to a
    sibling RL (different project_type split from the same bulk batch).
    The per-order signal (auto_link_order_to_release_letter) handles the
    reverse direction for orders created after the RL.
    """
    if not created:
        return
    if not instance.request_code:
        return

    try:
        from .release_letter_services import link_orders_to_release_letter
        count = link_orders_to_release_letter(instance)
        if count > 0:
            logger.info(f"Auto-linked {count} Material Orders to Release Letter {instance.reference_number}")
    except Exception as e:
        logger.error(f"Error linking orders to release letter: {str(e)}", exc_info=True)


@receiver(post_save, sender='Inventory.MaterialOrder')
def auto_link_order_to_release_letter(sender, instance, created, **kwargs):
    """
    When a Material Order is saved, automatically link it to a matching
    Release Letter (by request_code) if not already linked.
    Only applies to Release-type orders — receipts must never get a release letter.
    """
    # Only try to link Release orders that don't already have a letter
    if getattr(instance, 'request_type', None) != 'Release':
        return
    if instance.release_letter_id or not instance.request_code:
        return

    try:
        from .release_letter_services import link_order_to_release_letter
        linked = link_order_to_release_letter(instance)
        if linked:
            logger.info(f"Auto-linked Material Order {instance.request_code} to Release Letter")
    except Exception as e:
        logger.error(f"Error linking material order to release letter: {str(e)}", exc_info=True)
