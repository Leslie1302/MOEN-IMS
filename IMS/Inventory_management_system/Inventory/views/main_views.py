from django.views.generic import TemplateView
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import render
from django.http import Http404

class Index(TemplateView):
    template_name = 'Inventory/index.html'

class AboutView(TemplateView):
    template_name = 'Inventory/about.html'

class SuperuserOnlyMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        # Hide existence of the page from non-superusers
        raise Http404()
