from django.db.models import Q
from .models import Profile, Notification


def user_profile(request):
    """Ensure profile is available globally in templates"""
    if request.user.is_authenticated:
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return {'profile': profile}
    return {'profile': None}


def notifications_context(request):
    """
    Make unread notification count available in all templates.
    Users only see notifications for their groups.
    """
    if not request.user.is_authenticated:
        return {
            'unread_notifications_count': 0,
            'recent_notifications': []
        }
    
    user = request.user
    user_groups = user.groups.values_list('name', flat=True)
    
    # Build query for user's notifications
    query = Q(recipient_group='All', is_read=False)
    for group_name in user_groups:
        query |= Q(recipient_group=group_name, is_read=False)
    query |= Q(recipient_user=user, is_read=False)
    
    # Get unread count
    if user.is_superuser:
        unread_count = Notification.objects.filter(is_read=False).count()
        recent_notifications = Notification.objects.filter(is_read=False).order_by('-created_at')[:5]
    else:
        unread_count = Notification.objects.filter(query).count()
        recent_notifications = Notification.objects.filter(query).order_by('-created_at')[:5]
    
    return {
        'unread_notifications_count': unread_count,
        'recent_notifications': recent_notifications
    }
