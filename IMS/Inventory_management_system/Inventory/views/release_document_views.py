"""
Phase F.1 — release-side document workflow views.

For now this exposes a single action: generate the approval memo and
release letter PDFs for an existing ReleaseLetter row. The button lives
on the release-letter detail page; clicking it allocates the
RE-yyyy-NNNN code (if not yet set), generates both PDFs, attaches them
to the row, and advances the workflow_status to 'memo_generated'.

Subsequent Phase F rounds will add:
  - upload_signed_scan (two-person review)
  - confirm_scan
  - mark_released
  - void / reissue
  - email reminders for stuck states
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView

from Inventory.models import ReleaseLetter, MaterialOrder
from Inventory.services.pdf_generator import generate_release_memo, generate_release_letter
from Inventory.services.release_code import next_release_code
from Inventory.services.audit import audit
from Inventory.services.scan_validation import (
    decode_qr_outcome,
    extract_payloads,
    rejection_reason,
)

logger = logging.getLogger(__name__)


class ReleaseLetterDetailView(LoginRequiredMixin, DetailView):
    """
    Detail page for a single ReleaseLetter. Reuses the existing
    release_letter_detail.html template (which assumes `release_letter` in
    context). Phase F.1 added the project_type pill + consignee block to
    that template, plus the document generation buttons added in this
    round.
    """
    model = ReleaseLetter
    template_name = 'Inventory/release_letter_detail.html'
    context_object_name = 'release_letter'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rl = self.object
        ctx['workflow_status_display'] = rl.get_workflow_status_display() if rl.workflow_status else ''
        ctx['can_generate_documents'] = (
            self.request.user.is_superuser
            or self.request.user.groups.filter(name__in=['Schedule Officers', 'Management']).exists()
        )
        ctx['pipeline_step'] = rl.get_pipeline_step()
        return ctx


class UploadSignedScanView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Phase F.2 — upload the signed scan of the release letter. Validates the
    upload by extracting any QR code in the image/PDF and matching it
    against the release event's `code`. Mismatched QR is rejected.

    Workflow effect:
      - On successful upload: workflow_status -> 'awaiting_scan_upload'
        (intermediate state meaning "scan is on file, awaiting second-person
        confirmation"), scan_uploaded_at / pdf_file populated.
      - On confirmation by a *different* user: workflow_status -> 'approved'.
    """
    http_method_names = ['post']

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        return self.request.user.groups.filter(
            name__in=['Schedule Officers', 'Management', 'Stores Management']
        ).exists()

    def post(self, request, pk):
        release_letter = get_object_or_404(ReleaseLetter, pk=pk)
        uploaded = request.FILES.get('signed_scan')
        force_accept = request.POST.get('force_accept') == 'on'

        if not uploaded:
            messages.error(request, "No file uploaded.")
            return redirect('release_letter_detail', pk=pk)

        if not release_letter.code:
            messages.error(
                request,
                "Cannot validate scan: this release event has no code yet. "
                "Click 'Generate memo & letter' first so the system mints a code.",
            )
            return redirect('release_letter_detail', pk=pk)

        # STRICT validation: decode the QR in memory before deciding to save.
        # Only 'match' is accepted by default; mismatch / missing-QR / decode
        # errors REJECT the upload outright. Superusers may force-accept via
        # the 'Force accept' checkbox.
        uploaded.seek(0)
        file_bytes = uploaded.read()
        uploaded.seek(0)
        # Decode once, surface both outcome and the actual payloads so the
        # mismatch error can show the user what came back vs. what was expected.
        found_payloads, decode_source = extract_payloads(file_bytes, uploaded.name)
        expected = (release_letter.code or '').strip()
        if not expected:
            qr_outcome = 'not_found'
        elif not found_payloads:
            qr_outcome = 'not_found'
        elif expected in found_payloads:
            qr_outcome = 'match'
        else:
            qr_outcome = 'mismatch'

        if qr_outcome != 'match':
            allow_force = request.user.is_superuser and force_accept
            if not allow_force:
                found_preview = ', '.join(found_payloads[:3]) if found_payloads else ''
                reason_text = rejection_reason(qr_outcome, release_letter.code, found_preview)
                override_hint = (
                    " Tick 'Force accept (bypass QR check)' below and re-upload "
                    "to override this rejection."
                    if request.user.is_superuser
                    else " Ask a superuser if you need to override this check."
                )
                messages.error(request, f"Upload rejected. {reason_text}{override_hint}")
                audit(request.user, release_letter, 'release.scan_rejected',
                      f"Scan upload rejected (outcome={qr_outcome}, filename={uploaded.name})")
                return redirect('release_letter_detail', pk=pk)
            # Superuser force-accept path -- log it loudly.
            audit(request.user, release_letter, 'release.scan_force_accepted',
                  f"Superuser force-accepted scan despite QR outcome={qr_outcome} "
                  f"(filename={uploaded.name})")

        # Validation passed (or was force-accepted). Persist the scan.
        release_letter.pdf_file.save(uploaded.name, uploaded, save=False)
        release_letter.scan_uploaded_at = timezone.now()
        release_letter.uploaded_by = request.user  # records who uploaded the scan, used for the two-person rule below
        if release_letter.workflow_status in ('draft', 'memo_generated', 'awaiting_signature'):
            release_letter.workflow_status = 'awaiting_scan_upload'
        release_letter.save()

        audit(request.user, release_letter, 'release.scan_uploaded',
              f"Signed scan uploaded for {release_letter.code} (qr={qr_outcome}, filename={uploaded.name})")

        if qr_outcome == 'match':
            messages.success(
                request,
                f"Scan uploaded and QR verified against {release_letter.code}. "
                "Awaiting second-person confirmation before the release is marked Approved.",
            )
        else:
            messages.warning(
                request,
                "Scan uploaded with force-accept override. QR validation was bypassed; "
                "the confirming user should verify the document carefully.",
            )

        return redirect('release_letter_detail', pk=pk)


class ConfirmSignedScanView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Phase F.2 — second-person confirmation of an uploaded signed scan.
    Enforces the two-person rule: the confirming user must differ from the
    uploader. On confirmation, workflow_status advances to 'approved'.
    """
    http_method_names = ['post']

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        return self.request.user.groups.filter(
            name__in=['Schedule Officers', 'Management', 'Stores Management']
        ).exists()

    def post(self, request, pk):
        release_letter = get_object_or_404(ReleaseLetter, pk=pk)

        if not release_letter.pdf_file:
            messages.error(request, "Cannot confirm: no signed scan has been uploaded.")
            return redirect('release_letter_detail', pk=pk)

        # Two-person rule: confirmer must differ from uploader.
        if release_letter.uploaded_by_id == request.user.id and not request.user.is_superuser:
            messages.error(
                request,
                "Two-person rule: the user who uploaded the scan cannot also confirm it. "
                "Ask a colleague to confirm.",
            )
            return redirect('release_letter_detail', pk=pk)

        release_letter.scan_confirmed_by = request.user
        release_letter.scan_confirmed_at = timezone.now()
        release_letter.workflow_status = 'approved'
        release_letter.save()

        audit(request.user, release_letter, 'release.scan_confirmed',
              f"Two-person confirm: {release_letter.code} -> approved "
              f"(uploader={release_letter.uploaded_by_id}, confirmer={request.user.id})")

        messages.success(
            request,
            f"Release event {release_letter.code} confirmed and marked Approved. "
            "Materials can now be physically released from MMU.",
        )
        return redirect('release_letter_detail', pk=pk)


class MarkReleasedView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Marks an approved release event as physically released (terminal happy-path state)."""
    http_method_names = ['post']

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        return self.request.user.groups.filter(
            name__in=['Store Officers', 'Stores Management', 'Management']
        ).exists()

    def post(self, request, pk):
        release_letter = get_object_or_404(ReleaseLetter, pk=pk)
        if release_letter.workflow_status != 'approved':
            messages.error(request, "Cannot mark released: workflow must be in 'Approved' state first.")
            return redirect('release_letter_detail', pk=pk)
        release_letter.workflow_status = 'released'
        release_letter.save()
        audit(request.user, release_letter, 'release.marked_released',
              f"Materials physically released for {release_letter.code}")
        messages.success(request, f"Release event {release_letter.code} marked Released.")
        return redirect('release_letter_detail', pk=pk)


class CreateReleaseLetterFromRequestView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    Replaces the legacy /release-letter/upload/?request_code=X page that
    was riddled with field-name bugs. Given a request_code, finds all
    matching MaterialOrders without a release letter, validates they
    share the same project type, creates a new ReleaseLetter in 'draft'
    workflow status (code auto-allocated by save()), links the orders,
    and redirects to the detail page where the user can hit
    'Generate memo & letter'.

    Idempotent on retry: if a draft ReleaseLetter already exists for this
    request_code, the user is redirected to it instead of creating
    another. POST-only to avoid GET-with-side-effect.
    """
    http_method_names = ['post', 'get']  # GET allowed for the existing <a href> button

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        return self.request.user.groups.filter(
            name__in=['Schedule Officers', 'Management', 'Stores Management']
        ).exists()

    def get(self, request):
        return self._handle(request)

    def post(self, request):
        return self._handle(request)

    def _handle(self, request):
        request_code = (request.GET.get('request_code') or request.POST.get('request_code') or '').strip()
        if not request_code:
            messages.error(request, "No request code supplied.")
            return redirect('material_orders')

        # Reject date-only codes (REQ-YYYYMMDD) — they have only 2 segments and
        # would match every order from that day via a startswith query. A valid
        # request code always has at least 3 segments: REQ-YYYYMMDD-XXXXXX.
        if len(request_code.split('-')) < 3:
            messages.error(
                request,
                f"'{request_code}' looks like a date-only prefix, not a specific request code. "
                "Use the full request code (e.g. REQ-20260604-XXXXXX) or the bulk base code "
                "for a batch (e.g. REQ-20260604-XXXXXX, whose sub-orders end in -1, -2, …)."
            )
            return redirect('material_orders')

        try:
            with transaction.atomic():
                # Find Release-type orders matching the request code that don't yet have a release letter.
                # Receipt orders are explicitly excluded — they never need a release letter or memo.
                orders = MaterialOrder.objects.filter(
                    request_code=request_code,
                    request_type='Release',
                    release_letter__isnull=True,
                )

                # Fall back to sub-code match for bulk batches.
                # e.g. if request_code='REQ-20260604-XXXXXX', look for orders
                # with codes 'REQ-20260604-XXXXXX-1', 'REQ-20260604-XXXXXX-2', …
                #
                # IMPORTANT: do NOT strip a path segment and use the result as
                # the prefix. 'REQ-20260604-XXXXXX'.split('-')[:-1] yields
                # 'REQ-20260604' which matches every order from that day.
                if not orders.exists():
                    orders = MaterialOrder.objects.filter(
                        request_code__startswith=f"{request_code}-",
                        request_type='Release',
                        release_letter__isnull=True,
                    )

                if not orders.exists():
                    # Idempotent retry: maybe a draft release letter already exists for this code.
                    existing = ReleaseLetter.objects.filter(
                        request_code=request_code,
                        workflow_status__in=('draft', 'memo_generated', 'awaiting_signature', 'awaiting_scan_upload'),
                    ).first()
                    if existing:
                        messages.info(
                            request,
                            f"A release letter already exists for {request_code}. "
                            "Opening it now — use 'Generate memo & letter' if you need to refresh the PDFs.",
                        )
                        return redirect('release_letter_detail', pk=existing.pk)
                    messages.warning(
                        request,
                        f"No pending material orders found for request code '{request_code}'. "
                        "The orders may already have a release letter attached.",
                    )
                    return redirect('material_orders')

                # Mixed-project batches used to be rejected with "Split the
                # request into per-project batches." We now auto-split:
                # one ReleaseLetter per project_type, each with its own
                # subset of orders. Blank project_type rows are bundled into
                # their own group so they don't get silently dropped.
                project_types = sorted({
                    (o.project_type or '') for o in orders
                })

                created_letters = []
                for ptype in project_types:
                    if ptype:
                        group = orders.filter(project_type=ptype)
                    else:
                        group = orders.filter(project_type='')
                    if not group.exists():
                        continue

                    first = group.first()
                    if first.name:
                        title = f"Release of {first.name}"
                    else:
                        title = f"Release for {request_code}"
                    if first.community:
                        title += f" — {first.community}"
                    if len(project_types) > 1 and ptype:
                        title += f" [{ptype}]"

                    total_quantity = sum((o.quantity or 0) for o in group)

                    release_letter = ReleaseLetter.objects.create(
                        request_code=request_code,
                        title=title[:200],
                        total_quantity=total_quantity,
                        material_type='Other',
                        project_type=(ptype or None),
                        workflow_status='draft',
                        uploaded_by=request.user,
                    )
                    group.update(release_letter=release_letter)
                    created_letters.append(release_letter)

                    audit(
                        request.user, release_letter, 'release.letter_created',
                        f"Release letter created for {request_code} "
                        f"project_type={ptype or '(none)'} (orders linked: {group.count()})"
                        + (" — split from mixed-project batch" if len(project_types) > 1 else ""),
                    )

            if len(created_letters) > 1:
                codes = ', '.join((rl.code or f"#{rl.pk}") for rl in created_letters)
                messages.success(
                    request,
                    f"This batch spanned {len(created_letters)} project types — "
                    f"created {len(created_letters)} release letters ({codes}). "
                    "Open any from the list to generate its memo + letter.",
                )
                return redirect('material_orders')
            else:
                release_letter = created_letters[0]
                messages.success(
                    request,
                    f"Release letter created for {request_code}. "
                    "Click 'Generate memo & letter' to produce the PDFs.",
                )
                return redirect('release_letter_detail', pk=release_letter.pk)

        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create ReleaseLetter for request_code=%s", request_code)
            messages.error(request, f"Could not create the release letter: {exc}")
            return redirect('material_orders')


class GenerateReleaseDocumentsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """
    POST endpoint that produces the memo + release letter for a release
    event. Idempotent for the code allocation (won't re-mint if already
    set) but each call regenerates the PDFs to reflect any data changes.

    Permission: Schedule Officers and superusers.
    """
    http_method_names = ['post']

    def test_func(self):
        if not self.request.user.is_authenticated:
            return False
        if self.request.user.is_superuser:
            return True
        return self.request.user.groups.filter(name__in=['Schedule Officers', 'Management']).exists()

    def post(self, request, pk):
        release_letter = get_object_or_404(ReleaseLetter, pk=pk)

        try:
            with transaction.atomic():
                # Allocate the code on first generation. Idempotent.
                if not release_letter.code:
                    release_letter.code = next_release_code()

                # Generate both PDFs from the current ReleaseLetter state.
                memo_file = generate_release_memo(release_letter)
                letter_file = generate_release_letter(release_letter)

                # Persist on the row. Saving the FileField triggers actual
                # write to MEDIA_ROOT.
                release_letter.memo_pdf.save(memo_file.name, memo_file, save=False)
                release_letter.letter_pdf.save(letter_file.name, letter_file, save=False)

                release_letter.documents_generated_at = timezone.now()
                release_letter.documents_generated_by = request.user

                # Advance workflow status forward only -- don't regress an
                # already-approved release back to memo_generated.
                if release_letter.workflow_status in ('draft', 'memo_generated'):
                    release_letter.workflow_status = 'memo_generated'

                release_letter.save()

            audit(request.user, release_letter, 'release.documents_generated',
                  f"Memo + letter generated for {release_letter.code}")

            messages.success(
                request,
                f"Generated documents for release event {release_letter.code}. "
                "Print the letter, get it signed by the Chief Director, then upload the signed scan.",
            )

        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to generate release documents for ReleaseLetter pk=%s", pk)
            messages.error(request, f"Document generation failed: {exc}")

        return redirect('release_letter_detail', pk=release_letter.pk)
