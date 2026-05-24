"""
KPI and Performance Views

Provides views for displaying performance metrics and KPIs for different user roles.
"""

from django.views.generic import TemplateView, DetailView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json

from Inventory.services.kpi import (
    get_user_performance_summary, get_management_dashboard_summary,
    get_store_officer_kpis, get_schedule_officer_kpis,
    get_consultant_kpis, get_management_kpis
)


class StaffProfilePerformanceView(LoginRequiredMixin, TemplateView):
    """
    Display performance metrics for a specific staff member.
    Accessible by the user themselves and by management.
    """
    template_name = 'Inventory/staff_profile_performance.html'
    context_object_name = 'staff_member'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        username = self.kwargs.get('username')
        staff_member = get_object_or_404(User, username=username)

        # Check if user can view this profile
        # (themselves, or management user)
        if self.request.user != staff_member and not self.request.user.groups.filter(name='Management').exists():
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied

        # Get performance summary
        performance = get_user_performance_summary(staff_member)

        context['staff_member'] = staff_member
        context['performance'] = performance
        context['full_name'] = f"{staff_member.first_name} {staff_member.last_name}".strip()
        context['groups'] = staff_member.groups.values_list('name', flat=True)

        # Overall status
        statuses = [kpi.get('status', 'Unknown') for kpi in performance.values()]
        if 'Needs Improvement' in statuses:
            context['overall_status'] = 'Needs Improvement'
            context['status_color'] = 'danger'
        elif 'Fair' in statuses:
            context['overall_status'] = 'Fair'
            context['status_color'] = 'warning'
        else:
            context['overall_status'] = 'Good'
            context['status_color'] = 'success'

        return context


class ManagementDashboardKPIView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    Display KPI summary for management dashboard.
    Only accessible to management users.
    """
    template_name = 'Inventory/management_dashboard_kpi.html'

    def test_func(self):
        return self.request.user.groups.filter(name='Management').exists() or self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get management dashboard summary
        summary = get_management_dashboard_summary()

        context['summary'] = summary
        context['total_orders'] = summary['total_orders']
        context['completed_orders'] = summary['completed_orders']
        context['order_completion_rate'] = summary['order_completion_rate']
        context['total_deliveries'] = summary['total_deliveries']
        context['delivered'] = summary['delivered']
        context['delivery_rate'] = summary['delivery_rate']
        context['top_store_officers'] = summary['top_store_officers']
        context['top_transporters'] = summary['top_transporters']

        return context


@require_http_methods(['GET'])
def staff_performance_api(request):
    """
    AJAX endpoint to fetch performance data for a staff member.
    GET /api/staff-performance/?username=<username>
    """
    username = request.GET.get('username')
    if not username:
        return JsonResponse({'error': 'username parameter required'}, status=400)

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({'error': f'User {username} not found'}, status=404)

    try:
        # Get performance summary
        performance = get_user_performance_summary(user)

        # Build response
        response_data = {
            'username': user.username,
            'full_name': f"{user.first_name} {user.last_name}".strip(),
            'email': user.email,
            'groups': list(user.groups.values_list('name', flat=True)),
            'performance': performance,
        }

        return JsonResponse(response_data)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching staff performance for {username}: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(['GET'])
def management_dashboard_kpi_api(request):
    """
    AJAX endpoint for management dashboard KPI summary.
    GET /api/management-dashboard-kpi/
    """
    try:
        # Only management can access this
        if not (request.user.groups.filter(name='Management').exists() or request.user.is_superuser):
            return JsonResponse({'error': 'Unauthorized'}, status=403)

        # Get summary
        summary = get_management_dashboard_summary()

        return JsonResponse(summary)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching management dashboard KPI: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)
