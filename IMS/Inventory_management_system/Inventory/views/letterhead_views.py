"""
Letterhead settings — upload the Ministry letterhead and calibrate the printable
area by dragging guides over it.

The numeric insets alone are unusable in practice: nobody knows that their
letterhead's header band ends at 184pt. The visual editor shows the actual
letterhead with four draggable guides, so calibration is "line them up with the
artwork" rather than "generate a PDF, squint, adjust, repeat".

Everything is in points, the unit WeasyPrint's `@page` rule and the PyMuPDF
stamping pipeline both use, so what the officer drags to is literally what the
renderer applies.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from Inventory.models import Letterhead
from Inventory.models.letterhead import A4_HEIGHT_PT, A4_WIDTH_PT

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ALLOWED_EXTENSIONS = ('.pdf', '.png', '.jpg', '.jpeg')


def _may_manage(user):
    return (user.is_superuser
            or user.groups.filter(name__in=['Management', 'Schedule Officers']).exists())


class LetterheadSettingsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Upload + calibrate the active letterhead."""

    def test_func(self):
        return self.request.user.is_authenticated and _may_manage(self.request.user)

    def get(self, request):
        lh = Letterhead.current()
        return render(request, 'Inventory/letterhead_settings.html', {
            'letterhead': lh,
            'page_w_pt': A4_WIDTH_PT,
            'page_h_pt': A4_HEIGHT_PT,
        })

    def post(self, request):
        action = request.POST.get('action', 'insets')
        lh = Letterhead.current()

        if action == 'upload':
            return self._upload(request, lh)
        if action == 'clear':
            return self._clear(request, lh)
        return self._save_insets(request, lh)

    # -- actions -------------------------------------------------------------
    def _upload(self, request, lh):
        upload = request.FILES.get('file')
        if not upload:
            messages.error(request, "No file was selected.")
            return redirect('letterhead_settings')

        name = (upload.name or '').lower()
        if not name.endswith(ALLOWED_EXTENSIONS):
            messages.error(
                request, "Unsupported file type. Upload a PDF, PNG or JPEG scan of the letterhead.")
            return redirect('letterhead_settings')
        if upload.size > MAX_UPLOAD_BYTES:
            messages.error(
                request,
                f"That file is {upload.size // (1024 * 1024)} MB. Keep the letterhead under 15 MB — "
                "a 150–300 dpi scan of one A4 page is plenty.")
            return redirect('letterhead_settings')

        if lh is None:
            lh = Letterhead(name='Ministry Letterhead', active=True)
        lh.file = upload
        lh.pre_printed = False
        lh.save()

        if lh.file and not lh.preview_image:
            # Stamping still works without a preview; only the calibration
            # screen suffers, so this is a warning rather than a failure.
            messages.warning(
                request,
                "Letterhead saved, but a preview image could not be generated — the visual "
                "editor will be blank. Check the file opens correctly.")
        else:
            messages.success(request, "Letterhead uploaded. Now drag the guides to set the printable area.")
        return redirect('letterhead_settings')

    def _clear(self, request, lh):
        if lh and lh.file:
            lh.file.delete(save=False)
            lh.file = None
            lh.preview_image = None
            lh.save()
            messages.success(request, "Letterhead removed. Documents will use the plain text header.")
        return redirect('letterhead_settings')

    def _save_insets(self, request, lh):
        if lh is None:
            lh = Letterhead(name='Ministry Letterhead', active=True)

        # Two independent sets: the release letter's printable area inside the
        # letterhead, and the approval memo's margins on a plain sheet.
        groups = {
            'letter': ('inset_%s', "release letter"),
            'memo': ('memo_inset_%s', "approval memo"),
        }
        values = {}
        for group, (pattern, label) in groups.items():
            try:
                values[group] = {
                    edge: int(request.POST.get(pattern % edge,
                                               getattr(lh, pattern % edge)))
                    for edge in ('top', 'bottom', 'left', 'right')
                }
            except (TypeError, ValueError):
                return self._reject(
                    request, f"The {label} margins must be whole numbers of points.")

            v = values[group]
            if min(v.values()) < 0:
                return self._reject(request, f"The {label} margins cannot be negative.")
            if v['top'] + v['bottom'] >= A4_HEIGHT_PT - 60:
                return self._reject(
                    request,
                    f"The {label} top and bottom margins leave no room for text on an A4 page.")
            if v['left'] + v['right'] >= A4_WIDTH_PT - 60:
                return self._reject(
                    request,
                    f"The {label} left and right margins leave no room for text on an A4 page.")

        try:
            cont_top = int(request.POST.get('cont_inset_top', lh.cont_inset_top))
        except (TypeError, ValueError):
            return self._reject(
                request, "The continuation-page top margin must be a whole number of points.")
        if cont_top < 0 or cont_top + values['letter']['bottom'] >= A4_HEIGHT_PT - 60:
            return self._reject(
                request, "The continuation-page top margin leaves no room for text on an A4 page.")

        for edge, value in values['letter'].items():
            setattr(lh, f'inset_{edge}', value)
        lh.cont_inset_top = cont_top
        for edge, value in values['memo'].items():
            setattr(lh, f'memo_inset_{edge}', value)
        lh.pre_printed = request.POST.get('pre_printed') == 'on'
        lh.save()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'letter': lh.insets_pt, 'memo': lh.memo_insets_pt})
        messages.success(
            request, "Margins saved. They apply to the next document generated.")
        return redirect('letterhead_settings')

    def _reject(self, request, msg):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect(f"{reverse('letterhead_settings')}")
