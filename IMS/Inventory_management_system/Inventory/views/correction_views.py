"""Correction / reversal process.

A user flags a mistake on a workflow record (raise_correction); a superuser
reviews the queue (CorrectionReviewListView) and approves or rejects
(review_correction). Approving auto-executes the reversal.
"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from Inventory.models import CorrectionRequest, MaterialOrder, StockMovement
from Inventory.services.correction import ReversalError, execute_reversal

logger = logging.getLogger(__name__)

# What a raise request may point at. Keeps user input off arbitrary models.
_TARGETS = {'order': MaterialOrder, 'movement': StockMovement}
# Which reversal kinds are valid for each target model.
_VALID_KINDS = {
    'order': {'release', 'order_approval'},
    'movement': {'stock_entry'},
}


@login_required
@require_POST
def raise_correction(request):
    """A user reports a mistake and requests a reversal. Creates a Pending
    CorrectionRequest for a superuser to review."""
    target_model = (request.POST.get('target_model') or '').strip()
    target_id = (request.POST.get('target_id') or '').strip()
    kind = (request.POST.get('kind') or '').strip()
    reason = (request.POST.get('reason') or '').strip()
    nxt = request.POST.get('next') or 'correction_list'

    model = _TARGETS.get(target_model)
    if model is None or kind not in _VALID_KINDS.get(target_model, set()):
        messages.error(request, "Invalid correction request.")
        return redirect(nxt)
    if not reason:
        messages.error(request, "Please say what the mistake was.")
        return redirect(nxt)

    target = get_object_or_404(model, pk=target_id)

    # Don't let the same record pile up duplicate open requests.
    ct = ContentType.objects.get_for_model(model)
    if CorrectionRequest.objects.filter(
            content_type=ct, object_id=target.pk, status='Pending').exists():
        messages.info(request, "A reversal request for this record is already pending.")
        return redirect(nxt)

    CorrectionRequest.objects.create(
        content_type=ct, object_id=target.pk, kind=kind,
        reason=reason, raised_by=request.user)
    messages.success(
        request, "Reversal requested. An administrator will review it.")
    return redirect(nxt)


class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class CorrectionReviewListView(LoginRequiredMixin, SuperuserRequiredMixin, ListView):
    """Superuser queue of correction/reversal requests."""
    model = CorrectionRequest
    template_name = 'Inventory/correction_list.html'
    context_object_name = 'requests'
    paginate_by = 50

    def get_queryset(self):
        qs = CorrectionRequest.objects.select_related(
            'raised_by', 'reviewed_by', 'content_type').order_by('-created_at')
        status = (self.request.GET.get('status') or 'Pending').strip()
        if status in ('Pending', 'Approved', 'Rejected'):
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['selected_status'] = (self.request.GET.get('status') or 'Pending').strip()
        ctx['pending_count'] = CorrectionRequest.objects.filter(status='Pending').count()
        return ctx


@require_POST
def review_correction(request, pk):
    """Superuser approves (auto-executes the reversal) or rejects a request."""
    if not request.user.is_superuser:
        messages.error(request, "Only administrators can review reversal requests.")
        return redirect('correction_list')

    cr = get_object_or_404(CorrectionRequest, pk=pk)
    if cr.status != 'Pending':
        messages.info(request, f"This request was already {cr.status.lower()}.")
        return redirect('correction_list')

    action = (request.POST.get('action') or '').strip()
    note = (request.POST.get('review_note') or '').strip()

    if action == 'reject':
        cr.status = 'Rejected'
        cr.review_note = note
        cr.reviewed_by = request.user
        cr.reviewed_at = timezone.now()
        cr.save()
        messages.success(request, f"Reversal request #{cr.pk} rejected.")
        return redirect('correction_list')

    if action == 'approve':
        try:
            result = execute_reversal(cr, request.user)
        except ReversalError as e:
            messages.error(request, f"Could not reverse: {e}")
            return redirect('correction_list')
        cr.status = 'Approved'
        cr.result = result
        cr.review_note = note
        cr.reviewed_by = request.user
        cr.reviewed_at = timezone.now()
        cr.save()
        logger.info("Correction #%s approved & reversed by %s: %s",
                    cr.pk, request.user, result)
        messages.success(request, f"Reversed. {result}")
        return redirect('correction_list')

    messages.error(request, "Unknown action.")
    return redirect('correction_list')
