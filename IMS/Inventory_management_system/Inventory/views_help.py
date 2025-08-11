from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin


class HelpView(LoginRequiredMixin, TemplateView):
    """View for the help page."""
    template_name = 'Inventory/help.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add any context data needed for the help page
        context['page_title'] = 'Help Center'
        return context
