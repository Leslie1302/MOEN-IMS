"""
Views for notification management.
Users see notifications based on their group membership.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.generic import ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from .models import Notification
import logging

logger = logging.getLogger(__name__)


class NotificationListView(LoginRequiredMixin, ListView):
    """
    Display notifications relevant to the current user based on their group membership.
    """
    model = Notification
    template_name = 'Inventory/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 20
    
    def get_queryset(self):
        """
        Get notifications for the current user's groups with optional filtering.
        """
        user = self.request.user
        
        # Get user's groups
        user_groups = user.groups.values_list('name', flat=True)
        
        # Build query
        query = Q(recipient_group='All')  # Always include 'All' notifications
        
        # Add user's specific groups
        for group_name in user_groups:
            query |= Q(recipient_group=group_name)
        
        # Also include notifications specifically for this user
        query |= Q(recipient_user=user)
        
        # Superusers see everything
        if user.is_superuser:
            queryset = Notification.objects.all()
        else:
            queryset = Notification.objects.filter(query)
        
        # Apply filters from GET parameters
        # Filter by unread status
        if self.request.GET.get('unread') == 'true':
            queryset = queryset.filter(is_read=False)
        
        # Filter by notification type
        notification_type = self.request.GET.get('type')
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get unread count
        user = self.request.user
        user_groups = user.groups.values_list('name', flat=True)
        
        query = Q(recipient_group='All', is_read=False)
        for group_name in user_groups:
            query |= Q(recipient_group=group_name, is_read=False)
        query |= Q(recipient_user=user, is_read=False)
        
        if user.is_superuser:
            context['unread_count'] = Notification.objects.filter(is_read=False).count()
        else:
            context['unread_count'] = Notification.objects.filter(query).count()
        
        # Add filter status
        context['show_unread_only'] = self.request.GET.get('unread') == 'true'
        context['notification_type'] = self.request.GET.get('type', 'all')
        
        return context


@login_required
def notification_detail(request, pk):
    """
    View a single notification and mark it as read.
    """
    notification = get_object_or_404(Notification, pk=pk)
    
    # Check if user has access to this notification
    user = request.user
    user_groups = user.groups.values_list('name', flat=True)
    
    has_access = (
        user.is_superuser or
        notification.recipient_group == 'All' or
        notification.recipient_group in user_groups or
        notification.recipient_user == user
    )
    
    if not has_access:
        return render(request, '403.html', status=403)
    
    # Mark as read
    if not notification.is_read:
        notification.mark_as_read(user)
    
    context = {
        'notification': notification
    }
    
    return render(request, 'Inventory/notification_detail.html', context)


@login_required
def mark_notification_read(request, pk):
    """
    Mark a notification as read via AJAX.
    """
    if request.method == 'POST':
        notification = get_object_or_404(Notification, pk=pk)
        
        # Check if user has access
        user = request.user
        user_groups = user.groups.values_list('name', flat=True)
        
        has_access = (
            user.is_superuser or
            notification.recipient_group == 'All' or
            notification.recipient_group in user_groups or
            notification.recipient_user == user
        )
        
        if not has_access:
            return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)
        
        notification.mark_as_read(user)
        
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)


@login_required
def mark_all_notifications_read(request):
    """
    Mark all notifications for the current user as read.
    """
    if request.method == 'POST':
        user = request.user
        user_groups = user.groups.values_list('name', flat=True)
        
        # Build query for user's notifications
        query = Q(recipient_group='All', is_read=False)
        for group_name in user_groups:
            query |= Q(recipient_group=group_name, is_read=False)
        query |= Q(recipient_user=user, is_read=False)
        
        if user.is_superuser:
            notifications = Notification.objects.filter(is_read=False)
        else:
            notifications = Notification.objects.filter(query)
        
        # Mark all as read
        count = notifications.count()
        notifications.update(is_read=True, read_at=timezone.now())
        
        return JsonResponse({'success': True, 'count': count})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)


@login_required
def get_unread_count(request):
    """
    Get unread notification count for the current user (AJAX endpoint).
    """
    user = request.user
    user_groups = user.groups.values_list('name', flat=True)
    
    # Build query
    query = Q(recipient_group='All', is_read=False)
    for group_name in user_groups:
        query |= Q(recipient_group=group_name, is_read=False)
    query |= Q(recipient_user=user, is_read=False)
    
    if user.is_superuser:
        count = Notification.objects.filter(is_read=False).count()
    else:
        count = Notification.objects.filter(query).count()
    
    return JsonResponse({'count': count})


@login_required
def delete_notification(request, pk):
    """
    Delete a notification (superusers only).
    """
    if not request.user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    if request.method == 'POST':
        notification = get_object_or_404(Notification, pk=pk)
        notification.delete()
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=400)


@login_required
def notification_preferences(request):
    """
    View and update notification preferences (future feature).
    """
    # This is a placeholder for future notification preference management
    context = {
        'title': 'Notification Preferences',
        'message': 'Notification preferences will be available in a future update.'
    }
    return render(request, 'Inventory/notification_preferences.html', context)
