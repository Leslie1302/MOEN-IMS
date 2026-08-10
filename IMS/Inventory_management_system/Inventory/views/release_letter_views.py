"""
ReleaseLetterUploadView — the entry point to a release.

**One step, not three** (revised 2026-08-09, §2a item 7).

  Pick a request code → the system allocates RE-yyyy-NNNN, generates the memo
  and the release letter, and opens the release letter itself.

Everything after that happens on the release-letter page: read the documents,
edit the wording live, then choose the e-signature route (send for signature →
sign in-system) or the wet-signature route (print on Ministry letterhead stock
→ upload the signed scan).

Why the old three-step strip went. Steps 2 and 3 were "upload signed scan" and
"confirm & release", both of which already existed on the release-letter page
and both of which came *after* work the wizard never showed: reading the
document, and deciding which signature route to use. So the strip described a
sequence nobody followed, and its step 1 handed the officer a download link for
a document he had not read. The remaining step is the only one this page was
ever the right home for — choosing which request becomes a release.

`ponytail:` `_handle_scan_upload` below is kept, and still routed on
`action=upload_scan`, even though nothing in the template posts to it any more.
It carries the QR-matching logic that rejects a scan of the wrong document, and
`UploadSignedScanView` on the detail page is its replacement. Deleting a
validated path in the same change that reworks the flow buys nothing and would
break anything bookmarked. Remove it after one stable production cycle.
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


class BoQBlocked(Exception):
    """The release cannot be reconciled to the Bill of Quantity.

    Carries the blockers dict — over-issued and unmatched kept apart — so the
    view can attach the right remedy to each. A refusal that says only "BoQ
    problem" makes the officer hunt for which line, and the reliable outcome of
    that is a phone call to someone who suggests a workaround.
    """

    def __init__(self, blockers):
        self.blockers = blockers
        total = len(blockers['over_issued']) + len(blockers['unmatched'])
        super().__init__(f"{total} line(s) cannot be reconciled to the Bill of Quantity")


def _unsaved_blocker_message(blockers, request_code):
    """The refusal when the release was rolled back and has no page to link to.

    The over-issuance route still works — a justification is raised against the
    BoQ line, which exists independently of the release. The assistance route
    does not, because it reports against a saved release. So this names the
    lines precisely enough that an administrator can act on the description
    alone, rather than offering a link that would 404.
    """
    from django.utils.html import format_html
    from django.utils.safestring import mark_safe

    blocks = []
    if blockers['over_issued']:
        rows = []
        for line in blockers['over_issued']:
            detail = (f"{line['material']} ({line['item_code']}) at {line['community']}"
                      f" — over by {line['exceeds_by']} {line['unit']}".rstrip())
            if line['boq'] is not None:
                url = reverse('boq_overissuance_justification_create', args=[line['boq'].pk])
                detail += f' — <a href="{url}">raise a justification</a>'
            rows.append(detail)
        blocks.append("<b>Exceeds the Bill of Quantity, with no approved "
                      "justification:</b><br>" + "<br>".join(rows))

    if blockers['unmatched']:
        rows = [f"{line['material']} ({line['item_code'] or 'no item code'}) "
                f"at {line['community'] or 'no community'}"
                for line in blockers['unmatched']]
        blocks.append(
            "<b>No Bill of Quantity entry for their community:</b><br>"
            + "<br>".join(rows)
            + "<br>The Bill of Quantity for this community may not have been "
              "imported, may be under a different package number, or the item "
              "codes may not match. Ask a system administrator to check, quoting "
              f"request {request_code}.")

    return format_html("Nothing was created.<br><br>{}",
                       mark_safe("<br><br>".join(blocks)))


def _decode_qr_payloads(file_bytes, filename):
    """Return all candidate payloads (QR + printed text). Thin wrapper."""
    payloads, _source = extract_payloads(file_bytes, filename)
    return payloads


class ReleaseLetterUploadView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Start a release: pick a request code, generate both documents, open it.

    The route name (`release-letter-upload`) is unchanged on purpose — six
    templates link to it, and renaming it in the same change that reworks the
    flow would turn one reviewable diff into a hunt for NoReverseMatch.
    """
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

    @staticmethod
    def _base_code(request_code):
        """Collapse a bulk per-row code to its batch base.

        Single requests use REQ-YYYYMMDD-NNNNNN (3 segments). A bulk upload
        suffixes each row: REQ-YYYYMMDD-NNNNNN-1, -2, … (4 segments). Stripping
        the trailing numeric segment ONLY when there are more than 3 segments
        yields the batch base for bulk rows while leaving single requests (and
        the numeric date/random parts) untouched. So a whole bulk batch is
        released under ONE letter, and a single request stays on its own.
        """
        code = (request_code or '').strip()
        parts = code.split('-')
        if len(parts) > 3 and parts[-1].isdigit():
            return '-'.join(parts[:-1])
        return code

    def _matching_orders(self, request_code):
        """All un-released orders for a request code's batch (base + suffixed rows)."""
        from django.db.models import Q
        base = self._base_code(request_code)
        return MaterialOrder.objects.filter(
            Q(request_code=base) | Q(request_code__startswith=f"{base}-"),
            release_letter__isnull=True,
        ).select_related('unit', 'user')

    def _generate_docs_for(self, release_letter):
        """Allocate code (idempotent) + generate memo + letter PDFs.

        Raises `BoQBlocked` when any line either exceeds the approved Bill of
        Quantity without an approved justification, or has no Bill of Quantity
        entry at all. The same gate guards `GenerateReleaseDocumentsView`;
        enforced on only one of the two doors it would not be a control at all,
        and this is the door most releases come through.
        """
        from Inventory.services.reconciliation import generation_blockers, has_blockers

        blockers, _result = generation_blockers(release_letter)
        if has_blockers(blockers):
            raise BoQBlocked(blockers)

        if not release_letter.code:
            release_letter.code = next_release_code()
        memo_file = generate_release_memo(release_letter)
        letter_file = generate_release_letter(release_letter)
        release_letter.memo_pdf.save(memo_file.name, memo_file, save=False)
        release_letter.letter_pdf.save(letter_file.name, letter_file, save=False)

        # Version every generation, exactly as GenerateReleaseDocumentsView does.
        #
        # This path did not, and once it became the primary way documents get
        # made, every release started life at version 0. That is not cosmetic:
        # a DocumentSignature records the version it signed and a
        # DocumentDispatch records the version it emailed, so the version is how
        # the system answers "which bytes did this person actually see". At 0 the
        # answer is a lie in a specific direction — `apply_signature` coerces a
        # falsy version to 1, so the signature would claim v1 on a document the
        # record calls v0, and a later regenerate would produce a second v1.
        release_letter.memo_version = (release_letter.memo_version or 0) + 1
        release_letter.letter_version = (release_letter.letter_version or 0) + 1

        release_letter.documents_generated_at = timezone.now()
        release_letter.documents_generated_by = self.request.user
        if release_letter.workflow_status in ('draft', None, ''):
            release_letter.workflow_status = 'memo_generated'
        release_letter.save()

    def _build_context(self, request, *, form=None, request_code=None, release_letter=None, orders=None):
        from Inventory.models import Signatory
        active = Signatory.objects.filter(active=True)

        # If a bulk upload stashed a designation hint on the first order
        # of this batch (marker: "[SignatoryHint] memo=<pk>; letter=<pk>"),
        # surface it so the dropdowns can pre-select the right option.
        memo_prefill_pk = ''
        letter_prefill_pk = ''
        hint_warnings = []
        if orders:
            for o in orders:
                note = (o.notes or '')
                if '[SignatoryHint]' not in note:
                    continue
                # Single line: [SignatoryHint] memo=12; letter=7
                for line in note.splitlines():
                    if not line.startswith('[SignatoryHint]'):
                        continue
                    body = line[len('[SignatoryHint]'):].strip()
                    for part in body.split(';'):
                        k, _, v = part.strip().partition('=')
                        if not v:
                            continue
                        if v.startswith('RAW:'):
                            hint_warnings.append((k, v[4:]))
                            continue
                        if k == 'memo':
                            memo_prefill_pk = v
                        elif k == 'letter':
                            letter_prefill_pk = v
                break

        # Sibling release letters share a request_code when a mixed-project
        # batch was auto-split. Surface them so the page can render a
        # switcher; exclude the currently-active one to keep the widget tidy.
        sibling_release_letters = []
        if request_code:
            sibling_qs = ReleaseLetter.objects.filter(
                request_code=request_code,
            ).order_by('upload_time')
            if release_letter is not None:
                sibling_qs = sibling_qs.exclude(pk=release_letter.pk)
            sibling_release_letters = list(sibling_qs)

        return {
            'form': form or ReleaseLetterUploadForm(user=request.user),
            'orders': orders or [],
            'selected_request_code': request_code or '',
            'release_letter': release_letter,
            'sibling_release_letters': sibling_release_letters,
            'is_superuser': request.user.is_superuser,
            'is_schedule_officer': request.user.groups.filter(name='Schedule Officers').exists(),
            # Designation-led pickers on Step 1. Filtered to officers flagged
            # eligible for each document type; the user picks a title and the
            # system attaches the matching name automatically.
            'memo_signatories':   active.filter(is_default_for_release_memo=True).order_by('title'),
            'letter_signatories': active.filter(is_default_for_release_letter=True).order_by('title'),
            # Kept for backwards-compat with any other consumers of this ctx.
            'signatories': active.order_by('title'),
            # Hints carried over from a bulk upload (Excel signatory columns).
            'memo_signatory_prefill_pk':   memo_prefill_pk,
            'letter_signatory_prefill_pk': letter_prefill_pk,
            'signatory_hint_warnings':     hint_warnings,
        }

    # ─────────────── GET ───────────────

    def get(self, request):
        """Render the page. If a request_code is given AND a draft RL already
        exists for it, surface that RL so the user can continue from step 2.

        When a single request_code spans multiple project types, the
        generate step auto-splits into one ReleaseLetter per type. We pick
        the one the user asked for via `?rl=<pk>` (so the sibling-letter
        links on the page can deep-link), falling back to the most recent.
        """
        request_code = self._base_code((request.GET.get('request_code') or '').strip())
        rl_pk        = (request.GET.get('rl') or '').strip()
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.GET.get('ajax') == 'true'

        orders = []
        release_letter = None
        if request_code:
            orders = list(self._matching_orders(request_code))
            siblings_qs = ReleaseLetter.objects.filter(
                request_code=request_code,
            ).order_by('upload_time')
            if rl_pk:
                release_letter = siblings_qs.filter(pk=rl_pk).first()
            if release_letter is None:
                release_letter = siblings_qs.order_by('-upload_time').first()

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

        # Collapse a bulk per-row code to its batch base so the entire batch is
        # released under ONE letter + memo. Single requests are unchanged.
        request_code = self._base_code(request_code)

        existing = ReleaseLetter.objects.filter(
            request_code=request_code,
        ).order_by('-upload_time').first()

        # Named before the branches rather than derived after them. The two
        # paths below set different subsets of these, and working out where to
        # land by subtracting one case from another is how a landing page ends
        # up being chosen by whichever branch happened to run last.
        release_letter = None
        created_letters = []

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
                            f"Release event {release_letter.code} already exists — opening it. "
                            "Use 'Generate memo & letter' there if the documents need "
                            "refreshing.",
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

                    # Carry through any per-event overrides from Step 1. These
                    # apply to EVERY split release letter — overrides are about
                    # who signs, not which project the materials belong to.
                    from Inventory.models import Signatory
                    memo_to        = (request.POST.get('memo_to_override') or '').strip()
                    memo_from      = (request.POST.get('memo_from_override') or '').strip()
                    memo_sig_id    = (request.POST.get('memo_signatory_override') or '').strip()
                    letter_sig_id  = (request.POST.get('letter_signatory_override') or '').strip()
                    memo_signatory   = Signatory.objects.filter(pk=memo_sig_id).first() if memo_sig_id else None
                    letter_signatory = Signatory.objects.filter(pk=letter_sig_id).first() if letter_sig_id else None

                    # Group orders by project_type and create one ReleaseLetter
                    # per group. Mixed batches used to be rejected with the
                    # "Split the request into per-project batches" error — we
                    # now do the split automatically so the user keeps moving.
                    # Blank project_type rows are bundled into their own group
                    # so they don't get silently dropped.
                    project_types = sorted({
                        (o.project_type or '') for o in matching_orders
                    })

                    for ptype in project_types:
                        if ptype:
                            group = matching_orders.filter(project_type=ptype)
                        else:
                            group = matching_orders.filter(project_type='')
                        if not group.exists():
                            continue

                        first = group.first()
                        title = (
                            f"Release of {first.name}" if first.name
                            else f"Release for {request_code}"
                        )
                        if first.community:
                            title += f" — {first.community}"
                        if len(project_types) > 1 and ptype:
                            # Disambiguate sibling letters in admin and lists.
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
                            memo_to_override=memo_to,
                            memo_from_override=memo_from,
                            memo_signatory_override=memo_signatory,
                            letter_signatory_override=letter_signatory,
                        )
                        # Attach this group's orders (use the queryset, not
                        # matching_orders, so siblings keep their own slice).
                        group.update(release_letter=release_letter)
                        self._generate_docs_for(release_letter)

                        audit(
                            request.user, release_letter, 'release.letter_created',
                            f"Release letter auto-created for request_code={request_code} "
                            f"project_type={ptype or '(none)'} ({group.count()} orders)"
                            + (" — split from mixed-project batch" if len(project_types) > 1 else ""),
                        )
                        audit(
                            request.user, release_letter, 'release.documents_generated',
                            f"Memo + letter auto-generated for {release_letter.code}",
                        )
                        created_letters.append(release_letter)

                    # Pick the newest one as the "current" letter the page
                    # surfaces; siblings show up in the sibling widget.
                    release_letter = created_letters[-1] if created_letters else None

                    if len(created_letters) > 1:
                        codes = ', '.join(rl.code for rl in created_letters)
                        messages.success(
                            request,
                            f"This batch spanned {len(created_letters)} project types — "
                            f"created {len(created_letters)} release events ({codes}). "
                            "Each has its own memo and letter; open them from the list.",
                        )
                    elif release_letter:
                        messages.success(
                            request,
                            f"Release event {release_letter.code} created and both documents "
                            "generated. Read them below and edit the wording if you need to, "
                            "then send for signature or print for a wet signature.",
                        )

            # ── Land on the release letter, not back here ────────────────────
            #
            # The wizard used to return the officer to a step-2 upload box,
            # which asked him to print, sign, scan and upload before he had ever
            # read the document he was about to put the Ministry's name on. The
            # detail page is where he reads it, edits the wording live, and then
            # chooses e-signature or wet signature — which is the actual order
            # of the work, and the reason the middle steps of the strip were
            # always skipped in practice.
            if len(created_letters) > 1:
                # Two landing pages is no landing page. The list names them all.
                return redirect('release_letter_list')
            if release_letter is not None:
                return redirect('release_letter_detail', pk=release_letter.pk)
            return redirect(f"{reverse('release-letter-upload')}?request_code={request_code}")

        except BoQBlocked as blocked:
            # Raised inside the atomic block, so the ReleaseLetter this would
            # have created is rolled back with it. That is deliberate: a release
            # event that cannot produce documents is a half-thing that shows up
            # in lists and confuses everyone who finds it.
            #
            # But the rollback takes the "contact system admin" route with it —
            # that view needs a saved release to report against. So the unmatched
            # case is described here in full, with the request code, and the
            # officer can raise it from the release once one exists. Naming the
            # lines matters more than the link.
            from Inventory.views.release_document_views import blocker_message

            messages.error(request, blocker_message(release_letter, blocked.blockers)
                           if release_letter and release_letter.pk
                           else _unsaved_blocker_message(blocked.blockers, request_code))
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

        # Verification policy (revised so the page never loops forever):
        #   match      -> accept, verified.
        #   mismatch   -> a DIFFERENT code was decoded, so this is almost
        #                 certainly the wrong document. Reject (a superuser can
        #                 still force-accept).
        #   not_found  -> nothing could be decoded. This happens whenever the
        #   / error       host has no QR-decoder library installed (the decode
        #                 step is optional) or the scan's QR is unreadable.
        #                 Previously this REJECTED and redirected back, so on a
        #                 host without decoders EVERY upload bounced — an
        #                 infinite loop. We now accept it with a warning; the
        #                 mandatory second-person confirmation (step 3) is the
        #                 real gate before the release is approved.
        if qr_outcome == 'mismatch' and not (request.user.is_superuser and force_accept):
            preview = ', '.join(found_payloads[:3])
            reason = rejection_reason('mismatch', release_letter.code, preview)
            hint = (
                " Tick 'Force accept' below to override (audit-logged)."
                if request.user.is_superuser
                else " Ask a superuser to force-accept if this is correct."
            )
            messages.error(request, f"Upload rejected. {reason}{hint}")
            audit(
                request.user, release_letter, 'release.scan_rejected',
                f"Scan upload rejected (outcome=mismatch, filename={uploaded.name})",
            )
            return redirect(f"{reverse('release-letter-upload')}?request_code={release_letter.request_code}")

        if qr_outcome != 'match' and request.user.is_superuser and force_accept:
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
        elif qr_outcome == 'mismatch':
            messages.warning(
                request,
                "Scan uploaded with force-accept override despite a code mismatch. "
                "The confirming user must verify the document carefully.",
            )
        else:
            messages.warning(
                request,
                f"Scan uploaded for {release_letter.code}, but the verification code "
                "could not be read automatically. The confirming user must verify the "
                "document before the release is approved.",
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
