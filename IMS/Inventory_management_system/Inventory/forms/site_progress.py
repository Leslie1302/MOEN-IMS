"""
Consultant-facing site progress form.

Lets the consultant update three fields on a single ProjectSite:

  * ``works_status``     -- the physical-works state machine
                            (Planned / In Progress / Energised / Commissioned).
  * ``progress_percent`` -- 0-100, free-text gut-feel reading; feeds the
                            Ghana map's headline access rate in the
                            interim before Energy Commission engagement.
  * ``progress_notes``   -- short context the map's drill-down surfaces.

The view stamps ``progress_updated_at`` and ``progress_updated_by`` from
the request, so they're not user-editable.
"""

from __future__ import annotations

from django import forms

from ..models import ProjectSite


class SiteProgressForm(forms.ModelForm):
    """Edits the consultant-controlled progress columns on a ProjectSite."""

    class Meta:
        model = ProjectSite
        fields = [
            'works_status', 'progress_percent', 'progress_notes',
            'meters_1ph_installed', 'meters_3ph_installed',
            'poles_erected', 'conductor_laid_m',
            'transformers_installed', 'transformers_commissioned',
        ]
        widgets = {
            'works_status':     forms.Select(attrs={'class': 'form-select'}),
            'progress_percent': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'max': '100', 'step': '5',
            }),
            'progress_notes':   forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': "What's actually on the ground today? "
                               "e.g. 'poles erected, conductors next week'.",
            }),
            'meters_1ph_installed': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'step': '1',
            }),
            'meters_3ph_installed': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'step': '1',
            }),
            'poles_erected': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'step': '1',
            }),
            'conductor_laid_m': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'step': '0.01',
            }),
            'transformers_installed': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'step': '1',
            }),
            'transformers_commissioned': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0', 'step': '1',
            }),
        }
        labels = {
            'meters_1ph_installed': 'Meters installed — 1-phase',
            'meters_3ph_installed': 'Meters installed — 3-phase',
            'poles_erected': 'Poles erected',
            'conductor_laid_m': 'Conductor / cable laid (m)',
            'transformers_installed': 'Transformers installed',
            'transformers_commissioned': 'Transformers commissioned',
        }

    def clean_progress_percent(self):
        value = self.cleaned_data.get('progress_percent') or 0
        if not 0 <= value <= 100:
            raise forms.ValidationError('Percent must be between 0 and 100.')
        return value

    def clean(self):
        """Cross-field guard: don't allow a state regression without a note.

        Going from 'Energised' back to 'In Progress' without writing
        progress_notes is almost always a typo. Require an explanation
        so the audit trail makes sense.
        """
        cleaned = super().clean()
        status = cleaned.get('works_status')
        notes = (cleaned.get('progress_notes') or '').strip()
        instance = getattr(self, 'instance', None)
        previous = getattr(instance, 'works_status', None) if instance else None

        regression = (
            previous in ('Energised', 'Commissioned')
            and status in ('Planned', 'In Progress')
        )
        if regression and not notes:
            self.add_error(
                'progress_notes',
                'Add a note explaining why this site is being moved back '
                f'from {previous}.',
            )

        installed = cleaned.get('transformers_installed')
        commissioned = cleaned.get('transformers_commissioned')
        if (installed is not None and commissioned is not None
                and commissioned > installed):
            self.add_error(
                'transformers_commissioned',
                'Transformers commissioned cannot exceed transformers installed.',
            )
        return cleaned
