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
    Usage: {% if user|is_in_group:"Store Officer" %}
    """
    return user.groups.filter(name=group_name).exists()


@register.filter(name='has_any_group')
def has_any_group(user, group_names):
    """
    Check if a user is in any of the comma-separated groups provided.
    Usage: {% if user|has_any_group:"Store Officer,Store Officers" %}
    """
    names = [name.strip() for name in str(group_names).split(',') if name.strip()]
    if not names:
        return False
    return user.groups.filter(name__in=names).exists()
