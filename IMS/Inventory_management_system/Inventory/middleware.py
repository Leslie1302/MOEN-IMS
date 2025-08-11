from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

class UserRoleMiddleware(MiddlewareMixin):
    """
    Middleware to handle role-based access control.
    Redirects unassigned users to the awaiting authorization page.
    """
    def __init__(self, get_response=None):
        self.get_response = get_response
        # List of URLs that don't require authentication or role assignment
        self.allowed_urls = [
            '/signin/',
            '/signup/',
            '/logout/',
            '/help/',
            '/profile/',
            '/awaiting-authorization/',
        ]
        
        # Add static and media URLs to allowed paths
        if hasattr(settings, 'STATIC_URL'):
            self.allowed_urls.append(settings.STATIC_URL)
        if hasattr(settings, 'MEDIA_URL'):
            self.allowed_urls.append(settings.MEDIA_URL)

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Skip middleware for admin URLs
        if request.path.startswith('/admin/'):
            return None

        # Skip if URL is in the allowed list
        if any(request.path.startswith(allowed) for allowed in self.allowed_urls):
            return None

        # Skip for static and media files
        if request.path.startswith(settings.STATIC_URL) or request.path.startswith(settings.MEDIA_URL):
            return None

        # Check if user is authenticated
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.path, settings.LOGIN_URL)

        # Allow superusers to access everything
        if request.user.is_superuser:
            return None

        # If user has no groups and not on the awaiting_authorization page
        if not hasattr(request.user, 'groups') or not request.user.groups.exists():
            if request.path != reverse('awaiting_authorization'):
                return redirect('awaiting_authorization')
        
        # If user has groups, make sure they're not trying to access the awaiting_authorization page
        elif request.path == reverse('awaiting_authorization'):
            return redirect('dashboard')

        return None
