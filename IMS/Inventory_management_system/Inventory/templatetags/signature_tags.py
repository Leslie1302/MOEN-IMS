"""
Template tags for rendering digital signature stamps.
Creates visual, stamp-like representations of user signatures.
"""

from django import template
from django.utils.safestring import mark_safe
from django.utils.html import escape
from datetime import datetime

register = template.Library()


@register.inclusion_tag('Inventory/signature_stamp.html')
def signature_stamp(profile, size='medium'):
    """
    Render a visual digital signature stamp for a user profile.
    
    Args:
        profile: Profile object with signature_stamp field
        size: 'small', 'medium', or 'large'
    
    Usage in templates:
        {% load signature_tags %}
        {% signature_stamp user.profile %}
        {% signature_stamp user.profile size='large' %}
    """
    if not profile or not profile.signature_stamp:
        return {
            'has_stamp': False,
            'size': size
        }
    
    # Parse the signature stamp
    stamp_data = profile.display_signature_stamp()
    
    if not stamp_data:
        return {
            'has_stamp': False,
            'size': size
        }
    
    # Extract components
    full_name = stamp_data.get('SIGNED_BY', 'Unknown')
    timestamp_str = stamp_data.get('TIMESTAMP', '')
    stamp_id = stamp_data.get('ID', '')
    
    # Parse timestamp
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('+00:00', ''))
        year = timestamp.year
        formatted_date = timestamp.strftime('%b %d, %Y')
        formatted_time = timestamp.strftime('%I:%M %p')
    except:
        year = 'N/A'
        formatted_date = 'N/A'
        formatted_time = ''
    
    # Get user role/title
    user_role = 'User'
    if profile.user:
        if profile.user.is_superuser:
            user_role = 'Administrator'
        elif profile.user.is_staff:
            user_role = 'Staff'
        elif profile.user.groups.exists():
            user_role = profile.user.groups.first().name
    
    return {
        'has_stamp': True,
        'full_name': full_name,
        'user_role': user_role,
        'year': year,
        'stamp_id': stamp_id,
        'formatted_date': formatted_date,
        'formatted_time': formatted_time,
        'size': size,
        'profile': profile
    }


@register.simple_tag
def signature_stamp_inline(profile):
    """
    Render a compact inline signature stamp.
    
    Usage:
        {% load signature_tags %}
        {% signature_stamp_inline user.profile %}
    """
    if not profile or not profile.signature_stamp:
        return mark_safe('<span class="no-signature">Not Signed</span>')
    
    stamp_data = profile.display_signature_stamp()
    if not stamp_data:
        return mark_safe('<span class="no-signature">Invalid Signature</span>')
    
    full_name = escape(stamp_data.get('SIGNED_BY', 'Unknown'))
    timestamp_str = stamp_data.get('TIMESTAMP', '')
    
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('+00:00', ''))
        date_str = timestamp.strftime('%b %d, %Y')
    except:
        date_str = 'Unknown date'
    
    html = f'''
    <span class="signature-inline">
        <span class="signature-icon">✓</span>
        <span class="signature-user">{full_name}</span>
        <span class="signature-date">{date_str}</span>
    </span>
    '''
    
    return mark_safe(html)


@register.filter
def has_signature(profile):
    """
    Check if a profile has a signature stamp.
    
    Usage:
        {% if user.profile|has_signature %}
            ...
        {% endif %}
    """
    return profile and profile.signature_stamp


@register.filter
def signature_username(profile):
    """
    Get the full name from a signature stamp.
    
    Usage:
        {{ user.profile|signature_username }}
    """
    if not profile or not profile.signature_stamp:
        return 'Unknown'
    
    stamp_data = profile.display_signature_stamp()
    return stamp_data.get('SIGNED_BY', 'Unknown') if stamp_data else 'Unknown'


@register.filter
def signature_date(profile):
    """
    Get the formatted date from a signature stamp.
    
    Usage:
        {{ user.profile|signature_date }}
    """
    if not profile or not profile.signature_stamp:
        return 'N/A'
    
    stamp_data = profile.display_signature_stamp()
    if not stamp_data:
        return 'N/A'
    
    timestamp_str = stamp_data.get('TIMESTAMP', '')
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace('+00:00', ''))
        return timestamp.strftime('%B %d, %Y at %I:%M %p')
    except:
        return 'N/A'
