"""
Phase C — two-step Material Request flow forms.

Step 1 (project selection) is a tiny form with just project_type.
Step 2 (project-specific request) renders one of three subclassed forms,
each carrying the shared base fields plus per-project additions:

  - SHEP: package_number is required (read from the linked Community)
  - Cost Sharing: beneficiary_contribution captures the community's share
  - Streetlights: pole_height_m + lumen_rating capture the spec

All three save into the existing MaterialOrder model. project_type is
stored as the legacy CharField value (mapped via constants.project_type_to_charfield).
The consignee is auto-resolved from project_type + community at save time
and written to MaterialOrder.consultant or .contractor based on
ProjectType.consignee_role.
"""

from django import forms

from ..models import (
    MaterialOrder, InventoryItem, Warehouse, Community, ProjectType,
)
from ..constants import (
    PROJECT_TYPE_SHEP, PROJECT_TYPE_COST_SHARING, PROJECT_TYPE_STREETLIGHTS,
    project_type_to_charfield, active_project_types,
)
from ..services.consignee_resolver import resolve_consignee


# ---------------------------------------------------------------------------
# Step 1: project selector
# ---------------------------------------------------------------------------
class ProjectSelectorForm(forms.Form):
    """A one-field form rendered on /request-material/select/."""

    project_type = forms.ModelChoiceField(
        queryset=ProjectType.objects.none(),
        empty_label='— select project —',
        label='Project type',
        widget=forms.Select(attrs={'class': 'form-control', 'autofocus': 'autofocus'}),
        help_text='Drives which form is rendered next and where the consignee resolves to.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project_type'].queryset = active_project_types()


# ---------------------------------------------------------------------------
# Step 2: per-project request forms
# ---------------------------------------------------------------------------
class BaseProjectRequestForm(forms.ModelForm):
    """
    Shared scaffolding for SHEP / Cost Sharing / Streetlights request
    forms. Subclasses override `Meta.fields` and `additional_fields` to
    layer in project-specific inputs.
    """

    # Project type is stamped by the view; the form receives it as an
    # instance attribute, not a user-editable field.
    project_type_instance: ProjectType = None

    # Community is the canonical location source. Saving the form looks up
    # the consignee from (project_type, community) via the resolver.
    community = forms.ModelChoiceField(
        queryset=Community.objects.none(),
        empty_label='— select community —',
        label='Community',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Determines the consignee. Add the community first if it is not in the list.',
    )

    name = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all().order_by('name'),
        empty_label='— select material —',
        label='Material',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    quantity = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=0.01,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )

    warehouse = forms.ModelChoiceField(
        queryset=Warehouse.objects.all().order_by('name'),
        required=False,
        empty_label='— any warehouse —',
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        help_text='Optional. Anything the storekeeper should know.',
    )

    is_urgent = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    class Meta:
        model = MaterialOrder
        fields = ['name', 'quantity', 'community', 'warehouse', 'notes', 'is_urgent']

    def __init__(self, *args, project_type_instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.project_type_instance = project_type_instance
        if project_type_instance is not None:
            self.fields['community'].queryset = (
                Community.objects.filter(project_type=project_type_instance, is_active=True)
                .order_by('region', 'district', 'community')
            )
        else:
            self.fields['community'].queryset = Community.objects.filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        if self.project_type_instance is None:
            raise forms.ValidationError("Project type is required (set by the view).")

        # MaterialOrder.unit is a required FK. The selected InventoryItem
        # carries the unit; reject early with a clear message if the item
        # has no unit configured rather than letting an IntegrityError
        # bubble up at save time.
        item = cleaned.get('name')
        if item is not None and getattr(item, 'unit', None) is None:
            self.add_error(
                'name',
                f"The selected material '{item}' has no unit configured. "
                "Set its unit via the Inventory admin (Inventory items → edit → Unit field), "
                "or pick a different material.",
            )
        return cleaned

    def save(self, commit=True, user=None):
        instance: MaterialOrder = super().save(commit=False)

        # MaterialOrder.unit is a required FK; copy it from the selected
        # InventoryItem so the model's NOT NULL constraint is satisfied.
        # (Bugfix: the original Phase C.1 save() forgot this.)
        item = self.cleaned_data.get('name')
        if item is not None and getattr(item, 'unit', None) is not None:
            instance.unit = item.unit

        # Project type goes into the legacy CharField via the mapper.
        instance.project_type = project_type_to_charfield(self.project_type_instance)

        # Pull location fields from the selected Community so list/detail
        # views can keep using them as text.
        community = self.cleaned_data.get('community')
        if community is not None:
            instance.region = community.region
            instance.district = community.district
            instance.community = community.community
            if self.project_type_instance.code == PROJECT_TYPE_SHEP and community.package_number:
                instance.package_number = community.package_number

        # Auto-resolve the consignee. Write the display name to
        # consultant or contractor based on consignee_role so legacy
        # views render the right thing without needing a schema change.
        resolved = resolve_consignee(self.project_type_instance, community=community)
        if resolved.kind == 'consultant':
            instance.consultant = resolved.name
        elif resolved.kind == 'mp':
            instance.contractor = resolved.render()  # "Hon. Mary Asante (Ga East)"

        # Capture the requesting user as both creator and requestor handle.
        if user is not None:
            instance.user = user if not getattr(instance, 'user_id', None) else instance.user
            instance.created_by = user
            display = (user.get_full_name() or user.username) if user else ''
            if display:
                instance.requestor = display

        # Project-specific fields land in notes for now (Profile sub-models
        # are deferred to a later phase).
        extras = self.collect_project_specific_notes()
        if extras:
            existing = instance.notes or ''
            instance.notes = f"{existing}\n\n{extras}".strip() if existing else extras

        if commit:
            instance.save()
        return instance

    def collect_project_specific_notes(self) -> str:
        """Subclass hook. Returns a multi-line string of project-specific
        field values, prefixed for readability in notes."""
        return ''


class SHEPRequestForm(BaseProjectRequestForm):
    """SHEP-specific request: package_number is implicitly the community's."""
    # No extra fields beyond the base for SHEP; the community already
    # carries the package_number.

    def collect_project_specific_notes(self) -> str:
        community = self.cleaned_data.get('community')
        if community and community.package_number:
            return f"[SHEP] Package: {community.package_number}"
        return ''


class CostSharingRequestForm(BaseProjectRequestForm):
    beneficiary_contribution = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 30% community contribution agreed at meeting of 10 March 2026',
        }),
        help_text='Cost Sharing only. Brief description of the beneficiary contribution arrangement.',
    )

    def collect_project_specific_notes(self) -> str:
        contribution = self.cleaned_data.get('beneficiary_contribution', '').strip()
        if contribution:
            return f"[Cost Sharing] Beneficiary contribution: {contribution}"
        return ''


class StreetlightsRequestForm(BaseProjectRequestForm):
    pole_height_m = forms.DecimalField(
        required=False, max_digits=5, decimal_places=2, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': 'e.g. 8'}),
        help_text='Streetlights only. Pole height in metres.',
    )
    lumen_rating = forms.IntegerField(
        required=False, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '500', 'placeholder': 'e.g. 12000'}),
        help_text='Streetlights only. Lumen rating of the lamp.',
    )
    pole_type = forms.CharField(
        required=False, max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. galvanised steel, octagonal'}),
        help_text='Streetlights only. Pole material / type.',
    )

    def collect_project_specific_notes(self) -> str:
        parts = []
        if self.cleaned_data.get('pole_height_m') is not None:
            parts.append(f"Pole height: {self.cleaned_data['pole_height_m']}m")
        if self.cleaned_data.get('lumen_rating'):
            parts.append(f"Lumen rating: {self.cleaned_data['lumen_rating']}")
        if self.cleaned_data.get('pole_type'):
            parts.append(f"Pole type: {self.cleaned_data['pole_type']}")
        return f"[Streetlights] {', '.join(parts)}" if parts else ''


# Registry — view picks the right form class from the project_type code.
FORM_BY_PROJECT_CODE = {
    PROJECT_TYPE_SHEP:         SHEPRequestForm,
    PROJECT_TYPE_COST_SHARING: CostSharingRequestForm,
    PROJECT_TYPE_STREETLIGHTS: StreetlightsRequestForm,
}


def form_class_for_project(project_type):
    """Return the request form class for a given ProjectType (or code)."""
    code = project_type.code if hasattr(project_type, 'code') else project_type
    return FORM_BY_PROJECT_CODE.get(code, BaseProjectRequestForm)
