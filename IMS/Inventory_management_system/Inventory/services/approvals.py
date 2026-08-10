"""
The management approval queue — what a signatory sees when they sign in.

Signatories were previously dropped into the schedule officer's workspace: the
release-letter dashboard shows every release in every state, with generate,
edit and adjust controls, and no per-user filtering at all. Only the Sign button
was correctly scoped. For someone whose entire involvement is "sign the two
documents that are waiting for me", that page is noise with a needle in it.

This module answers one question — *what is waiting for this person* — and
answers it from the same `next_signing_step()` the signing service enforces, so
the queue, the email and the Sign button cannot disagree about whose turn it is.

Read access stays open elsewhere. A senior officer hitting a permission wall on
his own Ministry's paperwork is a worse failure than his seeing a release early.
"""

import logging

logger = logging.getLogger(__name__)

# States where a release is genuinely in play. A voided release is not waiting
# for anybody, and a released one is finished.
LIVE_STATES = ('draft', 'memo_generated', 'awaiting_signature',
               'awaiting_scan_upload', 'approved')


def is_signatory(user):
    """True when this user is named on an active step of the signing chain."""
    from Inventory.models import SigningStep

    if not user or not user.is_authenticated:
        return False
    return SigningStep.objects.filter(active=True, user=user).exists()


def may_view_queue(user):
    """Who the approvals page is for.

    Signatories, because it is their landing point. Management, because they
    supervise the chain and need to see what is stuck without being on it. And
    superusers, who see everything anyway.
    """
    if not user or not user.is_authenticated:
        return False
    return (user.is_superuser
            or is_signatory(user)
            or user.groups.filter(name='Management').exists())


def _live_releases():
    from Inventory.models import ReleaseLetter

    return (ReleaseLetter.objects
            .filter(workflow_status__in=LIVE_STATES)
            .select_related('uploaded_by')
            .prefetch_related('signatures', 'signatures__step')
            .order_by('upload_time'))


def queue_for(user):
    """→ {'awaiting_me': [...], 'awaiting_others': [...], 'recently_signed': [...]}

    Each entry in the first two lists is a dict of the release plus the step it
    is sitting on, because a queue that shows only the release makes the reader
    work out whose turn it is — which is the thing they came to find out.

    Deliberately evaluated in Python rather than SQL: "the next unsigned
    required step" is a walk down an ordered chain against the set of signatures
    already applied, and expressing that as a query would mean a second
    implementation of the rule that decides whether a signature is valid. One
    implementation, used everywhere, is worth more here than the round trips.
    Release volume is tens per month, not thousands.
    """
    from Inventory.models import DocumentSignature

    awaiting_me, awaiting_others = [], []

    if not (user and user.is_authenticated):
        return {'awaiting_me': [], 'awaiting_others': [], 'recently_signed': []}

    for release in _live_releases():
        step = release.next_signing_step()
        if step is None:
            continue                      # fully signed; it is with MMU now
        entry = {
            'release': release,
            'step': step,
            'kind': step.document_kind,
            'signatory': step.signatory,
            'signed_so_far': list(release.signatures.filter(superseded=False)),
            # Nothing to sign until the document exists. Showing it in the
            # queue anyway would be honest but useless — the officer has not
            # finished preparing it.
            'ready': bool(getattr(release, f'{step.document_kind}_pdf', None)),
            # Whether the officer has formally handed it over. Shown, never
            # filtered on: an unsent release is still the signatory's business,
            # and hiding it would make the officer's button a permission wall.
            # But "not yet sent to you" is the difference between a document
            # waiting on him and one still being prepared, and he cannot tell
            # from the documents alone.
            'sent_at': release.sent_for_signature_at,
        }
        if step.user_id == user.pk:
            awaiting_me.append(entry)
        else:
            awaiting_others.append(entry)

    recently_signed = list(
        DocumentSignature.objects
        .filter(signed_by=user)
        .select_related('release_letter', 'step')
        .order_by('-signed_at')[:15])

    # Ordered by how much of a claim each item has on the signatory's attention:
    # generated and formally sent to him, then generated but not yet sent, then
    # not generated at all. Oldest first inside each band.
    awaiting_me.sort(key=lambda e: (not e['ready'], e['sent_at'] is None,
                                    e['release'].upload_time))

    return {
        'awaiting_me': awaiting_me,
        'awaiting_others': awaiting_others,
        'recently_signed': recently_signed,
    }


def preparing_officer(release_letter):
    """Whoever should be called about this release.

    The person who last edited a document is the one who knows what is in it;
    only if nobody has edited does this fall back to whoever created the row.
    """
    for candidate in (release_letter.letter_html_edited_by,
                      release_letter.memo_html_edited_by,
                      release_letter.uploaded_by):
        if candidate is not None:
            return candidate
    return None


def notify_next_signatory(release_letter, sender=None):
    """Tell the next signatory their turn has come.

    Called after a signature completes a step, so the Chief Director learns the
    memo has been approved without anyone remembering to email him — the handoff
    that otherwise sits in someone's head is the one that loses a week.

    The email carries a **link into the system**, never the documents. An
    emailed PDF that comes back signed proves a round trip nobody observed;
    signing in-system captures who signed, when, from where, and against which
    version. Failure is logged, not raised: the queue is the source of truth and
    the signature must not depend on Graph being reachable.
    """
    from Inventory.models import Notification

    step = release_letter.next_signing_step()
    if step is None or step.user is None:
        return None

    code = release_letter.code or release_letter.request_code
    kind = step.get_document_kind_display().lower()
    title = f"{code}: the {kind} is awaiting your signature"
    body = (f"The {kind} for {code} is now with you for signature. "
            f"Open Approvals in MOEN-IMS to review both documents and sign.")

    notification = Notification.objects.create(
        notification_type='signature_requested',
        title=title, message=body,
        recipient_group='Management', recipient_user=step.user,
        sender=sender,
    )

    send_link_email(sender, step.user, title, body, release_letter,
                    cta='Open the approvals queue')
    return notification


class SendForSignatureError(RuntimeError):
    """Why a release could not be handed to a signatory, phrased for the officer."""


def send_for_signature(release_letter, sender):
    """The officer's explicit handover to the next signatory.

    Generation deliberately notifies nobody (§2a(ii)): if every draft pinged the
    Ag. Director, he would learn to ignore the emails, and a signature queue
    that is ignored is worse than no queue at all. So the handover is its own
    act, performed when the officer judges the documents ready.

    Repeatable on purpose. The second press is a nudge, not a mistake — the
    commonest reason an officer returns to this button is that a week has gone
    by. `sent_for_signature_at` is overwritten so it always answers "when did we
    last chase this", which is the question actually being asked.

    Returns `(step, notification)`. Raises `SendForSignatureError` when there is
    nothing or nobody to send to.
    """
    from django.utils import timezone

    step = release_letter.next_signing_step()
    if step is None:
        raise SendForSignatureError(
            "Every required signature is already on file — there is nobody left to send this to.")

    # No login on the step means no one can sign in-system. Refuse rather than
    # record a handover to nobody: the officer would otherwise see "sent" and
    # wait, while the Signatory row sits unlinked in admin where nobody looks.
    if step.user is None:
        holder = step.signatory.title if step.signatory else 'the next signatory'
        raise SendForSignatureError(
            f"{holder} has no MOEN-IMS login linked to their signatory record, so they "
            "cannot sign in the system. Link the account in admin (Signing step → user), "
            "or use the wet-signature route.")

    if not getattr(release_letter, f'{step.document_kind}_pdf', None):
        raise SendForSignatureError(
            f"The {step.get_document_kind_display().lower()} has not been generated yet, "
            "so there is nothing for them to sign.")

    notification = notify_next_signatory(release_letter, sender=sender)

    release_letter.sent_for_signature_at = timezone.now()
    release_letter.sent_for_signature_by = sender
    fields = ['sent_for_signature_at', 'sent_for_signature_by']

    # Forward only. A release that has come back from MMU for a scan must not be
    # dragged back to 'awaiting signature' because someone chased a signatory.
    if release_letter.workflow_status in ('draft', 'memo_generated'):
        release_letter.workflow_status = 'awaiting_signature'
        fields.append('workflow_status')

    release_letter.save(update_fields=fields)
    return step, notification


def send_link_email(sender, recipient, subject, body, release_letter,
                    cta='Open in MOEN-IMS'):
    """Send a link-only covering email, best-effort.

    Graph sends on behalf of the signed-in officer, so the message arrives from
    a real Ministry mailbox and can simply be replied to. If the sender has
    never signed in with Microsoft there is no token and nothing can be sent —
    which is a reason to log, not a reason to fail the action that triggered it.
    """
    from accounts.notifications import send_email_notification

    address = (recipient.email or '').strip() if recipient else ''
    if not address:
        logger.info("No email address for %s; in-app notification only.", recipient)
        return False

    link = _absolute_url(release_letter)
    html = (f"<p>{body}</p>"
            f"<p><a href=\"{link}\">{cta}</a></p>"
            f"<p style='color:#666;font-size:12px'>The documents stay in MOEN-IMS. "
            f"Nothing is attached to this email.</p>")
    try:
        send_email_notification(user=sender, to=[address], subject=subject,
                                body=html, body_type='HTML')
        return True
    except Exception as exc:  # noqa: BLE001 — Graph failures must not lose the record
        logger.warning("Could not email %s about ReleaseLetter %s: %s",
                       address, release_letter.pk, exc)
        return False


def _absolute_url(release_letter):
    from django.conf import settings
    from django.urls import reverse

    base = (getattr(settings, 'BASE_URL', '') or '').rstrip('/')
    # Straight to the signing page for THIS release, not the queue. The
    # signatory clicked a link about one specific release; making him find it
    # again in a list is a step that exists only because it was easier to build.
    path = reverse('sign_release', args=[release_letter.pk])
    return f"{base}{path}" if base else path
