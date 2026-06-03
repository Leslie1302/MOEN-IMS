"""
Project management forms for creating and assigning projects
"""

from django import forms
from django.contrib.auth.models import User, Group
from Inventory.models import Project, ProjectSite, ProjectType
from Inventory.models.people import ProjectConsultant


def get_management_users():
    """Get users in Management group(s), handling multiple possible group names"""
    management_groups = Group.objects.filter(
        name__in=['Management', 'management', 'Project Manager', 'project manager']
    )
    if management_groups.exists():
        return User.objects.filter(groups__in=management_groups).distinct()
    # Fallback: return superusers if no management group exists
    return User.objects.filter(is_superuser=True)


def get_supervisor_users():
    """Get users in supervisor/store officer group(s)"""
    supervisor_groups = Group.objects.filter(
        name__in=['Store Officer', 'Store Officers', 'Storekeeper', 'Storekeepers',
                  'Stores Officer', 'Stores Officers', 'Site Supervisor', 'Site Supervisors']
    )
    if supervisor_groups.exists():
        return User.objects.filter(groups__in=supervisor_groups).distinct()
    return User.objects.none()


class ProjectCreateForm(forms.ModelForm):
    """Form for creating a new project"""

    project_manager = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        help_text="Select the user responsible for managing this project",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    consultant = forms.ModelChoiceField(
        queryset=ProjectConsultant.objects.filter(active=True),
        required=False,
        help_text="Select the primary consultant for the project",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    contractor = forms.CharField(
        required=False,
        help_text="Primary contractor name",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Primary contractor name',
            'list': 'contractor-list'
        })
    )

    class Meta:
        model = Project
        fields = [
            'name', 'code', 'description', 'project_type', 'phase',
            'status', 'project_manager', 'consultant', 'contractor',
            'start_date', 'planned_end_date', 'total_budget'
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Project name'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Unique project code (e.g., SHEP-4)',
                'pattern': '[A-Z0-9-]+'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Detailed project description',
                'rows': 4
            }),
            'project_type': forms.Select(attrs={'class': 'form-select'}),
            'phase': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Phase (e.g., Phase 1, SHEP-4)'
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'planned_end_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'total_budget': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Budget amount',
                'step': '0.01'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Override the consultant field to display the consultant name instead of the model
        if self.instance and self.instance.pk:
            # If editing, try to find the ProjectConsultant that matches the consultant text
            try:
                consultant = ProjectConsultant.objects.get(name=self.instance.consultant)
                self.fields['consultant'].initial = consultant
            except (ProjectConsultant.DoesNotExist, ProjectConsultant.MultipleObjectsReturned):
                # If no match, keep the text value
                pass

        # Drive the project_type dropdown from the same ProjectType registry
        # the material-request form uses, so the two views stop disagreeing.
        # Legacy values that are no longer in the registry (e.g. "Turnkey")
        # are surfaced as a single fallback choice so existing records stay
        # editable.
        try:
            active_types = list(
                ProjectType.objects.filter(active=True).order_by('sort_order', 'name')
            )
            choices = [(t.name, t.name) for t in active_types]
            legacy_value = (self.instance.project_type if self.instance else None)
            if legacy_value and legacy_value not in [c[0] for c in choices]:
                choices.append((legacy_value, f"{legacy_value} (legacy)"))
            self.fields['project_type'].widget.choices = (
                [('', '— select project type —')] + choices
            )
        except Exception:
            # If the ProjectType table isn't ready yet (e.g. during initial
            # migration) leave the model's static choices in place.
            pass


class ProjectAssignmentForm(forms.Form):
    """Form for assigning users to projects"""

    project = forms.ModelChoiceField(
        queryset=Project.objects.all(),
        required=True,
        help_text="Select project to assign users to",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    project_managers = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        help_text="Select project managers",
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'})
    )

    site_supervisors = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        help_text="Select site supervisors",
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate the user choices when the form is instantiated rather than
        # when this module is imported. get_management_users() and
        # get_supervisor_users() execute database queries; evaluating them at
        # class-definition time made the module impossible to import before the
        # database had been migrated.
        self.fields['project_managers'].queryset = get_management_users()
        self.fields['site_supervisors'].queryset = get_supervisor_users()


class ProjectSiteCreateForm(forms.ModelForm):
    """Form for adding sites to a project"""

    class Meta:
        model = ProjectSite
        fields = [
            'project', 'name', 'code', 'region', 'district', 'community',
            'gps_coordinates', 'site_supervisor', 'status',
            'start_date', 'planned_completion_date'
        ]
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Site name or identifier'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Site code'
            }),
            'region': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Region name'
            }),
            'district': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'District name'
            }),
            'community': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Community name (optional)',
                'required': False
            }),
            'gps_coordinates': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'GPS coordinates (optional)',
                'required': False
            }),
            'site_supervisor': forms.Select(attrs={
                'class': 'form-select',
                'required': False
            }),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': False
            }),
            'planned_completion_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': False
            }),
        }
