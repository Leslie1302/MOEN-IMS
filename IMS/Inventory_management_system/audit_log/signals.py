from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.utils.timezone import now
from Inventory.models import InventoryItem, Category, Unit, MaterialOrder
from .models import AuditLog
import json

def get_client_ip(request):
    """Helper function to get IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]  # Get first IP
    return request.META.get('REMOTE_ADDR')  # Default IP

def log_action(instance, action, user=None, ip_address=None, changes=None):
    """Log changes in AuditLog"""
    AuditLog.objects.create(
        user=user if isinstance(user, User) else None,
        model_name=instance.__class__.__name__,
        object_id=instance.pk,
        action=action,
        change_message=json.dumps(changes) if changes else '',
        ip_address=ip_address
    )

@receiver(pre_save, sender=InventoryItem)
def track_inventoryitem_changes(sender, instance, **kwargs):
    try:
        old_instance = InventoryItem.objects.get(pk=instance.pk)
        changes = {
            field: {'old': getattr(old_instance, field), 'new': getattr(instance, field)}
            for field in ['name', 'quantity', 'category', 'unit']  # Add relevant fields
            if getattr(old_instance, field) != getattr(instance, field)
        }
        if changes:
            log_action(instance, 'Updated', user=instance.user, changes=changes)
    except InventoryItem.DoesNotExist:
        pass  # First-time creation, no old data

@receiver(post_save, sender=InventoryItem)
def log_inventoryitem_save(sender, instance, created, **kwargs):
    if created:
        log_action(instance, 'Created', user=instance.user)
    else:
        pass  # Already logged in `pre_save`

@receiver(post_delete, sender=InventoryItem)
def log_inventoryitem_delete(sender, instance, **kwargs):
    log_action(instance, 'Deleted', user=instance.user)

# Repeat for Category & Unit models
@receiver(pre_save, sender=Category)
def track_category_changes(sender, instance, **kwargs):
    try:
        old_instance = Category.objects.get(pk=instance.pk)
        changes = {field: {'old': getattr(old_instance, field), 'new': getattr(instance, field)}
                   for field in ['name'] if getattr(old_instance, field) != getattr(instance, field)}
        if changes:
            log_action(instance, 'Updated', user=getattr(instance, 'user', None), changes=changes)
    except Category.DoesNotExist:
        pass

@receiver(post_save, sender=Category)
def log_category_save(sender, instance, created, **kwargs):
    if created:
        log_action(instance, 'Created', user=getattr(instance, 'user', None))

@receiver(post_delete, sender=Category)
def log_category_delete(sender, instance, **kwargs):
    log_action(instance, 'Deleted', user=getattr(instance, 'user', None))

