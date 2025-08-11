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
        form.instance.added_by = self.request.user
        messages.success(self.request, 'Item added successfully!')
        return super().form_valid(form)


class EditItem(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = InventoryItem
    form_class = InventoryItemForm
    template_name = 'Inventory/item_form.html'
    success_url = reverse_lazy('dashboard')

    def test_func(self):
        return self.request.user.is_staff

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

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, self.success_message)
        return super().delete(request, *args, **kwargs)
