from django.contrib import messages
from django.contrib.auth import login, authenticate
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from .forms import AuthenticationForm, UserRegistration
from .models import InventoryItem


class SignUpView(CreateView):
    form_class = UserRegistration
    template_name = 'Inventory/signup.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        response = super().form_valid(form)
        username = form.cleaned_data.get('username')
        password = form.cleaned_data.get('password1')
        user = authenticate(username=username, password=password)
        login(self.request, user)
        messages.success(self.request, 'Account created successfully!')
        return response


class SignInView(LoginView):
    form_class = AuthenticationForm
    template_name = 'Inventory/signin.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, 'You have been logged in successfully!')
        return super().form_valid(form)


class CustomLogoutView(LogoutView):
    next_page = 'index'

    def dispatch(self, request, *args, **kwargs):
        messages.info(request, 'You have been logged out successfully.')
        return super().dispatch(request, *args, **kwargs)


class Dashboard(TemplateView):
    template_name = 'Inventory/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all inventory items with related data including warehouse
        items = InventoryItem.objects.all().select_related('category', 'unit', 'warehouse').order_by('name')
        
        # Get low inventory items (quantity <= 10)
        low_inventory_items = items.filter(quantity__lte=10)
        low_inventory_names = list(low_inventory_items.values_list('name', flat=True))
        
        # Debug information
        print(f"Found {items.count()} items in the database")
        print(f"Found {low_inventory_items.count()} low inventory items")
        
        context.update({
            'items': items,  # This is what the template is looking for
            'low_inventory_items': low_inventory_names,
            'low_inventory_ids': list(low_inventory_items.values_list('id', flat=True))
        })
        
        return context
