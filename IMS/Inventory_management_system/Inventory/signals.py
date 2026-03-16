"""
Signals for automatic notification creation based on system events.
Notifications are role-based - users only see notifications relevant to their group.

Also handles automatic creation of user profiles and digital signature stamps.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from django.db.models import F
from .models import (
    MaterialOrder, MaterialTransport, SiteReceipt, 
    InventoryItem, BillOfQuantity, Notification, Profile
)
import logging
from django.conf import settings
from accounts.notifications import send_email_notification
from accounts.models import MicrosoftCredentials

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
        recipient_group: Target group ('Store Officers', 'Schedule Officers', 'Management', etc.)
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
        
        # Trigger email notification via M365
        try:
            _trigger_email_notification(notification)
        except Exception as email_err:
            logger.error(f"Failed to trigger email for notification {notification.id}: {str(email_err)}")
            
        return notification
    except Exception as e:
        logger.error(f"Error creating notification: {str(e)}", exc_info=True)
        return None


def _trigger_email_notification(notification):
    """
    Internal helper to send email alerts for a notification.
    """
    # 1. Resolve Recipient Emails
    recipients = []
    if notification.recipient_user and notification.recipient_user.email:
        recipients.append(notification.recipient_user.email)
    
    if notification.recipient_group:
        if notification.recipient_group == 'All':
            users = User.objects.filter(is_active=True).exclude(email='')
        else:
            users = User.objects.filter(groups__name=notification.recipient_group, is_active=True).exclude(email='')
        
        for u in users:
            if u.email and u.email not in recipients:
                recipients.append(u.email)
    
    if not recipients:
        logger.warning(f"No recipients found for email notification {notification.id}")
        return

    # 2. Resolve Sender (must have valid M365 token)
    email_sender = None
    # Try original sender first
    if notification.sender and MicrosoftCredentials.objects.filter(user=notification.sender).exists():
        email_sender = notification.sender
    else:
        # Fallback to any admin with creds
        email_sender = User.objects.filter(is_superuser=True, microsoft_credentials__isnull=False).first()

    if not email_sender:
        logger.error(f"Cannot send email for notification {notification.id}: No user with M365 credentials found to act as sender.")
        return

    # 3. Construct and Send Email
    subject = f"[MOEN-IMS] {notification.title}"
    
    # Simple HTML body
    html_body = f"""
    <div style="font-family: sans-serif; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
        <h2 style="color: #0078d4;">{notification.title}</h2>
        <p style="font-size: 16px; color: #333;">{notification.message}</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="font-size: 12px; color: #666;">
            This is an automated notification from the MOEN Inventory Management System.<br>
            <a href="{settings.BASE_URL if hasattr(settings, 'BASE_URL') else ''}/dashboard/" style="color: #0078d4; text-decoration: none;">View Dashboard</a>
        </p>
    </div>
    """
    
    try:
        send_email_notification(
            user=email_sender,
            to=recipients,
            subject=subject,
            body=html_body,
            body_type="HTML"
        )
        logger.info(f"Email alert sent for notification {notification.id} to {len(recipients)} recipients.")
    except Exception as e:
        logger.error(f"Graph API Email Error for notification {notification.id}: {str(e)}")
        # Don't re-raise, we don't want to break the app if email fails


# ===== MATERIAL ORDER SIGNALS =====

@receiver(post_save, sender=MaterialOrder)
def handle_material_order_notifications(sender, instance, created, **kwargs):
    """
    Create notifications when material orders are created or updated.
    Different notifications go to different groups based on the action.
    """
    try:
        if created:
            # New material request - notify Store Officers
            if instance.request_type == 'Release':
                create_notification(
                    notification_type='material_request',
                    title=f'New Release Request: {instance.name}',
                    message=f'{instance.user.username if instance.user else "Someone"} requested {instance.quantity} {instance.unit} of {instance.name}. '
                            f'Location: {instance.district}, {instance.region}. '
                            f'Request Code: {instance.request_code}',
                    recipient_group='Store Officers',
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
                        
                        # Material processed by store officer - notify requester
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
                            message=f'{instance.processed_by.username if instance.processed_by else "Store Officer"} {processing_type.lower()} {qty_diff} {instance.unit} of {instance.name}. '
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
                            # Material processed by store officer - notify requester
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
                                message=f'{instance.processed_by.username if instance.processed_by else "Store Officer"} processed {instance.processed_quantity} {instance.unit} of {instance.name}. '
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
                        f'Quantity: {instance.quantity} {instance.material_order.unit if instance.material_order else "units"}',
                recipient_group='Management',
                sender=instance.created_by,
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
                    sender=instance.created_by,
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
                                f'Expected delivery to {instance.district if instance.district else "site"}',
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
                                f'{instance.quantity} units delivered to {instance.district if instance.district else "site"}',
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
            # Site receipt logged - notify Management and Store Officers
            create_notification(
                notification_type='site_receipt_logged',
                title=f'Site Receipt Logged: {instance.material_transport.material_order.name if instance.material_transport and instance.material_transport.material_order else "Materials"}',
                message=f'{instance.received_by.username if instance.received_by else "Consultant"} confirmed receipt of materials on site. '
                        f'Quantity: {instance.received_quantity} units. '
                        f'Condition: {instance.condition}. '
                        f'Location: {instance.material_transport.district if instance.material_transport else "Site"}',
                recipient_group='Management',
                sender=instance.received_by,
                related_transport=instance.material_transport
            )
            
            # Notify Store Officers
            create_notification(
                notification_type='site_receipt_logged',
                title=f'Materials Received on Site',
                message=f'Site receipt confirmed for {instance.material_transport.material_order.name if instance.material_transport and instance.material_transport.material_order else "materials"}. '
                        f'Quantity: {instance.received_quantity}, Condition: {instance.condition}',
                recipient_group='Store Officers',
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
                    recipient_group='Store Officers',
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
                    recipient_group='Store Officers',
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


# ===== USER PROFILE & SIGNATURE STAMP SIGNALS =====

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create a Profile for new users.
    This ensures every user has a profile with a digital signature stamp.
    
    Args:
        sender: The User model class
        instance: The actual User instance being saved
        created: Boolean indicating if this is a new user
        **kwargs: Additional keyword arguments
    """
    if created:
        try:
            # Create profile for the new user
            profile = Profile.objects.create(user=instance)
            logger.info(f"Created profile for new user: {instance.username}")
        except Exception as e:
            logger.error(f"Error creating profile for user {instance.username}: {str(e)}", exc_info=True)


@receiver(post_save, sender=Profile)
def generate_signature_stamp_for_profile(sender, instance, created, **kwargs):
    """
    Automatically generate a digital signature stamp for new profiles.
    Also handles cases where existing profiles don't have stamps.
    
    This signal ensures that:
    1. New profiles get a stamp immediately upon creation
    2. Existing profiles without stamps get one when they're saved
    3. Proper null checks prevent 'NoneType' errors
    
    Args:
        sender: The Profile model class
        instance: The actual Profile instance being saved
        created: Boolean indicating if this is a new profile
        **kwargs: Additional keyword arguments
    """
    try:
        # Check if profile needs a signature stamp
        if not instance.signature_stamp:
            # Verify user exists and has a username
            if instance.user and hasattr(instance.user, 'username') and instance.user.username:
                try:
                    # Generate the text-based stamp (for database record)
                    stamp = instance.generate_signature_stamp()
                    
                    # Save only if we successfully generated a stamp
                    if stamp:
                        # Use update to avoid triggering the signal again
                        Profile.objects.filter(pk=instance.pk).update(signature_stamp=stamp)
                        logger.info(f"Generated signature stamp for profile: {instance.user.username}")
                        
                        # Also generate PNG stamp image
                        try:
                            if hasattr(instance, 'generate_digital_stamp_png'):
                                png_path = instance.generate_digital_stamp_png()
                                if png_path:
                                    logger.info(f"Generated PNG digital stamp for profile: {instance.user.username} at {png_path}")
                        except Exception as png_error:
                            logger.warning(f"Could not generate PNG stamp for {instance.user.username}: {str(png_error)}")
                    else:
                        logger.warning(f"Failed to generate stamp for profile {instance.pk}: Empty stamp returned")
                        
                except ValueError as ve:
                    # This happens if user is None or has no username
                    logger.warning(f"Cannot generate signature stamp for profile {instance.pk}: {str(ve)}")
                except Exception as e:
                    logger.error(f"Error generating signature stamp for profile {instance.pk}: {str(e)}", exc_info=True)
            else:
                # Profile has no user or user has no username
                if not instance.user:
                    logger.warning(f"Profile {instance.pk} has no associated user - cannot generate signature stamp")
                else:
                    logger.warning(f"User for profile {instance.pk} has no username - cannot generate signature stamp")
    
    except Exception as e:
        # Catch-all to prevent signal from breaking the save operation
        logger.error(f"Unexpected error in signature stamp signal for profile {instance.pk}: {str(e)}", exc_info=True)
