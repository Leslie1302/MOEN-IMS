from django.views.generic import CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from .models import InventoryItem
from .forms import InventoryItemForm


class AddItem(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = 'Inventory/item_form.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        return self.request.user.is_staff

    def form_valid(self, form):
        form.instance.user = self.request.user
        # Attach the user's group if available (keeps filtering by group consistent)
        if not self.request.user.is_superuser:
            first_group = self.request.user.groups.first()
            if first_group:
                form.instance.group = first_group
        messages.success(self.request, 'Item added successfully!')
        return super().form_valid(form)


class EditItem(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = 'Inventory/item_form.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        return self.request.user.is_staff

    def get_queryset(self):
        """Scope editable items to the user's own group(s).

        ``is_staff`` alone is not authorisation: without this, any staff
        user could edit another group's stock by changing the URL pk
        (IDOR). This mirrors the app-wide scoping convention used in
        ``views/order_views.py`` — superusers and Management see all
        items; everyone else is restricted to their own group(s). Items
        outside the user's scope raise 404 (not 403) so we don't leak
        that the pk exists.
        """
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.groups.filter(name='Management').exists():
            return qs
        return qs.filter(group__in=user.groups.all())

    def form_valid(self, form):
        messages.success(self.request, 'Item updated successfully!')
        return super().form_valid(form)


class DeleteItem(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = InventoryItem
    template_name = 'Inventory/delete_confirm.html'
    success_url = reverse_lazy('dashboard')
    success_message = 'Item was deleted successfully.'

    def test_func(self):
        return self.request.user.is_staff

    def get_queryset(self):
        """Scope deletable items to the user's own group(s).

        Same IDOR guard as ``EditItem`` — deletion is higher-impact than
        edit, so object-level scoping here is essential. Mirrors the
        app-wide convention in ``views/order_views.py``.
        """
        qs = super().get_queryset()
        user = self.request.user
        if user.is_superuser or user.groups.filter(name='Management').exists():
            return qs
        return qs.filter(group__in=user.groups.all())

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        return super().delete(request, *args, **kwargs)
