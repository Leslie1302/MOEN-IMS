"""
Phases 3-5 — the signatory's side of the release workflow.

  * `/approvals/`                     the queue: what is waiting for me
  * `/release-letters/<pk>/sign/`     the signing page: both documents, one panel
  * call officer for discussion       a conversation, not a rejection
  * treat as urgent                   a management directive to MMU
  * `/reports/urgent-releases/`       so urgency is a trend, not a finding

The permission model here is deliberately not group-based. Who may sign is the
signing chain; who may declare urgency is the signing chain. Groups say what
kind of job someone does, and a signature is about a named office, not a job
kind.
"""

import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView

from Inventory.models import ReleaseLetter, SigningStep
from Inventory.services.approvals import (
    is_signatory, may_view_queue, preparing_officer, queue_for,
)
from Inventory.services.audit import audit
from Inventory.services.discussion import (
    DiscussionError, call_officer, request_correction,
)
from Inventory.services.document_render import letterhead_applies
from Inventory.services.signing import can_sign
from Inventory.services.urgency import (
    UrgencyError, advance_notice_queryset, declare_urgent, urgent_queryset,
)

logger = logging.getLogger(__name__)


class ApprovalQueueView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """The signatory's landing point.

    Three sections, in the order a signatory cares about them: what is waiting
    for me, what is waiting for someone else, and what I have signed recently.
    The middle section matters more than it looks — without it a signatory who
    is second in the chain sees an empty page and concludes the system is broken,
    when in fact the memo simply has not reached them yet.

    The queue shows **both documents** on every entry. Whoever signs is entitled
    to the whole pack: the Ag. Director is approving that this letter goes out,
    and the Chief Director signs the letter on the authority of that memo.
    """
    template_name = 'Inventory/approvals.html'

    def test_func(self):
        return may_view_queue(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.info(self.request,
                          "The approvals queue is for officers named on the signing chain.")
            return redirect('dashboard')
        return super().handle_no_permission()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(queue_for(self.request.user))
        ctx['is_signatory'] = is_signatory(self.request.user)
        # Management supervises the chain without being on it. Saying so keeps
        # an empty "awaiting me" section from reading as a fault.
        ctx['oversight_only'] = not ctx['is_signatory']
        ctx['advance_notice'] = advance_notice_queryset()[:10]
        return ctx


class SigningPageView(LoginRequiredMixin, DetailView):
    """One release, both documents, one signature panel.

    A signatory used to be sent to `release_letter_detail#sign` — the schedule
    officer's workspace, ~1,900 lines of generate / edit / adjust / dispatch
    controls, with the thing he came for anchored somewhere down the middle.
    Everything on it was readable by him and almost none of it was his to touch.

    This page is the counterpart to the approvals queue: the queue answers
    *what is waiting for me*, this answers *here it is, sign it*. It carries no
    control that is not a signatory's to use, which is what §2a(iii) means by
    the dashboard becoming an archive — the fix is a page that fits the reader,
    not a page with its buttons hidden.

    **Both documents, always.** The Ag. Director is approving that this letter
    goes out; the Chief Director signs the letter on the authority of that memo.
    Showing a signatory only the page he puts his name on asks him to certify
    half a decision.

    Read access is open to any signed-in user. The Sign button is not — that is
    `can_sign`, which enforces the chain. A senior officer hitting a permission
    wall on his own Ministry's paperwork is a worse failure than his seeing a
    release early.
    """
    model = ReleaseLetter
    template_name = 'Inventory/signing_page.html'
    context_object_name = 'release_letter'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        rl = self.object
        user = self.request.user

        # The release-wide next step, spanning both documents. This is the same
        # value that drives the queue and the notification email, so the three
        # cannot disagree about whose turn it is.
        next_step = rl.next_signing_step()
        ctx['next_step'] = next_step
        ctx['chain'] = SigningStep.chain()
        ctx['signed_step_ids'] = rl._signed_step_ids()

        # Per document: is it generated, is it signed, may this user sign it,
        # and if not, why not. The refusal text is shown rather than the button
        # simply vanishing — "awaiting the Ag. Director" is information; a
        # missing control is a puzzle.
        documents = []
        for kind, label, url_name in (('memo', 'Approval memo', 'release_memo_preview'),
                                      ('letter', 'Release letter', 'release_letter_preview')):
            allowed, step, reason = can_sign(user, rl, kind)
            # Built here rather than in the template: `{% url %}` cannot take a
            # name from a variable, and the alternative is an if/else inside an
            # iframe src attribute in two places.
            preview = reverse(url_name, args=[rl.pk])
            documents.append({
                'kind': kind,
                'label': label,
                'preview_url': preview,
                # Same render with the letterhead artwork omitted, for printing
                # onto Ministry letterhead stock. The stored PDF is untouched.
                'print_url': f"{preview}?plain=1",
                # Only the letter carries a rendered letterhead. Offering the
                # option on the memo would advertise a difference that does not
                # exist, and an officer who compared the two would reasonably
                # conclude the button was broken.
                'has_letterhead': letterhead_applies(kind),
                'pdf': getattr(rl, f'{kind}_pdf', None),
                'version': getattr(rl, f'{kind}_version', 0),
                'locked': getattr(rl, f'{kind}_locked', False),
                'complete': rl.signing_complete(kind),
                'signatures': rl.signatures_for(kind),
                'allowed': allowed,
                'step': step,
                'reason': reason,
                # The document this signatory is here for, highlighted. The
                # other is context he is entitled to, not a second task.
                'is_mine': bool(next_step and next_step.document_kind == kind
                                and next_step.user_id == user.pk),
            })
        ctx['documents'] = documents
        ctx['can_sign_any'] = any(d['allowed'] for d in documents)
        ctx['signing_complete'] = rl.signing_complete()
        ctx['may_call_officer'] = may_view_queue(user)
        ctx['preparing_officer'] = preparing_officer(rl)
        ctx['discussions'] = rl.discussion_requests.select_related('raised_by', 'officer')[:5]
        return ctx


class CallOfficerView(LoginRequiredMixin, UserPassesTestMixin, View):
    """Ask the preparing officer to discuss the release. No state change.

    Open to any signatory, not only the one whose turn it is: a signatory
    further down the chain who spots a problem should raise it immediately
    rather than wait for the document to reach them and then stall it.
    """
    http_method_names = ['post']

    def test_func(self):
        return may_view_queue(self.request.user)

    def post(self, request, pk):
        release = get_object_or_404(ReleaseLetter, pk=pk)
        back = request.POST.get('next') or reverse('approval_queue')
        document_kind = request.POST.get('document_kind', '')

        # Two tiers, one form. A correction moves state and discards signatures;
        # a routine call moves nothing. Which one it is comes from an explicit
        # radio choice rather than being inferred from the wording of the note —
        # guessing intent from prose is how a conversation becomes a rejection.
        if request.POST.get('kind') == 'correction':
            try:
                call = request_correction(
                    release, request.user,
                    note=request.POST.get('note', ''),
                    document_kind=document_kind,
                )
            except DiscussionError as exc:
                messages.error(request, str(exc))
                return redirect(back)

            label = 'approval memo' if call.document_kind == 'memo' else 'release letter'
            messages.success(
                request,
                f"The {label} has been returned to "
                f"{call.officer.get_full_name() if call.officer else 'the preparing officer'} "
                f"for correction. {call.superseded_count} signature(s) superseded and the "
                "affected document(s) unlocked — they will be re-signed at a new version.")
            return redirect(back)

        try:
            call = call_officer(
                release, request.user,
                note=request.POST.get('note', ''),
                document_kind=document_kind,
            )
        except DiscussionError as exc:
            messages.error(request, str(exc))
            return redirect(back)

        audit(request.user, release, 'release.discussion_raised',
              f"Called {call.officer or 'the preparing officer'} for discussion")

        if call.officer is None:
            messages.warning(
                request,
                "Your note is on file, but the system could not tell who prepared "
                "this release, so nobody was notified. Contact the schedule office "
                "directly.")
        elif call.email_sent:
            messages.success(
                request,
                f"{call.officer.get_full_name() or call.officer.username} has been "
                "emailed and notified. The release has not been changed.")
        else:
            messages.warning(
                request,
                f"{call.officer.get_full_name() or call.officer.username} has been "
                "notified in the system, but the email could not be sent from your "
                "mailbox. Sign in with Microsoft if you want emails to leave from you.")
        return redirect(back)


class DeclareUrgentView(LoginRequiredMixin, View):
    """Treat a release as urgent — MMU may release on the digital signature.

    Not a `UserPassesTestMixin`: the refusal message is the useful part. An
    officer who tries this should be told *why* only a signatory may do it,
    rather than shown a 403 that reads like a bug.
    """
    http_method_names = ['post']

    def post(self, request, pk):
        release = get_object_or_404(ReleaseLetter, pk=pk)
        back = request.POST.get('next') or reverse('release_letter_detail', args=[pk])

        try:
            declare_urgent(release, request.user, request.POST.get('reason', ''))
        except UrgencyError as exc:
            messages.error(request, str(exc))
            return redirect(back)

        audit(request.user, release, 'release.marked_urgent', release.urgent_reason)
        messages.success(
            request,
            "Marked urgent. MMU may release on the digital signature. The wet-signed "
            "copy is still required and will show as outstanding until it is uploaded.")
        return redirect(back)


class UrgentReleasesReportView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Every release ever fast-tracked, with who directed it and why.

    The point of this page is not any single row. It is that "how often do we do
    this" has an answer someone can read, so normalisation surfaces as a number
    Internal Audit can watch rather than as a finding after the fact.
    """
    template_name = 'Inventory/urgent_releases_report.html'

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (
            user.is_superuser
            or is_signatory(user)
            or user.groups.filter(name__in=['Management', 'Store Officers']).exists())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        releases = list(urgent_queryset())
        ctx['releases'] = releases
        ctx['total'] = len(releases)
        ctx['outstanding'] = [r for r in releases if r.urgent_scan_outstanding]
        # Denominator, so the number above can be read as a rate. A count of
        # urgent releases with nothing to compare it against says very little.
        ctx['all_signed'] = ReleaseLetter.objects.filter(
            advance_notice_at__isnull=False).count()
        return ctx
