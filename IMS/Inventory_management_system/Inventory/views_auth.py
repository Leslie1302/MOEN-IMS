from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView


class AwaitingAuthorizationView(LoginRequiredMixin, TemplateView):
    """View for users who have registered but haven't been assigned a role yet."""
    template_name = 'Inventory/awaiting_authorization.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Allow access only to users with no groups (not assigned any role yet)
        if request.user.groups.exists() or request.user.is_superuser:
            return redirect('dashboard')  # Redirect to dashboard if user has roles
        return super().dispatch(request, *args, **kwargs)


def custom_403_view(request, exception=None):
    """Custom 403 Forbidden view."""
    return render(request, '403.html', status=403)


def custom_404_view(request, exception=None):
    """Custom 404 Not Found view."""
    return render(request, '404.html', status=404)


def custom_500_view(request):
    """Custom 500 Internal Server Error view."""
    return render(request, '500.html', status=500)
