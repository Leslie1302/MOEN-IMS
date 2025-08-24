from django import template
from django.contrib.auth.models import Group

register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name):
    """
    Check if a user is in a specific group.
    Usage: {% if user|has_group:"Schedule Officer" %}
    """
    try:
        group = Group.objects.get(name=group_name)
        return user.groups.filter(id=group.id).exists()
    except Group.DoesNotExist:
        return False

@register.filter(name='is_in_group')
def is_in_group(user, group_name):
    """
    Alternative filter to check if a user is in a specific group.
    Usage: {% if user|is_in_group:"Storekeeper" %}
    """
    return user.groups.filter(name=group_name).exists()
