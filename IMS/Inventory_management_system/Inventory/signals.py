"""
Signals for automatic notification creation based on system events.
Notifications are role-based - users only see notifications relevant to their group.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import Group
from django.db.models import F
from .models import (
    MaterialOrder, MaterialTransport, SiteReceipt, 
    InventoryItem, BillOfQuantity, Notification
)
import logging

logger = logging.getLogger(__name__)


def create_notification(notification_type, title, message, recipient_group, 
                       sender=None, recipient_user=None, related_order=None, 
                       related_transport=None, related_project=None):
    """
    Utility function to create notifications.
    
    Args:
        notification_type: Type of notification (from Notification.NOTIFICATION_TYPES)
        title: Notification title
        message: Detailed notification message
        recipient_group: Target group ('Storekeepers', 'Schedule Officers', 'Management', etc.)
        sender: User who triggered the action (optional)
        recipient_user: Specific user recipient (optional)
        related_order: Related MaterialOrder (optional)
        related_transport: Related MaterialTransport (optional)
        related_project: Related Project (optional)
    """
    try:
        notification = Notification.objects.create(
            notification_type=notification_type,
            title=title,
            message=message,
            recipient_group=recipient_group,
            sender=sender,
            recipient_user=recipient_user,
            related_order=related_order,
            related_transport=related_transport,
            related_project=related_project
        )
        logger.info(f"Created notification: {title} for {recipient_group}")
        return notification
    except Exception as e:
        logger.error(f"Error creating notification: {str(e)}", exc_info=True)
        return None


# ===== MATERIAL ORDER SIGNALS =====

@receiver(post_save, sender=MaterialOrder)
def handle_material_order_notifications(sender, instance, created, **kwargs):
    """
    Create notifications when material orders are created or updated.
    Different notifications go to different groups based on the action.
    """
    try:
        if created:
            # New material request - notify Storekeepers
            if instance.request_type == 'Release':
                create_notification(
                    notification_type='material_request',
                    title=f'New Release Request: {instance.name}',
                    message=f'{instance.user.username if instance.user else "Someone"} requested {instance.quantity} {instance.unit} of {instance.name}. '
                            f'Location: {instance.district}, {instance.region}. '
                            f'Request Code: {instance.request_code}',
                    recipient_group='Storekeepers',
                    sender=instance.user,
                    related_order=instance
                )
                
                # Also notify Management for visibility
                create_notification(
                    notification_type='material_request',
                    title=f'New Release Request: {instance.name}',
                    message=f'Release request from {instance.user.username if instance.user else "Unknown"} for {instance.quantity} {instance.unit} of {instance.name}. '
                            f'Request Code: {instance.request_code}',
                    recipient_group='Management',
                    sender=instance.user,
                    related_order=instance
                )
            
            elif instance.request_type == 'Receipt':
                # Material receipt notification - notify Management
                create_notification(
                    notification_type='material_request',
                    title=f'Material Receipt Logged: {instance.name}',
                    message=f'{instance.quantity} {instance.unit} of {instance.name} received from {instance.supplier.name if instance.supplier else "supplier"}. '
                            f'Warehouse: {instance.warehouse.name if instance.warehouse else "Not specified"}',
                    recipient_group='Management',
                    sender=instance.user,
                    related_order=instance
                )
        
        else:
            # Order was updated - check for processing or status changes
            try:
                # Check if processed_quantity changed (partial or full processing)
                if hasattr(instance, '_quantity_processed') and instance._quantity_processed:
                    old_qty = instance._old_processed_quantity
                    new_qty = instance.processed_quantity
                    qty_diff = new_qty - old_qty
                    
                    if qty_diff > 0:  # Only notify if quantity increased
                        # Determine if this is partial or full processing
                        is_partial = instance.remaining_quantity > 0
                        processing_type = "Partially processed" if is_partial else "Fully processed"
                        
                        # Material processed by storekeeper - notify requester
                        create_notification(
                            notification_type='material_processed',
                            title=f'Request {processing_type}: {instance.name}',
                            message=f'Your request for {instance.name} has been {processing_type.lower()}. '
                                    f'Processed: {qty_diff} {instance.unit} (Total: {instance.processed_quantity}/{instance.quantity}). '
                                    f'{"Remaining: " + str(instance.remaining_quantity) + " " + str(instance.unit) if is_partial else "Request complete!"}. '
                                    f'Request Code: {instance.request_code}',
                            recipient_group='Schedule Officers' if instance.user and instance.user.groups.filter(name='Schedule Officers').exists() else 'All',
                            sender=instance.processed_by,
                            recipient_user=instance.user,
                            related_order=instance
                        )
                        
                        # Notify Management
                        create_notification(
                            notification_type='material_processed',
                            title=f'Material {processing_type}: {instance.name}',
                            message=f'{instance.processed_by.username if instance.processed_by else "Storekeeper"} {processing_type.lower()} {qty_diff} {instance.unit} of {instance.name}. '
                                    f'Total processed: {instance.processed_quantity}/{instance.quantity}. '
                                    f'Request Code: {instance.request_code}',
                            recipient_group='Management',
                            sender=instance.processed_by,
                            related_order=instance
                        )
                
                # Check if status changed
                if hasattr(instance, '_status_changed'):
                    old_status = instance._old_status
                    new_status = instance.status
                    
                    if old_status != new_status:
                        # Status changed - notify relevant parties based on new status
                        if new_status == 'Processed' and not hasattr(instance, '_quantity_processed'):
                            # Status changed to Processed but we haven't already sent processing notification
                            # Material processed by storekeeper - notify requester
                            create_notification(
                                notification_type='material_processed',
                                title=f'Request Processed: {instance.name}',
                                message=f'Your request for {instance.name} has been processed. '
                                        f'Processed: {instance.processed_quantity} {instance.unit}. '
                                        f'Request Code: {instance.request_code}',
                                recipient_group='Schedule Officers' if instance.user and instance.user.groups.filter(name='Schedule Officers').exists() else 'All',
                                sender=instance.processed_by,
                                recipient_user=instance.user,
                                related_order=instance
                            )
                            
                            # Notify Management
                            create_notification(
                                notification_type='material_processed',
                                title=f'Material Processed: {instance.name}',
                                message=f'{instance.processed_by.username if instance.processed_by else "Storekeeper"} processed {instance.processed_quantity} {instance.unit} of {instance.name}. '
                                        f'Request Code: {instance.request_code}',
                                recipient_group='Management',
                                sender=instance.processed_by,
                                related_order=instance
                            )
                        
                        elif new_status == 'In Transit':
                            # Material in transit - notify requester
                            create_notification(
                                notification_type='transport_assigned',
                                title=f'Material In Transit: {instance.name}',
                                message=f'Your requested materials ({instance.name}) are now in transit. '
                                        f'Request Code: {instance.request_code}',
                                recipient_group='All',
                                sender=None,
                                recipient_user=instance.user,
                                related_order=instance
                            )
                        
                        elif new_status == 'Delivered':
                            # Material delivered - notify all stakeholders
                            create_notification(
                                notification_type='material_delivered',
                                title=f'Material Delivered: {instance.name}',
                                message=f'{instance.quantity} {instance.unit} of {instance.name} has been delivered. '
                                        f'Request Code: {instance.request_code}',
                                recipient_group='Management',
                                sender=None,
                                related_order=instance
                            )
                            
                            # Notify requester
                            create_notification(
                                notification_type='material_delivered',
                                title=f'Your Order Delivered: {instance.name}',
                                message=f'Your requested materials have been delivered successfully. '
                                        f'Request Code: {instance.request_code}',
                                recipient_group='All',
                                sender=None,
                                recipient_user=instance.user,
                                related_order=instance
                            )
                
            except MaterialOrder.DoesNotExist:
                pass  # This is a new instance
            except Exception as inner_e:
                logger.error(f"Error processing notification in post_save: {str(inner_e)}", exc_info=True)
    
    except Exception as e:
        logger.error(f"Error in material order notification handler: {str(e)}", exc_info=True)


@receiver(pre_save, sender=MaterialOrder)
def track_material_order_status_change(sender, instance, **kwargs):
    """
    Track status and processing changes before saving to trigger appropriate notifications.
    """
    if instance.pk:
        try:
            old_instance = MaterialOrder.objects.get(pk=instance.pk)
            
            # Track status changes
            if old_instance.status != instance.status:
                instance._status_changed = True
                instance._old_status = old_instance.status
            
            # Track processed_quantity changes (for partial/full processing)
            if old_instance.processed_quantity != instance.processed_quantity:
                instance._quantity_processed = True
                instance._old_processed_quantity = old_instance.processed_quantity
                
        except MaterialOrder.DoesNotExist:
            pass


# ===== TRANSPORT SIGNALS =====

@receiver(post_save, sender=MaterialTransport)
def handle_transport_notifications(sender, instance, created, **kwargs):
    """
    Create notifications when transport is assigned or updated.
    """
    try:
        if created:
            # Transport assigned - notify transporter and management
            create_notification(
                notification_type='transport_assigned',
                title=f'Transport Assignment: {instance.material_order.name if instance.material_order else "Materials"}',
                message=f'Transport assigned to {instance.transporter.name if instance.transporter else "transporter"}. '
                        f'Vehicle: {instance.vehicle.registration_number if instance.vehicle else "TBD"}. '
                        f'Quantity: {instance.quantity_assigned} {instance.material_order.unit if instance.material_order else "units"}',
                recipient_group='Management',
                sender=instance.assigned_by,
                related_transport=instance,
                related_order=instance.material_order
            )
            
            # Notify Schedule Officers if they made the request
            if instance.material_order and instance.material_order.user:
                create_notification(
                    notification_type='transport_assigned',
                    title=f'Transport Assigned for Your Request',
                    message=f'Transport has been assigned for your material request ({instance.material_order.name}). '
                            f'Transporter: {instance.transporter.name if instance.transporter else "TBD"}',
                    recipient_group='All',
                    sender=instance.assigned_by,
                    recipient_user=instance.material_order.user,
                    related_transport=instance,
                    related_order=instance.material_order
                )
        
        else:
            # Transport updated - check for status changes
            if hasattr(instance, '_transport_status_changed'):
                old_status = instance._old_transport_status
                new_status = instance.status
                
                if new_status == 'In Transit' and old_status != 'In Transit':
                    create_notification(
                        notification_type='transport_assigned',
                        title=f'Materials En Route',
                        message=f'Transport for {instance.material_order.name if instance.material_order else "materials"} is now en route. '
                                f'Expected delivery to {instance.destination_location if instance.destination_location else "site"}',
                        recipient_group='Management',
                        sender=None,
                        related_transport=instance,
                        related_order=instance.material_order
                    )
                
                elif new_status == 'Delivered' and old_status != 'Delivered':
                    create_notification(
                        notification_type='material_delivered',
                        title=f'Materials Delivered',
                        message=f'Transport completed for {instance.material_order.name if instance.material_order else "materials"}. '
                                f'{instance.quantity_assigned} units delivered to {instance.destination_location if instance.destination_location else "site"}',
                        recipient_group='Management',
                        sender=None,
                        related_transport=instance,
                        related_order=instance.material_order
                    )
    
    except Exception as e:
        logger.error(f"Error in transport notification handler: {str(e)}", exc_info=True)


@receiver(pre_save, sender=MaterialTransport)
def track_transport_status_change(sender, instance, **kwargs):
    """
    Track transport status changes before saving.
    """
    if instance.pk:
        try:
            old_instance = MaterialTransport.objects.get(pk=instance.pk)
            if old_instance.status != instance.status:
                instance._transport_status_changed = True
                instance._old_transport_status = old_instance.status
        except MaterialTransport.DoesNotExist:
            pass


# ===== SITE RECEIPT SIGNALS =====

@receiver(post_save, sender=SiteReceipt)
def handle_site_receipt_notifications(sender, instance, created, **kwargs):
    """
    Create notifications when site receipts are logged.
    """
    try:
        if created:
            # Site receipt logged - notify Management and Storekeepers
            create_notification(
                notification_type='site_receipt_logged',
                title=f'Site Receipt Logged: {instance.material_transport.material_order.name if instance.material_transport and instance.material_transport.material_order else "Materials"}',
                message=f'{instance.received_by.username if instance.received_by else "Consultant"} confirmed receipt of materials on site. '
                        f'Quantity: {instance.received_quantity} units. '
                        f'Condition: {instance.condition}. '
                        f'Location: {instance.material_transport.destination_location if instance.material_transport else "Site"}',
                recipient_group='Management',
                sender=instance.received_by,
                related_transport=instance.material_transport
            )
            
            # Notify Storekeepers
            create_notification(
                notification_type='site_receipt_logged',
                title=f'Materials Received on Site',
                message=f'Site receipt confirmed for {instance.material_transport.material_order.name if instance.material_transport and instance.material_transport.material_order else "materials"}. '
                        f'Quantity: {instance.received_quantity}, Condition: {instance.condition}',
                recipient_group='Storekeepers',
                sender=instance.received_by,
                related_transport=instance.material_transport
            )
    
    except Exception as e:
        logger.error(f"Error in site receipt notification handler: {str(e)}", exc_info=True)


# ===== INVENTORY SIGNALS =====

@receiver(post_save, sender=InventoryItem)
def handle_low_inventory_notifications(sender, instance, created, **kwargs):
    """
    Create notifications when inventory falls below reorder level.
    """
    try:
        # Check if quantity is low (below 10 as default threshold)
        LOW_STOCK_THRESHOLD = 10
        CRITICAL_STOCK_THRESHOLD = 5
        
        if not created:  # Only for updates, not new items
            if instance.quantity <= CRITICAL_STOCK_THRESHOLD:
                # Critical stock level
                create_notification(
                    notification_type='staff_prompt',
                    title=f'CRITICAL: Low Stock Alert - {instance.name}',
                    message=f'{instance.name} is critically low with only {instance.quantity} {instance.unit} remaining. '
                            f'Immediate restocking required! Code: {instance.code}',
                    recipient_group='Storekeepers',
                    sender=None
                )
                
                # Also notify Management
                create_notification(
                    notification_type='staff_prompt',
                    title=f'CRITICAL: Low Stock Alert - {instance.name}',
                    message=f'{instance.name} is critically low ({instance.quantity} {instance.unit}). Immediate action required.',
                    recipient_group='Management',
                    sender=None
                )
            
            elif instance.quantity <= LOW_STOCK_THRESHOLD:
                # Low stock level
                create_notification(
                    notification_type='staff_prompt',
                    title=f'Low Stock Alert - {instance.name}',
                    message=f'{instance.name} stock is low with {instance.quantity} {instance.unit} remaining. '
                            f'Consider restocking soon. Code: {instance.code}',
                    recipient_group='Storekeepers',
                    sender=None
                )
    
    except Exception as e:
        logger.error(f"Error in inventory notification handler: {str(e)}", exc_info=True)


# ===== BOQ SIGNALS =====

@receiver(post_save, sender=BillOfQuantity)
def handle_boq_notifications(sender, instance, created, **kwargs):
    """
    Create notifications when BOQ entries are created or updated.
    """
    try:
        if created:
            # New BOQ entry - notify Management and Schedule Officers
            create_notification(
                notification_type='boq_updated',
                title=f'New BOQ Entry: {instance.material_description}',
                message=f'New BOQ entry added for {instance.material_description}. '
                        f'Package: {instance.package_number}, '
                        f'Contract Qty: {instance.contract_quantity}, '
                        f'Location: {instance.district}, {instance.region}',
                recipient_group='Management',
                sender=instance.user
            )
            
            # Notify Schedule Officers
            create_notification(
                notification_type='boq_updated',
                title=f'New BOQ Entry: {instance.material_description}',
                message=f'BOQ updated for package {instance.package_number} in {instance.district}. '
                        f'Material: {instance.material_description}, Qty: {instance.contract_quantity}',
                recipient_group='Schedule Officers',
                sender=instance.user
            )
    
    except Exception as e:
        logger.error(f"Error in BOQ notification handler: {str(e)}", exc_info=True)
