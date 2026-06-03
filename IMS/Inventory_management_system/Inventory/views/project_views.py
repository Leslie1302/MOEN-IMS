"""
Project management views for creating, updating, and assigning projects
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView, ListView, DetailView, UpdateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction
from django.db.models import Count

from Inventory.models import Project, ProjectSite, ProjectType
from Inventory.forms.project_forms import (
    ProjectCreateForm, ProjectAssignmentForm, ProjectSiteCreateForm
)
from Inventory.utils import is_management, is_superuser
import logging

logger = logging.getLogger(__name__)


class ProjectListView(LoginRequiredMixin, ListView):
    """Display all projects (with access control)"""
    model = Project
    template_name = 'Inventory/project_list.html'
    context_object_name = 'projects'
    paginate_by = 20

    def get_queryset(self):
        """Filter projects based on user role"""
        if is_superuser(self.request.user) or is_management(self.request.user):
            return Project.objects.all().order_by('-created_at')
        else:
            # Non-management users see only their managed projects
            return Project.objects.filter(
                project_manager=self.request.user
            ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = self.get_queryset()
        context['can_create'] = is_superuser(self.request.user) or is_management(self.request.user)
        context['total_projects'] = qs.count()
        context['active_projects'] = qs.filter(status='Active').count()
        # Surface the same registry the request form uses, so the user can
        # see (and extend) the canonical list. Each entry carries a count of
        # projects already on the page that belong to it — including legacy
        # values that aren't in the registry, exposed as a synthetic row.
        try:
            registry = list(
                ProjectType.objects.filter(active=True).order_by('sort_order', 'name')
            )
            counts = {
                row['project_type']: row['n']
                for row in qs.values('project_type').annotate(n=Count('id'))
            }
            registry_rows = []
            for t in registry:
                registry_rows.append({
                    'pk': t.pk,
                    'name': t.name,
                    'code': t.code,
                    'consignee_role': t.get_consignee_role_display(),
                    'count': counts.get(t.name, 0) + counts.get(t.code.upper(), 0),
                    'is_legacy': False,
                })
            registry_names = {r['name'] for r in registry_rows}
            for legacy_name, n in counts.items():
                if legacy_name and legacy_name not in registry_names:
                    registry_rows.append({
                        'pk': None,
                        'name': legacy_name,
                        'code': legacy_name.lower(),
                        'consignee_role': '—',
                        'count': n,
                        'is_legacy': True,
                    })
            context['project_type_registry'] = registry_rows
        except Exception:
            context['project_type_registry'] = []
        return context


class ProjectCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create a new project"""
    model = Project
    form_class = ProjectCreateForm
    template_name = 'Inventory/project_form.html'
    success_url = reverse_lazy('project_list')

    def test_func(self):
        """Only management users can create projects"""
        return is_superuser(self.request.user) or is_management(self.request.user)

    def form_valid(self, form):
        try:
            # Convert consultant ModelChoiceField to string
            if form.cleaned_data.get('consultant'):
                consultant_obj = form.cleaned_data['consultant']
                form.instance.consultant = consultant_obj.display_name
            else:
                form.instance.consultant = None

            response = super().form_valid(form)
            messages.success(self.request, f'Project "{self.object.name}" created successfully!')
            logger.info(f"Project {self.object.code} created by {self.request.user.username}")
            return response
        except Exception as e:
            logger.error(f"Error creating project: {str(e)}", exc_info=True)
            messages.error(self.request, f'Error creating project: {str(e)}')
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Create New Project'
        # Get unique contractor names from existing projects
        context['contractors'] = list(
            Project.objects.exclude(contractor__isnull=True).exclude(contractor='').values_list('contractor', flat=True).distinct()
        )
        return context


class ProjectDetailView(LoginRequiredMixin, DetailView):
    """View project details and sites"""
    model = Project
    template_name = 'Inventory/project_detail.html'
    context_object_name = 'project'
    slug_field = 'code'
    slug_url_kwarg = 'code'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        project = self.get_object()

        # Get project sites
        context['sites'] = project.sites.all().order_by('region', 'community')
        context['site_count'] = context['sites'].count()
        context['active_sites'] = context['sites'].filter(status='Active').count()
        context['completed_sites'] = context['sites'].filter(status='Completed').count()

        # Check if user can edit
        context['can_edit'] = (
            is_superuser(self.request.user) or
            is_management(self.request.user) or
            self.request.user == project.project_manager
        )

        return context


class ProjectUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Update project details"""
    model = Project
    form_class = ProjectCreateForm
    template_name = 'Inventory/project_form.html'
    slug_field = 'code'
    slug_url_kwarg = 'code'

    def test_func(self):
        """Only project manager or management can edit"""
        project = self.get_object()
        return (
            is_superuser(self.request.user) or
            is_management(self.request.user) or
            self.request.user == project.project_manager
        )

    def get_success_url(self):
        return reverse_lazy('project_detail', kwargs={'code': self.object.code})

    def form_valid(self, form):
        try:
            # Convert consultant ModelChoiceField to string
            if form.cleaned_data.get('consultant'):
                consultant_obj = form.cleaned_data['consultant']
                form.instance.consultant = consultant_obj.display_name
            else:
                form.instance.consultant = None

            response = super().form_valid(form)
            messages.success(self.request, f'Project "{self.object.name}" updated successfully!')
            return response
        except Exception as e:
            logger.error(f"Error updating project: {str(e)}", exc_info=True)
            messages.error(self.request, f'Error updating project: {str(e)}')
            return self.form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f'Edit Project: {self.object.name}'
        context['is_edit'] = True
        # Get unique contractor names from existing projects
        context['contractors'] = list(
            Project.objects.exclude(contractor__isnull=True).exclude(contractor='').values_list('contractor', flat=True).distinct()
        )
        return context


@login_required
def project_assignment_view(request):
    """Assign users to projects"""
    if not (is_superuser(request.user) or is_management(request.user)):
        messages.error(request, 'You do not have permission to assign projects.')
        return redirect('project_list')

    if request.method == 'POST':
        form = ProjectAssignmentForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    project = form.cleaned_data['project']
                    managers = form.cleaned_data['project_managers']
                    supervisors = form.cleaned_data['site_supervisors']

                    # Update project manager
                    if managers:
                        project.project_manager = managers[0]  # Set first manager as primary
                        project.save()

                    # Assign site supervisors to project sites
                    if supervisors:
                        sites = project.sites.all()
                        for supervisor in supervisors:
                            sites.update(site_supervisor=supervisor)

                    messages.success(
                        request,
                        f'Successfully assigned users to project "{project.name}"'
                    )
                    logger.info(
                        f"Project {project.code} assigned to managers: {[m.username for m in managers]} "
                        f"and supervisors: {[s.username for s in supervisors]}"
                    )
                    return redirect('project_detail', code=project.code)

            except Exception as e:
                logger.error(f"Error assigning project: {str(e)}", exc_info=True)
                messages.error(request, f'Error assigning project: {str(e)}')
    else:
        form = ProjectAssignmentForm()

    context = {
        'form': form,
        'page_title': 'Assign Users to Project'
    }
    return render(request, 'Inventory/project_assignment.html', context)


@login_required
def project_site_create_view(request, code):
    """Add a site to a project"""
    project = get_object_or_404(Project, code=code)

    # Check permission
    if not (is_superuser(request.user) or is_management(request.user) or request.user == project.project_manager):
        messages.error(request, 'You do not have permission to add sites to this project.')
        return redirect('project_detail', code=code)

    if request.method == 'POST':
        form = ProjectSiteCreateForm(request.POST)
        if form.is_valid():
            try:
                site = form.save(commit=False)
                site.project = project
                site.save()
                messages.success(request, f'Site "{site.name}" added to project successfully!')
                logger.info(f"Site {site.code} added to project {project.code}")
                return redirect('project_detail', code=code)
            except Exception as e:
                logger.error(f"Error creating site: {str(e)}", exc_info=True)
                messages.error(request, f'Error creating site: {str(e)}')
    else:
        form = ProjectSiteCreateForm(initial={'project': project})
        form.fields['project'].initial = project
        form.fields['project'].disabled = True  # Disable project field

    context = {
        'form': form,
        'project': project,
        'page_title': f'Add Site to {project.name}'
    }
    return render(request, 'Inventory/project_site_form.html', context)
