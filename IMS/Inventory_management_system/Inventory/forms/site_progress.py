"""
Consultant-facing site progress form.

Captures the physical works at a site, split by voltage class and pole
lifecycle, plus transformers and meters. The overall completion percentage is
NO LONGER entered by hand — it is derived from these works against the
community's frozen targets (see services.community_progress) and stamped on
save, so the field has been removed from this form.

Inputs (all cumulative, as-of latest update):
  * works_status                         — physical-works state machine
  * HT / LV poles erected · dressed · strung
  * HT / LV conductor used for stringing (metres)
  * transformers installed · commissioned
  * meters installed — 1-phase · 3-phase
  * progress_notes                       — short context for the map drill-down
"""

from __future__ import annotations

from django import forms

from ..models import ProjectSite


# Pole-lifecycle field groups, used for the monotonic validation
# (strung ≤ dressed ≤ erected) per voltage class.
_LIFECYCLE = {
    'HT': ('ht_poles_erected', 'ht_poles_dressed', 'ht_poles_strung'),
    'LV': ('lv_poles_erected', 'lv_poles_dressed', 'lv_poles_strung'),
}

_COUNT = lambda: forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'})
_METRES = lambda: forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '0.01'})


class SiteProgressForm(forms.ModelForm):
    """Edits the consultant-controlled works columns on a ProjectSite."""

    class Meta:
        model = ProjectSite
        fields = [
            'works_status',
            'ht_poles_erected', 'lv_poles_erected',
            'ht_poles_dressed', 'lv_poles_dressed',
            'ht_poles_strung', 'lv_poles_strung',
            'ht_conductor_strung_m', 'lv_conductor_strung_m',
            'transformers_installed', 'transformers_commissioned',
            'meters_1ph_installed', 'meters_3ph_installed',
            'progress_notes',
        ]
        widgets = {
            'works_status': forms.Select(attrs={'class': 'form-select'}),
            'ht_poles_erected': _COUNT(), 'lv_poles_erected': _COUNT(),
            'ht_poles_dressed': _COUNT(), 'lv_poles_dressed': _COUNT(),
            'ht_poles_strung':  _COUNT(), 'lv_poles_strung':  _COUNT(),
            'ht_conductor_strung_m': _METRES(), 'lv_conductor_strung_m': _METRES(),
            'transformers_installed': _COUNT(), 'transformers_commissioned': _COUNT(),
            'meters_1ph_installed': _COUNT(), 'meters_3ph_installed': _COUNT(),
            'progress_notes': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': "What's on the ground today? "
                               "e.g. 'HT strung, LV poles being dressed'.",
            }),
        }
        labels = {
            'ht_poles_erected': 'HT poles erected', 'lv_poles_erected': 'LV poles erected',
            'ht_poles_dressed': 'HT poles dressed', 'lv_poles_dressed': 'LV poles dressed',
            'ht_poles_strung':  'HT poles strung',  'lv_poles_strung':  'LV poles strung',
            'ht_conductor_strung_m': 'HT conductor used (m)',
            'lv_conductor_strung_m': 'LV conductor used (m)',
            'transformers_installed': 'Transformers installed',
            'transformers_commissioned': 'Transformers commissioned',
            'meters_1ph_installed': 'Meters installed — 1-phase',
            'meters_3ph_installed': 'Meters installed — 3-phase',
        }

    def clean(self):
        cleaned = super().clean()

        # 1. Pole lifecycle is monotonic per class: strung ≤ dressed ≤ erected.
        # A pole must be erected before it can be dressed, dressed before strung.
        for cls, (erected_f, dressed_f, strung_f) in _LIFECYCLE.items():
            erected = cleaned.get(erected_f) or 0
            dressed = cleaned.get(dressed_f) or 0
            strung  = cleaned.get(strung_f) or 0
            if dressed > erected:
                self.add_error(dressed_f,
                               f'{cls} poles dressed cannot exceed {cls} poles erected ({erected}).')
            if strung > dressed:
                self.add_error(strung_f,
                               f'{cls} poles strung cannot exceed {cls} poles dressed ({dressed}).')

        # 2. Transformers commissioned ≤ installed.
        installed = cleaned.get('transformers_installed')
        commissioned = cleaned.get('transformers_commissioned')
        if (installed is not None and commissioned is not None
                and commissioned > installed):
            self.add_error('transformers_commissioned',
                           'Transformers commissioned cannot exceed transformers installed.')

        # 3. Don't allow a works_status regression without an explanatory note.
        status = cleaned.get('works_status')
        notes = (cleaned.get('progress_notes') or '').strip()
        previous = getattr(getattr(self, 'instance', None), 'works_status', None)
        regression = (previous in ('Energised', 'Commissioned')
                      and status in ('Planned', 'In Progress'))
        if regression and not notes:
            self.add_error('progress_notes',
                           f'Add a note explaining why this site is being moved back from {previous}.')

        return cleaned
