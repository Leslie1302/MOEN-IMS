"""
Forms for logging and verifying MeterInstallation rows.

Two paths in:
  * :class:`MeterInstallationForm` -- single-row entry for a field
    officer who's logging today's installs at one community.
  * :class:`BulkMeterUploadForm` -- file picker for the XLSX bulk
    upload flow; row parsing lives in
    :func:`Inventory.views.meter_views.process_bulk_meter_upload`.

Verification (the manager step that moves a row from "reported" to
"counted") is not a form -- it's a single-button POST handled by
:func:`Inventory.views.meter_views.verify_meter_installation`. The form
classes here only cover the data-entry side.
"""

from __future__ import annotations

from django import forms

from ..models import Community, MeterInstallation, ProjectSite


class MeterInstallationForm(forms.ModelForm):
    """Single-row create/edit form for a meter install batch.

    ``project_site`` is filtered to sites in the chosen community at
    clean-time so the dropdown doesn't drown the user in sites that
    don't apply. ``reported_by`` and the verification fields are NOT on
    the form -- the view sets ``reported_by`` to ``request.user``, and a
    manager separately stamps the verify fields.
    """

    class Meta:
        model = MeterInstallation
        fields = [
            'community', 'project_site', 'phase_type', 'quantity',
            'installation_date', 'evidence_photo', 'notes',
        ]
        widgets = {
            'community':         forms.Select(attrs={'class': 'form-select', 'autofocus': 'autofocus'}),
            'project_site':      forms.Select(attrs={'class': 'form-select'}),
            'phase_type':        forms.Select(attrs={'class': 'form-select'}),
            'quantity':          forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'step': '1'}),
            'installation_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'evidence_photo':    forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'notes':             forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                                       'placeholder': 'Feeder name, transformer ID, anything '
                                                                      'the verifier should know.'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Narrow community choices to active rows. Project_site is unbounded
        # at __init__; clean() trims it to sites in the chosen community.
        self.fields['community'].queryset = (
            Community.objects.filter(is_active=True)
            .order_by('region', 'district', 'community')
        )
        self.fields['project_site'].required = False
        self.fields['project_site'].queryset = ProjectSite.objects.all()
        self.fields['project_site'].empty_label = '— optional —'

    def clean(self):
        cleaned = super().clean()
        community = cleaned.get('community')
        site = cleaned.get('project_site')
        if community and site:
            # Sites are linked to projects, not communities directly, but
            # share region/district/community name fields. Reject the
            # binding if those don't match -- caller probably picked the
            # wrong site.
            if (site.community or '').strip().lower() != (community.community or '').strip().lower():
                self.add_error(
                    'project_site',
                    f"Site '{site}' is in {site.community}, not "
                    f"{community.community}. Pick a matching site or leave blank.",
                )
        return cleaned


class BulkMeterUploadForm(forms.Form):
    """Picks the XLSX file for bulk meter ingest.

    Real parsing happens in the view; this form exists so we get the
    same upload widget and CSRF protection as every other bulk-import
    in the codebase.
    """

    file = forms.FileField(
        label='Meter installation log (.xlsx)',
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx,.xls',
        }),
        help_text='Columns: region, district, community, phase_type (1ph/3ph), '
                  'quantity, installation_date (YYYY-MM-DD), notes (optional).',
    )
