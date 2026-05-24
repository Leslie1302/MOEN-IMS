"""
ReleaseLetterUploadView — auto-generation single-page wizard.

User flow (restored on 2026-05-17 per user feedback):

  Step 1: Pick a request code from the dropdown.
          - System auto-creates the ReleaseLetter row, allocates an
            RE-yyyy-NNNN code, generates the memo + release letter PDFs
            with embedded QR.
          - Page reloads in step-2 mode showing download links for both
            generated documents plus the upload box for the signed scan.

  Step 2: Print, get signed, scan, then upload here.
          - System decodes any QR in the uploaded scan and verifies it
            matches the auto-allocated code.
          - Mismatch / no-QR rejects the upload (warning, doesn't crash).

This removes the "Create RL" intermediate detour. Everything happens on
one page.
"""

import json
import logging
from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import View
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.db import transaction

from Inventory.models import ReleaseLetter, MaterialOrder
from Inventory.forms import ReleaseLetterUploadForm
from Inventory.services.scan_validation import (
    decode_qr_outcome, extract_payloads, rejection_reason,
)
from Inventory.services.audit import audit
from Inventory.services.release_code import next_release_code
from Inventory.services.pdf_generator import (
    generate_release_memo, generate_release_letter,
)

logger = logging.getLogger(__name__)


def _decode_qr_payloads(file_bytes, filename):
    """Return all candidate payloads (QR + printed text). Thin wrapper."""
    payloads, _source = extract_payloads(file_bytes, filename)
    return payloads


class ReleaseLetterUploadView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Wizard for generating release documents and uploading the signed scan."""
    template_name = 'Inventory/upload_release_letter.html'
    login_url = 'login'
    permission_denied_message = "You don't have permission to upload release letters."

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        return self.request.user.groups.filter(name='Schedule Officers').exists()

    # ─────────────── helpers ───────────────

    def _matching_orders(self, request_code):
        """All un-released orders matching a request code (exact or base prefix)."""
        qs = MaterialOrder.objects.filter(
            request_code=request_code,
            release_letter__isnull=True,
        )
        if not qs.exists() and '-' in request_code:
            base = '-'.join(request_code.split('-')[:-1])
            if base:
                qs = MaterialOrder.objects.filter(
                    request_code__startswith=base,
                    release_letter__isnull=True,
                ).select_related('unit', 'user')
        return qs

    def _generate_docs_for(self, release_letter):
        """Allocate code (idempotent) + generate memo + letter PDFs."""
        if not release_letter.code:
            release_letter.code = next_release_code()
        memo_file = generate_release_memo(release_letter)
        letter_file = generate_release_letter(release_letter)
        release_letter.memo_pdf.save(memo_file.name, memo_file, save=False)
        release_letter.letter_pdf.save(letter_file.name, letter_file, save=False)
        release_letter.documents_generated_at = timezone.now()
        release_letter.documents_generated_by = self.request.user
        if release_letter.workflow_status in ('draft', None, ''):
            release_letter.workflow_status = 'memo_generated'
        release_letter.save()

    def _build_context(self, request, *, form=None, request_code=None, release_letter=None, orders=None):
        return {
            'form': form or ReleaseLetterUploadForm(user=request.user),
            'orders': orders or [],
            'selected_request_code': request_code or '',
            'release_letter': release_letter,
            'is_superuser': request.user.is_superuser,
            'is_schedule_officer': request.user.groups.filter(name='Schedule Officers').exists(),
        }

    # ─────────────── GET ───────────────

    def get(self, request):
        """Render the page. If a request_code is given AND a draft RL already
        exists for it, surface that RL so the user can continue from step 2.
        """
        request_code = (request.GET.get('request_code') or '').strip()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == 'true'

        orders = []
        release_letter = None
        if request_code:
            orders = list(self._matching_orders(request_code))
            release_letter = ReleaseLetter.objects.filter(
                request_code=request_code,
            ).order_by('-upload_time').first()

        ctx = self._build_context(
            request,
            request_code=request_code,
            orders=orders,
            release_letter=release_letter,
        )

        if is_ajax and request_code:
            return render(request, 'Inventory/includes/order_summary.html', ctx)

        return render(request, self.template_name, ctx)

    # ─────────────── POST ───────────────

    def post(self, request):
        action = (request.POST.get('action') or '').strip()
        request_code = (request.POST.get('request_code') or '').strip()

        if action == 'upload_scan':
            return self._handle_scan_upload(request)
        # Default action is generate.
        return self._handle_generate(request, request_code)

    def _handle_generate(self, request, request_code):
        """Step 1: create / find the ReleaseLetter and auto-generate PDFs."""
        if not request_code:
            messages.error(request, "Pick a request code first.")
            return redirect('release-letter-upload')

        existing = ReleaseLetter.objects.filter(
            request_code=request_code,
        ).order_by('-upload_time').first()

        try:
            with transaction.atomic():
                if existing:
                    release_letter = existing
                    # Refresh PDFs if missing.
                    if not release_letter.memo_pdf or not release_letter.letter_pdf:
                        self._generate_docs_for(release_letter)
                        messages.success(
                            request,
                            f"Refreshed documents for release event {release_letter.code}.",
                        )
                    else:
                        messages.info(
                            request,
                            f"Release event {release_letter.code} already exists. "
                            "Use the upload box below to attach the signed scan.",
                        )
                else:
                    matching_orders = self._matching_orders(request_code)
                    if not matching_orders.exists():
                        messages.error(
                            request,
                            f"No pending orders found for request code '{request_code}'. "
                            "The orders may already have a release letter attached, "
                            "or the request code was typed incorrectly.",
                        )
                        return redirect(f"{reverse('release-letter-upload')}?request_code={request_code}")

                    # Uniform project type check.
                    project_types = set(
                        matching_orders.exclude(project_type='').values_list('project_type', flat=True)
                    )
                    if len(project_types) > 1:
                        messages.error(
                            request,
                            f"Cannot create one release letter for orders across multiple project "
                            f"types: {', '.join(sorted(project_types))}. Split the request into "
                            "per-project batches.",
                        )
                        return redirect('material_orders')

                    first = matching_orders.first()
                    title = (
                        f"Release of {first.name}" if first.name
                        else f"Release for {request_code}"
                    )
                    if first.community:
                        title += f" — {first.community}"
                    total_quantity = sum((o.quantity or 0) for o in matching_orders)

                    release_letter = ReleaseLetter.objects.create(
                        request_code=request_code,
                        title=title[:200],
                        total_quantity=total_quantity,
                        material_type='Other',
                        project_type=(project_types.pop() if project_types else None),
                        workflow_status='draft',
                        uploaded_by=request.user,
                    )
                    matching_orders.update(release_letter=release_letter)
                    self._generate_docs_for(release_letter)

                    audit(
                        request.user, release_letter, 'release.letter_created',
                        f"Release letter auto-created from upload page for "
                        f"request_code={request_code} ({matching_orders.count()} orders)",
                    )
                    audit(
                        request.user, release_letter, 'release.documents_generated',
                        f"Memo + letter auto-generated for {release_letter.code}",
                    )

                    messages.success(
                        request,
                        f"Release event {release_letter.code} created and documents "
                        "generated. Download the memo and letter below, get them "
                        "signed, then upload the scan.",
                    )

            return redirect(f"{reverse('release-letter-upload')}?request_code={request_code}")

        except Exception as e:
            logger.exception("Failed to generate release documents")
            messages.error(request, f"Document generation failed: {e}")
            return redirect(f"{reverse('release-letter-upload')}?request_code={request_code}")

    def _handle_scan_upload(self, request):
        """Step 2: validate the uploaded signed scan against the QR and persist."""
        rl_id = (request.POST.get('release_letter_id') or '').strip()
        if not rl_id:
            messages.error(request, "No release letter context — generate documents first.")
            return redirect('release-letter-upload')

        release_letter = get_object_or_404(ReleaseLetter, pk=rl_id)
        uploaded = request.FILES.get('pdf_file')
        force_accept = request.POST.get('force_accept') == 'on'

        if not uploaded:
            messages.error(request, "Pick a file to upload.")
            return redirect(f"{reverse('release-letter-upload')}?request_code={release_letter.request_code}")

        if not release_letter.code:
            messages.error(
                request,
                "This release letter doesn't have a code yet — generate the documents first.",
            )
            return redirect(f"{reverse('release-letter-upload')}?request_code={release_letter.request_code}")

        uploaded.seek(0)
        file_bytes = uploaded.read()
        uploaded.seek(0)
        found_payloads, decode_source = extract_payloads(file_bytes, uploaded.name)
        expected = (release_letter.code or '').strip()
        if not found_payloads:
            qr_outcome = 'not_found'
        elif expected in found_payloads:
            qr_outcome = 'match'
        else:
            qr_outcome = 'mismatch'

        if qr_outcome != 'match':
            allow_force = request.user.is_superuser and force_accept
            if not allow_force:
                preview = ', '.join(found_payloads[:3])
                reason = rejection_reason(qr_outcome, release_letter.code, preview)
                hint = (
                    " Tick 'Force accept' below to override (audit-logged)."
                    if request.user.is_superuser
                    else " Ask a superuser to force-accept if this is correct."
                )
                messages.error(request, f"Upload rejected. {reason}{hint}")
                audit(
                    request.user, release_letter, 'release.scan_rejected',
                    f"Scan upload rejected (outcome={qr_outcome}, filename={uploaded.name})",
                )
                return redirect(f"{reverse('release-letter-upload')}?request_code={release_letter.request_code}")

            audit(
                request.user, release_letter, 'release.scan_force_accepted',
                f"Superuser force-accepted scan despite QR outcome={qr_outcome} (filename={uploaded.name})",
            )

        # Validation passed (or force-accepted). Persist.
        release_letter.pdf_file.save(uploaded.name, uploaded, save=False)
        release_letter.scan_uploaded_at = timezone.now()
        release_letter.uploaded_by = request.user
        if release_letter.workflow_status in ('draft', 'memo_generated', 'awaiting_signature'):
            release_letter.workflow_status = 'awaiting_scan_upload'
        release_letter.save()

        audit(
            request.user, release_letter, 'release.scan_uploaded',
            f"Signed scan uploaded for {release_letter.code} (qr={qr_outcome}, filename={uploaded.name})",
        )

        if qr_outcome == 'match':
            messages.success(
                request,
                f"Scan uploaded and verified against {release_letter.code}. "
                "Awaiting second-person confirmation before the release is marked Approved.",
            )
        else:
            messages.warning(
                request,
                "Scan uploaded with force-accept override. The confirming user should verify the document carefully.",
            )
        return redirect('release_letter_detail', pk=release_letter.pk)


class AdjustReleaseLetterQuantityView(LoginRequiredMixin, UserPassesTestMixin, View):
    """View for adjusting the total authorized quantity of a release letter."""
    http_method_names = ['post']

    def test_func(self):
        return self.request.user.is_superuser or self.request.user.groups.filter(name='Schedule Officers').exists()

    def post(self, request, pk):
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

        release_letter = get_object_or_404(ReleaseLetter, pk=pk)
        try:
            data = json.loads(request.body)
            new_quantity = Decimal(str(data.get('total_quantity')))
            if new_quantity < 0:
                return JsonResponse({'success': False, 'error': 'Quantity cannot be negative'}, status=400)
            old_quantity = release_letter.total_quantity
            release_letter.total_quantity = new_quantity
            release_letter.save()
            logger.info(
                f"User {request.user.username} adjusted RL {release_letter.reference_number} "
                f"quantity from {old_quantity} to {new_quantity}"
            )
            return JsonResponse({
                'success': True,
                'new_quantity': float(new_quantity),
                'new_balance': float(release_letter.balance_to_request),
                'new_fulfillment': float(release_letter.fulfillment_percentage),
            })
        except (InvalidOperation, ValueError, TypeError) as e:
            return JsonResponse({'success': False, 'error': f'Invalid quantity format: {str(e)}'}, status=400)
        except Exception as e:
            logger.error(f"Error adjusting RL quantity: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
