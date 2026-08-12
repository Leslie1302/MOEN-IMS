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
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.views import View
from django.views.generic import DetailView

from django.contrib.auth.models import User

from Inventory.models import ReleaseLetter, MaterialOrder, Signatory
from Inventory.services.document_dispatch import send_release_documents, DispatchError
from Inventory.services.signing import (
    apply_signature, can_sign, rebuild_signed_pdf, signed_pdf_is_stale, SigningError,
)
from Inventory.services.approvals import (
    is_signatory, may_view_queue, notify_next_signatory,
    send_for_signature, SendForSignatureError,
)
from Inventory.services.urgency import can_declare_urgent
from Inventory.services.pdf_generator import generate_release_memo, generate_release_letter
from Inventory.services.document_render import (
    render_document_html, context_fingerprint, weasyprint_status, RendererUnavailable,
)
from Inventory.services.html_sanitize import sanitize_document_html
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
        ctx['signatories'] = Signatory.objects.filter(active=True).order_by('name')
        # WYSIWYG state: is each document hand-edited, and has the underlying
        # data moved since that edit (in which case the stored wording is stale)?
        ctx['memo_edited'] = bool(rl.memo_html)
        ctx['letter_edited'] = bool(rl.letter_html)
        ctx['memo_drift'] = rl.document_drift('memo')
        ctx['letter_drift'] = rl.document_drift('letter')
        # Surface a missing PDF renderer up front. Without this the only clue
        # is a flash message after clicking Generate, and the stale PDFs below
        # look like the new template failing to apply.
        ctx['renderer_ok'], ctx['renderer_detail'] = weasyprint_status()
        # Recipient picker + history for the "Send documents" panel.
        ctx['dispatch_users'] = (User.objects.filter(is_active=True)
                                 .exclude(email='').order_by('first_name', 'username'))
        ctx['dispatches'] = rl.dispatches.all()[:8]

        # Signing state, per document. `can_sign` returns the reason a user may
        # not sign, which the panel shows rather than simply hiding the button —
        # "awaiting the Ag. Director" is more useful than a missing control.
        signing = {}
        for kind in ('memo', 'letter'):
            allowed, step, reason = can_sign(self.request.user, rl, kind)
            signing[kind] = {
                'allowed': allowed, 'step': step, 'reason': reason,
                'complete': rl.signing_complete(kind),
                'locked': getattr(rl, f'{kind}_locked', False),
                'signatures': rl.signatures_for(kind),
                'next': rl.next_signing_step(kind),
                # Signed while the renderer was down: the record says signed,
                # but the stored PDF still shows a blank signature line.
                'stale_pdf': signed_pdf_is_stale(rl, kind),
            }
        ctx['signing'] = signing
        ctx['can_sign_any'] = any(s['allowed'] for s in signing.values())

        # The release-wide next step, spanning both documents — the same value
        # that drives the queue and the notification email, so the officer's
        # "who has it" and the signatory's "what is waiting for me" cannot
        # disagree. `signing[kind]['next']` above answers the narrower question
        # and is None whenever the turn belongs to the other document.
        ctx['next_step'] = rl.next_signing_step()
        ctx['signing_complete'] = rl.signing_complete()
        # Generation notifies nobody. Handing the release to the first
        # signatory is a separate, explicit act — otherwise every draft pesters
        # the Ag. Director and people learn to ignore the emails.
        ctx['can_send_for_signature'] = bool(
            ctx['can_generate_documents'] and ctx['next_step'] is not None
            and getattr(rl, f"{ctx['next_step'].document_kind}_pdf", None))
        # Only the letter carries a rendered letterhead, so only the letter has
        # a meaningfully different print-on-stock render.
        ctx['letter_plain_print_url'] = (
            f"{reverse('release_letter_preview', args=[rl.pk])}?plain=1")
        # Any lock at all means Generate must not be offered — regenerating
        # would put an existing signature over new content.
        ctx['any_locked'] = rl.memo_locked or rl.letter_locked
        ctx['locked_kinds'] = [k for k in ('memo', 'letter')
                               if getattr(rl, f'{k}_locked', False)]

        # ── Signatory-side controls (Phases 3-5) ────────────────────────────
        # For a signatory this page is a read-only archive, not a workspace:
        # `can_generate_documents` already excludes them from every editing
        # control, and this flag lets the template say so rather than simply
        # presenting a page with the buttons missing.
        ctx['viewer_is_signatory'] = is_signatory(self.request.user)
        ctx['can_call_officer'] = may_view_queue(self.request.user)
        allowed, refusal = can_declare_urgent(self.request.user, rl)
        ctx['can_declare_urgent'] = allowed
        ctx['urgency_refusal'] = refusal
        ctx['discussions'] = rl.discussion_requests.select_related(
            'raised_by', 'officer')[:8]
        return ctx


def _can_generate(user):
    return (user.is_superuser
            or user.groups.filter(name__in=['Schedule Officers', 'Management']).exists())


class AdjustReleaseDocumentsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Save the officer's document adjustments (TO/FROM/signatory/notes) before
    generating. Fields mirror HTMS's referenceNo/addressee/notes overrides."""
    def test_func(self):
        return self.request.user.is_authenticated and _can_generate(self.request.user)

    def post(self, request, pk):
        rl = get_object_or_404(ReleaseLetter, pk=pk)
        rl.memo_to_override = (request.POST.get('memo_to_override') or '').strip()
        rl.memo_from_override = (request.POST.get('memo_from_override') or '').strip()
        rl.memo_notes = (request.POST.get('memo_notes') or '').strip()
        rl.letter_notes = (request.POST.get('letter_notes') or '').strip()
        rl.memo_signatory_override = _signatory_or_none(request.POST.get('memo_signatory_override'))
        rl.letter_signatory_override = _signatory_or_none(request.POST.get('letter_signatory_override'))
        rl.save(update_fields=[
            'memo_to_override', 'memo_from_override', 'memo_notes', 'letter_notes',
            'memo_signatory_override', 'letter_signatory_override',
        ])
        messages.success(request, "Document adjustments saved. Preview updated.")
        return redirect(f"{reverse('release_letter_detail', args=[pk])}#adjust")


def _signatory_or_none(raw):
    if not raw:
        return None
    return Signatory.objects.filter(pk=raw).first()


class _DocumentPreviewBase(LoginRequiredMixin, View):
    """Live HTML preview — the exact template the PDF is rendered from.

    Query params:
      ?edit=1      make #doc-body contenteditable and load the editor bridge.
                   Only honoured for users who may generate documents.
      ?original=1  ignore a stored hand-edit and show the data-driven template
                   (used by the "revert" confirm step).
      ?plain=1     omit the rendered letterhead, for printing onto Ministry
                   letterhead stock (the wet-signature route).

    `plain` is deliberately a render of the same document rather than a second
    stored file. The alternative — keeping a no-letterhead PDF alongside the
    real one — gives the Ministry two documents that can disagree, and the one
    that gets wet-signed and filed would be the one nobody verified.
    """
    kind = None

    def get(self, request, pk):
        rl = get_object_or_404(ReleaseLetter, pk=pk)
        # A locked document is frozen: editing it would put the officer's
        # changes under a signature that was given for different content.
        locked = getattr(rl, f'{self.kind}_locked', False)
        edit = (request.GET.get('edit') == '1'
                and _can_generate(request.user)
                and not locked)
        use_stored = request.GET.get('original') != '1'
        plain = request.GET.get('plain') == '1'
        # Editing a letterhead-less render would show the officer a page whose
        # margins are not the ones his edit will print in. One or the other.
        if plain:
            edit = False
        html = render_document_html(rl, self.kind, edit_mode=edit,
                                    use_stored=use_stored, plain=plain)
        resp = HttpResponse(html)
        # The preview is user-authored HTML in a same-origin frame; keep it out
        # of caches and refuse to let it be framed by anything but this site.
        resp['Cache-Control'] = 'no-store'
        resp['X-Frame-Options'] = 'SAMEORIGIN'
        return resp


class MemoPreviewView(_DocumentPreviewBase):
    kind = 'memo'


class LetterPreviewView(_DocumentPreviewBase):
    kind = 'letter'


class SaveDocumentHtmlView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Store the officer's hand-edited document body.

    The posted HTML comes from a `contenteditable` region, so it is passed
    through the allowlist sanitiser before it touches the database — it will be
    re-rendered in a same-origin iframe, where a surviving `<script>` would run.

    A fingerprint of the underlying release data is recorded alongside it, so
    the detail page can tell the officer when the materials or signatory moved
    after they wrote their version.
    """
    http_method_names = ['post']

    def test_func(self):
        return self.request.user.is_authenticated and _can_generate(self.request.user)

    def post(self, request, pk, kind):
        if kind not in ('memo', 'letter'):
            raise Http404("Unknown document type.")
        rl = get_object_or_404(ReleaseLetter, pk=pk)

        if getattr(rl, f'{kind}_locked', False):
            return JsonResponse(
                {'ok': False,
                 'error': f"This {kind} has been signed and is locked. Void and reissue "
                          "the release if it must change."},
                status=409)

        cleaned = sanitize_document_html(request.POST.get('html', ''))
        if not cleaned:
            return JsonResponse(
                {'ok': False, 'error': "Nothing to save — the document body came through empty."},
                status=400)

        setattr(rl, f'{kind}_html', cleaned)
        setattr(rl, f'{kind}_html_edited_at', timezone.now())
        setattr(rl, f'{kind}_html_edited_by', request.user)
        setattr(rl, f'{kind}_html_fingerprint', context_fingerprint(rl, kind))
        rl.save(update_fields=[
            f'{kind}_html', f'{kind}_html_edited_at',
            f'{kind}_html_edited_by', f'{kind}_html_fingerprint',
        ])

        audit(request.user, rl, 'release.document_edited',
              f"{kind.title()} body hand-edited for {rl.code or rl.request_code}")
        logger.info("ReleaseLetter pk=%s %s_html edited by %s", pk, kind, request.user)
        return JsonResponse({'ok': True, 'kind': kind,
                             'message': f"{kind.title()} saved. Re-generate to mint the PDF."})


class RevertDocumentHtmlView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Discard a hand-edit and go back to the data-driven template."""
    http_method_names = ['post']

    def test_func(self):
        return self.request.user.is_authenticated and _can_generate(self.request.user)

    def post(self, request, pk, kind):
        if kind not in ('memo', 'letter'):
            raise Http404("Unknown document type.")
        rl = get_object_or_404(ReleaseLetter, pk=pk)

        setattr(rl, f'{kind}_html', '')
        setattr(rl, f'{kind}_html_edited_at', None)
        setattr(rl, f'{kind}_html_edited_by', None)
        setattr(rl, f'{kind}_html_fingerprint', '')
        rl.save(update_fields=[
            f'{kind}_html', f'{kind}_html_edited_at',
            f'{kind}_html_edited_by', f'{kind}_html_fingerprint',
        ])

        audit(request.user, rl, 'release.document_reverted',
              f"{kind.title()} reverted to the generated template for {rl.code or rl.request_code}")
        messages.success(request, f"{kind.title()} reverted to the generated version.")
        return redirect(f"{reverse('release_letter_detail', args=[pk])}#adjust")


class SignDocumentView(LoginRequiredMixin, View):
    """Apply a drawn signature to the memo or letter.

    Permission is not group-based: the only person who may sign is the one named
    on the next outstanding `SigningStep`. That is checked inside the service,
    which also enforces chain order and the lock on signed documents.
    """
    http_method_names = ['post']

    def post(self, request, pk, kind):
        if kind not in ('memo', 'letter'):
            raise Http404("Unknown document type.")
        rl = get_object_or_404(ReleaseLetter, pk=pk)

        # Return the signer to the page they signed from. A flag, not a URL:
        # accepting a redirect target from a POST body is an open redirect, and
        # there are exactly two callers, so there is nothing to generalise.
        if request.POST.get('from') == 'signing_page':
            back = reverse('sign_release', args=[pk])
        else:
            back = f"{reverse('release_letter_detail', args=[pk])}#sign"

        try:
            signature = apply_signature(
                rl, request.user, kind,
                request.POST.get('signature', ''),
                ip_address=_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
            )
        except SigningError as exc:
            messages.error(request, str(exc))
            return redirect(back)

        audit(request.user, rl, 'release.document_signed',
              f"{kind} signed by {signature.signatory_name} "
              f"({signature.signatory_title}) token {signature.verification_token}")

        # Report the release-wide next step, not this document's. After the
        # memo is signed the next step is usually the LETTER, so asking
        # next_signing_step(kind) would return None and lose the handoff.
        nxt = rl.next_signing_step()
        if nxt is None:
            messages.success(
                request,
                f"{kind.title()} signed. The signing chain is complete and the "
                "documents are locked — void and reissue if they must change. "
                "MMU has been given advance notice to prepare the materials; "
                "they may not release them until the signed scan is on file.")
        else:
            # Hand off automatically. The step-1-to-step-2 handoff is the one
            # that otherwise sits in somebody's head and loses a week.
            notify_next_signatory(rl, sender=request.user)
            who = nxt.signatory.title if nxt.signatory else 'the next signatory'
            messages.success(
                request,
                f"{kind.title()} signed. It now goes to {who} for the "
                f"{nxt.get_document_kind_display().lower()}.")

        return redirect(back)


class RebuildSignedDocumentView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Re-render a signed document's PDF so it shows its signatures.

    Repair path for a document signed while the PDF renderer was unavailable:
    the signature was recorded and the document locked, but the stored PDF still
    shows a blank signature line, and the lock rightly blocks Generate.

    This is safe on a locked document because it is not a regeneration from
    changed data — it re-renders the same content and adds the signature block
    that should already have been there. The lock protects content, and content
    does not change here.
    """
    http_method_names = ['post']

    def test_func(self):
        return self.request.user.is_authenticated and _can_generate(self.request.user)

    def post(self, request, pk, kind):
        if kind not in ('memo', 'letter'):
            raise Http404("Unknown document type.")
        rl = get_object_or_404(ReleaseLetter, pk=pk)

        if not rl.signatures_for(kind).exists():
            messages.error(request, f"The {kind} has no signatures to rebuild.")
            return redirect(f"{reverse('release_letter_detail', args=[pk])}#sign")

        try:
            rebuild_signed_pdf(rl, kind)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Rebuild failed for ReleaseLetter %s (%s)", pk, kind)
            messages.error(request, f"The {kind} could not be rebuilt: {exc}")
            return redirect(f"{reverse('release_letter_detail', args=[pk])}#sign")

        audit(request.user, rl, 'release.document_rebuilt',
              f"{kind} PDF re-minted with its signatures")
        messages.success(request, f"The {kind} has been rebuilt and now shows its signatures.")
        return redirect(f"{reverse('release_letter_detail', args=[pk])}#sign")


def _blocking_message(release_letter, request):
    """Refuse generation while an unjustified over-issuance stands. → True if blocked.

    Shared by both generation paths — the detail page's Generate button and the
    request-code page that creates a release — because a control enforced on one
    of two doors is not a control.

    The message names every offending line and links straight to the
    justification form for it. A refusal that says only "over-issuance detected"
    leaves the officer hunting through the BoQ for which line, and the reliable
    outcome of that is a phone call to someone who will suggest a workaround.
    """
    from Inventory.services.reconciliation import generation_blockers, has_blockers

    # Non-conventional programmes (Streetlights / Cost-sharing) are handled in
    # reconciliation.generation_blockers itself — their unmatched lines are
    # authorised by the release, not blockers — so both generation doors get the
    # policy with no per-view logic here.
    try:
        blockers, _result = generation_blockers(release_letter)
    except Exception as exc:  # noqa: BLE001
        # A gate that cannot be evaluated must not silently pass. But neither
        # should a reconciliation bug make every release ungeneratable — so log
        # loudly and let it through, and the memo's own conditional wording will
        # not claim the release reconciles.
        logger.exception("BoQ gate failed for ReleaseLetter %s: %s",
                         release_letter.pk, exc)
        return False

    if not has_blockers(blockers):
        return False

    messages.error(request, blocker_message(release_letter, blockers))
    return True


def blocker_message(release_letter, blockers):
    """The refusal, with the right remedy attached to each kind of blocker.

    Two remedies, never mixed. An over-issuance is the officer's to clear —
    raise a justification, get it approved. An unmatched line is not: the BoQ
    itself is wrong or missing, which is above his desk, so that one routes to a
    system administrator. Offering "raise a justification" against a material
    with no BoQ row would send him to a form that cannot be filled in.
    """
    from django.urls import reverse as _reverse

    blocks = []

    if blockers['over_issued']:
        rows = []
        for line in blockers['over_issued']:
            detail = (f"{line['material']} ({line['item_code']}) at {line['community']}"
                      f" — over by {line['exceeds_by']} {line['unit']}".rstrip())
            if line['boq'] is not None:
                url = _reverse('boq_overissuance_justification_create', args=[line['boq'].pk])
                detail += f' — <a href="{url}">raise a justification</a>'
            rows.append(detail)
        blocks.append(
            f"<b>{len(blockers['over_issued'])} line(s) exceed the approved Bill of "
            "Quantity</b> with no approved over-issuance justification. Raise one for "
            "each and have it approved by the Director of Power.<br>"
            + "<br>".join(rows))

    if blockers['unmatched']:
        rows = [f"{line['material']} ({line['item_code'] or 'no item code'}) "
                f"at {line['community'] or 'no community'}"
                for line in blockers['unmatched']]
        url = _reverse('release_boq_assistance', args=[release_letter.pk])
        blocks.append(
            f"<b>{len(blockers['unmatched'])} line(s) have no Bill of Quantity entry</b> "
            "for their community, so the system cannot establish what authorises this "
            "release. This is not something you can correct from here.<br>"
            + "<br>".join(rows)
            + f'<br><a href="{url}">Contact system admin for assistance</a>')

    return format_html(
        "Documents were not generated.<br><br>{}",
        mark_safe("<br><br>".join(blocks)))


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        # App Service sits behind a proxy; the client is the first entry.
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class BoQAssistanceView(LoginRequiredMixin, UserPassesTestMixin, View):
    """The door out of an unmatched Bill of Quantity line.

    GET shows a short confirmation with the lines named; POST sends it. A block
    with no route out produces either a release that stalls until somebody
    chases it, or an officer who finds a way round the check — and the second
    one is off the record by definition.
    """
    http_method_names = ['get', 'post']
    template_name = 'Inventory/boq_assistance.html'

    def test_func(self):
        return self.request.user.is_authenticated and _can_generate(self.request.user)

    def get(self, request, pk):
        from Inventory.services.boq_assistance import admin_recipients
        from Inventory.services.reconciliation import generation_blockers

        rl = get_object_or_404(ReleaseLetter, pk=pk)
        blockers, _result = generation_blockers(rl)
        users, extra = admin_recipients()
        return render(request, self.template_name, {
            'release_letter': rl,
            'unmatched': blockers['unmatched'],
            'recipients': users,
            'extra_emails': extra,
        })

    def post(self, request, pk):
        from Inventory.services.boq_assistance import AssistanceError, request_assistance

        rl = get_object_or_404(ReleaseLetter, pk=pk)
        try:
            recipients, emailed = request_assistance(
                rl, request.user, note=request.POST.get('note', ''))
        except AssistanceError as exc:
            messages.error(request, str(exc))
            return redirect('release_letter_detail', pk=pk)

        names = ", ".join(
            (r.get_full_name() or r.username) if hasattr(r, 'username') else str(r)
            for r in recipients)
        if emailed:
            messages.success(
                request,
                f"Assistance requested. {names} has been notified in the system and "
                f"emailed. The release stays exactly where it is.")
        else:
            # The in-app notification is the record; the email is the courtesy.
            messages.warning(
                request,
                f"Assistance requested and {names} notified in the system, but no email "
                "could be sent from your mailbox. Sign in with Microsoft if you want "
                "emails to leave from you.")
        return redirect('release_letter_detail', pk=pk)


class ReconciliationReportView(LoginRequiredMixin, DetailView):
    """The standalone BoQ reconciliation, computed live on every view.

    Read-open to any signed-in user, like the release itself: this is the
    evidence that a release is within contract, and the people most likely to
    want it — audit, a signatory checking after the fact, the consultant whose
    package it draws on — are not all in one group.

    Not stored, not versioned, not signed. A reconciliation frozen into a PDF
    would go stale the moment the BoQ moved and would still carry the authority
    of a filed document, which is worse than having none.
    """
    model = ReleaseLetter
    template_name = 'Inventory/reconciliation_report.html'
    context_object_name = 'release_letter'

    def get_context_data(self, **kwargs):
        from Inventory.services.reconciliation import reconcile, summary_sentence

        ctx = super().get_context_data(**kwargs)
        result = reconcile(self.object)
        ctx['reconciliation'] = result
        ctx['reconciliation_summary'] = summary_sentence(result)
        ctx['generated_at'] = timezone.now()
        return ctx


class SendForSignatureView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Hand the release to the next signatory. The officer's explicit act.

    Separate from generation on purpose (§2a(ii)). If generating notified the
    Ag. Director, he would be emailed about every half-finished draft, and the
    predictable result is that he stops reading the emails — at which point the
    signature queue has quietly died and nobody can point to when.

    Nothing is attached. The email carries a link into the system, because a PDF
    that goes out and comes back signed proves a round trip nobody observed,
    whereas signing here records who signed, when, from what address and against
    which version.
    """
    http_method_names = ['post']

    def test_func(self):
        return self.request.user.is_authenticated and _can_generate(self.request.user)

    def post(self, request, pk):
        rl = get_object_or_404(ReleaseLetter, pk=pk)
        resend = bool(rl.sent_for_signature_at)

        try:
            step, notification = send_for_signature(rl, request.user)
        except SendForSignatureError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('release_letter_detail', args=[pk])}#sign")

        who = step.signatory.title if step.signatory else (
            step.user.get_full_name() or step.user.username)
        kind = step.get_document_kind_display().lower()

        audit(request.user, rl, 'release.sent_for_signature',
              f"{'Re-sent' if resend else 'Sent'} to {who} for the {kind}")

        # Say plainly that the notification is in-app and the email is a
        # courtesy. If Graph is unreachable the signatory still has the item in
        # his queue, and the officer should not conclude the handover failed.
        messages.success(
            request,
            f"{'Reminder sent' if resend else 'Sent'} to {who} for the {kind}. "
            "It is in their approvals queue, and they have been emailed a link — "
            "the documents themselves stay in the system.")
        return redirect(f"{reverse('release_letter_detail', args=[pk])}#sign")


class SendReleaseDocumentsView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Email the memo and/or letter to chosen users and/or typed addresses.

    Graph sends on behalf of the signed-in officer, so the message leaves their
    own mailbox and the recipient can just reply. Every attempt is recorded as a
    DocumentDispatch — including failures, so a release that was never sent is
    distinguishable from one where the send was rejected.
    """
    http_method_names = ['post']

    def test_func(self):
        return self.request.user.is_authenticated and _can_generate(self.request.user)

    def post(self, request, pk):
        rl = get_object_or_404(ReleaseLetter, pk=pk)

        user_ids = request.POST.getlist('recipient_users')
        users = list(User.objects.filter(pk__in=user_ids, is_active=True)) if user_ids else []
        # The free-text field accepts several addresses separated by comma,
        # semicolon or newline — officers paste from Outlook.
        raw = (request.POST.get('recipient_emails') or '').replace(';', ',').replace('\n', ',')
        extra = [part.strip() for part in raw.split(',') if part.strip()]

        try:
            dispatch = send_release_documents(
                rl, sender=request.user, users=users, extra_emails=extra,
                include_memo=request.POST.get('include_memo') == 'on',
                include_letter=request.POST.get('include_letter') == 'on',
                subject=request.POST.get('subject'),
                message=request.POST.get('message', ''),
            )
        except DispatchError as exc:
            messages.error(request, str(exc))
            return redirect(f"{reverse('release_letter_detail', args=[pk])}#send")

        audit(request.user, rl, 'release.documents_sent',
              f"{dispatch.documents_label} emailed to {dispatch.recipients}")
        messages.success(
            request,
            f"Sent the {dispatch.documents_label} to {dispatch.recipients}.")
        return redirect(f"{reverse('release_letter_detail', args=[pk])}#send")


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

        # Validation passed (or was force-accepted). Persist the scan under a
        # storage-safe name — the raw scanner filename can be rejected by the
        # Azure Blob backend (production), surfacing as a bare "Bad Request (400)".
        from Inventory.services.scan_validation import safe_scan_filename
        try:
            release_letter.pdf_file.save(
                safe_scan_filename(uploaded.name, release_letter.code), uploaded, save=False)
        except Exception as exc:  # noqa: BLE001 — storage failure must not 400/500 opaquely
            logger.error("Scan save failed for ReleaseLetter %s (file=%s): %s",
                         release_letter.pk, uploaded.name, exc, exc_info=True)
            messages.error(
                request,
                "The scan could not be saved. Please try again, or upload a smaller "
                "PDF/image. If it keeps failing, contact a system administrator.")
            return redirect('release_letter_detail', pk=pk)
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

        # A confirmed wet signature closes the document exactly as an in-system
        # signature does. Without this the letter stayed editable after it had
        # been signed on paper — an officer could alter wording the Chief
        # Director had already put his name to, and the stored PDF would no
        # longer match the scan sitting beside it.
        release_letter.memo_locked = True
        release_letter.letter_locked = True
        release_letter.save()

        audit(request.user, release_letter, 'release.scan_confirmed',
              f"Two-person confirm: {release_letter.code} -> approved, documents locked "
              f"(uploader={release_letter.uploaded_by_id}, confirmer={request.user.id})")

        messages.success(
            request,
            f"Release event {release_letter.code} confirmed and marked Approved. "
            "The documents are now locked. Materials can be physically released "
            "from MMU — mark the release once they have gone.",
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

        # A signed document is frozen. Regenerating it would reproduce the
        # signature over content the signatory never saw — so refuse rather than
        # silently re-sign. Changing a signed document means void and reissue.
        locked = [kind for kind in ('memo', 'letter')
                  if getattr(release_letter, f'{kind}_locked', False)]
        if locked:
            messages.error(
                request,
                f"The {' and '.join(locked)} has been signed and is locked. "
                "Void and reissue this release if the document must change — "
                "regenerating would place an existing signature over new content.")
            return redirect('release_letter_detail', pk=pk)

        # An over-issuance with no approved justification stops generation.
        #
        # This does not prevent the release — it routes it through the control
        # built for exactly this case. The officer raises a justification, the
        # Director of Power approves it, and generation proceeds. What it does
        # prevent is a memo going to a signatory asserting that a release sits
        # within contract when it does not.
        blocked = _blocking_message(release_letter, request)
        if blocked:
            return redirect('release_letter_detail', pk=pk)

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

                # Version every generation so a dispatch can record precisely
                # which document a recipient received.
                release_letter.memo_version = (release_letter.memo_version or 0) + 1
                release_letter.letter_version = (release_letter.letter_version or 0) + 1

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

        except RendererUnavailable as exc:
            # Distinct from a data error: nothing is wrong with this release,
            # the host simply cannot render PDFs. Say so plainly, and say that
            # the documents still on the record are the OLD ones — otherwise
            # the officer re-reads a stale PDF and concludes the template
            # never changed.
            logger.error("Renderer unavailable generating ReleaseLetter pk=%s: %s", pk, exc)
            messages.error(
                request,
                f"{exc} The documents shown below are the previously generated ones "
                "and have not been updated.")

        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to generate release documents for ReleaseLetter pk=%s", pk)
            messages.error(
                request,
                f"Document generation failed: {exc} The previously generated documents "
                "are unchanged.")

        return redirect('release_letter_detail', pk=release_letter.pk)
