import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import View

from Inventory.models import MaterialTransport
from Inventory.forms import MaterialTransportForm

# Configure logger
logger = logging.getLogger(__name__)

class MaterialTransportView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'Inventory.view_materialtransport'

    def get(self, request, pk=None):
        """Handle GET requests based on the URL path."""
        path = request.path
        if 'transport_detail' in path and pk:
            # Detail view
            transport = get_object_or_404(MaterialTransport, pk=pk)
            return render(request, 'Inventory/transport_detail.html', {'transport': transport})
        elif 'transport_list' in path:
            # List view
            transports = MaterialTransport.objects.all()
            return render(request, 'Inventory/transport_list.html', {'transports': transports})
        elif 'transport_form' in path:
            # Create form view
            form = MaterialTransportForm()
            return render(request, 'Inventory/transport_form.html', {'form': form})
        else:
            # Dashboard view (transport_dash)
            transports = MaterialTransport.objects.all()
            return render(request, 'Inventory/transport_dash.html', {'transports': transports})

    def post(self, request, pk=None):
        """Handle POST requests for creating a new transport."""
        # Check if we are in the form view
        if 'transport_form' in request.path:
            form = MaterialTransportForm(request.POST)
            if form.is_valid():
                form.save()
                return redirect('transport_list')
            return render(request, 'Inventory/transport_form.html', {'form': form})
        return redirect('transport_list')  # Fallback
