from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LogoutView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import RedirectView, TemplateView

from .models import InventoryItem


class SignUpView(RedirectView):
    """
    Signup is handled exclusively via Microsoft 365.
    Redirect any direct visits to /signup/ to the M365 OAuth login.
    """
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse_lazy('ms_login')


class SignInView(RedirectView):
    """
    Sign-in is handled exclusively via Microsoft 365 OAuth.
    Redirect any direct visits to /signin/ to the M365 OAuth login.
    """
    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        return reverse_lazy('ms_login')


class CustomLogoutView(LogoutView):
    """
    Logs the user out of Django and then redirects to the Microsoft
    logout endpoint so the M365 session is also terminated.
    """
    next_page = 'index'

    def dispatch(self, request, *args, **kwargs):
        messages.info(request, 'You have been signed out successfully.')
        logout(request)
        ms_logout_url = (
            f"{settings.MICROSOFT['AUTHORITY']}/oauth2/v2.0/logout"
            f"?post_logout_redirect_uri={settings.MICROSOFT['REDIRECT_URI']}"
        )
        return redirect(ms_logout_url)


class Dashboard(LoginRequiredMixin, TemplateView):
    template_name = 'Inventory/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get all inventory items with related data including warehouse
        items = InventoryItem.objects.all().select_related('category', 'unit', 'warehouse').order_by('name')

        # Get low inventory items (quantity <= 10)
        low_inventory_items = items.filter(quantity__lte=10)
        low_inventory_names = list(low_inventory_items.values_list('name', flat=True))

        context.update({
            'items': items,
            'low_inventory_items': low_inventory_names,
            'low_inventory_ids': list(low_inventory_items.values_list('id', flat=True))
        })

        return context
