"""
MMU fast-track: advance notice by default, urgency by directive.

Two different things, and the value of the design is entirely in keeping them
apart.

**Advance notice** happens on every release, automatically, the moment the
signing chain completes. MMU sees the release and may pick and stage stock —
but may not move it. Most of the delay in a release sits in MMU waiting to
*start*, and starting requires nothing that the paper copy provides. No control
is waived: materials still leave only on the verified wet-signed scan.

**Urgency** is a management directive that clears MMU to release on the digital
signature alone. The real risk here is not a single misuse; it is quiet
normalisation — "urgent" becoming what every release is called. That is what the
guardrails in this module are for:

  * only a user named on an active `SigningStep` may declare it. The officer
    raising the release cannot. That single restriction is the difference
    between a directive and a self-serve waiver, and it is the whole reason this
    is acceptable where a per-officer "urgent" checkbox would not be;
  * a reason is mandatory, and is recorded with who and when;
  * it is shown everywhere the release appears, including on the document;
  * it is reportable, so a drift toward routine urgency shows up as a trend
    rather than as an audit finding after the fact;
  * the wet-signed copy is still required afterwards. Urgency changes *when*
    MMU may act, never *whether* the paper record exists.
"""

import logging

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

MIN_REASON = 10


class UrgencyError(RuntimeError):
    """Anything that stops urgency being declared, phrased for the signatory."""


def can_declare_urgent(user, release_letter=None):
    """→ (allowed, reason).

    Being a signatory is the test — not being *this release's* signatory. A
    Chief Director may fast-track a release the Ag. Director signed; what must
    not happen is the preparing officer fast-tracking his own paperwork.
    """
    from Inventory.services.approvals import is_signatory

    if not user or not user.is_authenticated:
        return False, "You must be signed in."
    if not (is_signatory(user) or user.is_superuser):
        return False, ("Only a signatory may treat a release as urgent. Ask the "
                       "officer who signs it — this is a directive, not a request.")
    if release_letter is not None:
        if release_letter.workflow_status == 'voided':
            return False, "This release has been voided."
        if not release_letter.signing_complete():
            return False, ("The signing chain is not complete. Urgency clears MMU to "
                           "release on the digital signature, so there must be one.")
        if release_letter.is_urgent:
            return False, "This release is already marked urgent."
    return True, ""


@transaction.atomic
def declare_urgent(release_letter, user, reason):
    """Mark the release urgent. Raises `UrgencyError` if refused."""
    from Inventory.models import Notification

    allowed, refusal = can_declare_urgent(user, release_letter)
    if not allowed:
        raise UrgencyError(refusal)

    reason = (reason or '').strip()
    if len(reason) < MIN_REASON:
        raise UrgencyError(
            "Give the reason for the urgency. It is recorded against the release "
            "and reviewed by Internal Audit, so 'urgent' on its own is not enough.")

    release_letter.is_urgent = True
    release_letter.urgent_reason = reason
    release_letter.urgent_declared_by = user
    release_letter.urgent_declared_at = timezone.now()
    release_letter.save(update_fields=[
        'is_urgent', 'urgent_reason', 'urgent_declared_by', 'urgent_declared_at'])

    code = release_letter.code or release_letter.request_code
    who = (user.get_full_name() or user.username)
    Notification.objects.create(
        notification_type='release_urgent',
        title=f"{code} treated as urgent — MMU may release before the scan",
        message=(f"{who} has directed that {code} be treated as urgent.\n\n"
                 f"Reason: {reason}\n\n"
                 f"The wet-signed copy is still required and will be flagged as "
                 f"outstanding until it is uploaded."),
        recipient_group='Store Officers',
        sender=user,
    )

    logger.info("ReleaseLetter %s marked urgent by %s: %s",
                release_letter.pk, user, reason[:120])
    return release_letter


def mark_advance_notice(release_letter):
    """Open advance notice to MMU. Idempotent; called on chain completion.

    Separate from `declare_urgent` on purpose. This one needs no authority
    because it authorises nothing — it tells MMU a release is coming.
    """
    if release_letter.advance_notice_at:
        return release_letter.advance_notice_at

    release_letter.advance_notice_at = timezone.now()
    release_letter.save(update_fields=['advance_notice_at'])
    logger.info("ReleaseLetter %s: signing chain complete, MMU on advance notice.",
                release_letter.pk)
    return release_letter.advance_notice_at


def advance_notice_queryset():
    """Releases MMU may prepare but not yet release.

    The filter MMU's existing list uses — not a new screen for them to remember
    to open.
    """
    from Inventory.models import ReleaseLetter

    return (ReleaseLetter.objects
            .filter(advance_notice_at__isnull=False)
            .exclude(workflow_status__in=('released', 'voided'))
            .order_by('advance_notice_at'))


def urgent_queryset():
    """Every release ever declared urgent, newest first — the audit report."""
    from Inventory.models import ReleaseLetter

    return (ReleaseLetter.objects
            .filter(is_urgent=True)
            .select_related('urgent_declared_by')
            .order_by('-urgent_declared_at'))
