"""
Two things a signatory can say short of signing — and they are not the same.

**Routine** (`call_officer`) is the alternative to a reject button. A chain with
a formal reject state teaches people to use it for small things; the release
then carries a permanent rejection because the addressee's title was wrong, and
the officer learns that sending anything up is risky. What a signatory usually
wants when something looks off is thirty seconds of conversation. So this
records a call, not a verdict: the note goes on file, the officer is notified
and emailed from the signatory's own mailbox, and **the workflow does not move.**

**Correction** (`request_correction`) is for the other case, which that reasoning
never covered: a signatory who has found a real error in a document that is
already signed. The only route used to be void-and-reissue, and the practical
effect was that corrections were arranged by phone while the record showed a
clean release that had quietly been rebuilt. An off-record correction is worse
than a recorded one. So a correction now has a name, a stated reason, and
consequences: the signatures on the named document and every later step are
superseded, those documents unlock, the release returns to the officer, and the
regenerate that follows numbers the new version. The history then reads
correctly — signed v1, superseded on this date for this reason, v2 on file.

Signatures are superseded, never deleted. The record that someone signed
version 1 has to survive the issue of version 2.
"""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

MAX_NOTE = 4000


class DiscussionError(RuntimeError):
    """Anything that stops a call being raised, phrased for the signatory."""


def kinds_from(release_letter, document_kind):
    """Document kinds affected when `document_kind` is corrected.

    The named document, plus every document signed **after** it in the release
    sequence. Correcting the memo therefore takes the letter with it: the signed
    memo is the authority for the letter, so if the memo changes the letter is
    resting on something that no longer exists. Correcting the letter alone
    leaves the memo standing, because nothing about the memo has changed.

    Derived from the chain's `order` rather than hard-coded as
    "memo implies letter". The sequence is configuration — an administrator can
    reorder it, or add a step — and a rule written against today's arrangement
    would keep applying after someone changed it, silently and wrongly.
    """
    from Inventory.models import SigningStep

    chain = SigningStep.chain()
    starts = [s.order for s in chain if s.document_kind == document_kind]
    if not starts:
        return [document_kind]
    first = min(starts)
    return sorted({s.document_kind for s in chain if s.order >= first})


@transaction.atomic
def request_correction(release_letter, raised_by, note, document_kind):
    """A signatory returning a document to the officer to be fixed.

    This is the tier `call_officer` deliberately is not. It moves state:

      * signatures on the named document and every later step are **superseded**
        — never deleted, because the record that someone signed version 1 has to
        survive the issue of version 2;
      * those documents unlock, so the officer can edit and regenerate;
      * `sent_for_signature_at` is cleared, so the release stops claiming it is
        with a signatory and the officer must hand it over again deliberately;
      * the workflow returns to `memo_generated` — the documents still exist,
        they are simply no longer signed.

    The regenerate that follows increments the document version, which is what
    makes the whole thing legible afterwards: the chain shows the Ag. Director
    signed v1, that v1 was superseded on this date for this stated reason, and
    that what is on file now is v2.

    Raises `DiscussionError` if the signatory names a document that does not
    exist, or leaves the note blank — a correction with no stated reason is an
    instruction to guess.
    """
    from Inventory.models import DiscussionRequest, Notification
    from Inventory.services.approvals import preparing_officer, send_link_email
    from Inventory.services.audit import audit

    note = (note or '').strip()
    if not note:
        raise DiscussionError(
            "Say what needs correcting. This returns the document to the officer "
            "and discards the signatures on it, so the reason has to be on record.")
    if len(note) > MAX_NOTE:
        raise DiscussionError("That note is too long. Keep it to the essentials.")
    if document_kind not in ('memo', 'letter'):
        raise DiscussionError(
            "Name the document that needs correcting — the approval memo or the "
            "release letter.")

    affected = kinds_from(release_letter, document_kind)

    # Supersede first, so a failure here aborts the whole thing rather than
    # leaving a correction on file against a release that never unlocked.
    superseded = 0
    signatures = release_letter.signatures.filter(
        superseded=False, document_kind__in=affected)
    superseded = signatures.count()
    signatures.update(superseded=True)

    for kind in affected:
        setattr(release_letter, f'{kind}_locked', False)

    release_letter.sent_for_signature_at = None
    release_letter.sent_for_signature_by = None
    # Forward-only elsewhere in the system; deliberately backward here, because
    # that is the entire point of a correction. Never touches a released or
    # voided release — those are finished, and a correction cannot un-issue
    # materials that have already left the store.
    fields = [f'{k}_locked' for k in affected] + [
        'sent_for_signature_at', 'sent_for_signature_by']
    if release_letter.workflow_status in ('awaiting_signature', 'approved',
                                          'awaiting_scan_upload'):
        release_letter.workflow_status = 'memo_generated'
        fields.append('workflow_status')
    release_letter.save(update_fields=fields)

    officer = preparing_officer(release_letter)
    request = DiscussionRequest.objects.create(
        release_letter=release_letter,
        document_kind=document_kind,
        kind='correction',
        raised_by=raised_by,
        officer=officer,
        note=note,
        superseded_count=superseded,
    )

    code = release_letter.code or release_letter.request_code
    who = (raised_by.get_full_name() or raised_by.username) if raised_by else 'A signatory'
    label = 'approval memo' if document_kind == 'memo' else 'release letter'
    subject = f"{code}: correction required to the {label}"
    body = (f"{who} has returned {code} for correction to the {label}.\n\n{note}\n\n"
            f"{superseded} signature(s) have been superseded and the affected "
            f"document(s) unlocked. Edit and regenerate — the new version will be "
            f"numbered so the record shows what was signed before.")

    audit(raised_by, release_letter, 'release.correction_requested',
          f"{label} returned for correction; {superseded} signature(s) superseded")

    logger.info("ReleaseLetter %s: correction requested on %s by %s, %s signature(s) "
                "superseded, affected=%s", release_letter.pk, document_kind,
                raised_by, superseded, affected)

    if officer is None:
        logger.warning("ReleaseLetter %s: correction raised but no preparing officer "
                       "could be identified.", release_letter.pk)
        return request

    Notification.objects.create(
        notification_type='discussion_request',
        title=subject, message=body,
        recipient_group='Schedule Officers', recipient_user=officer,
        sender=raised_by,
    )
    sent = send_link_email(raised_by, officer, subject, body.replace('\n', '<br>'),
                           release_letter, cta='Open the release in MOEN-IMS')
    request.email_sent = bool(sent)
    if not sent:
        request.email_error = (
            "The email could not be sent from your mailbox — the officer has been "
            "notified in-app instead.")
    request.save(update_fields=['email_sent', 'email_error'])
    return request


@transaction.atomic
def call_officer(release_letter, raised_by, note, document_kind=''):
    """Record the call, notify the officer, email them. Returns the request row.

    The row is written before the email is attempted and is not rolled back if
    Graph fails — a call that was raised but could not be emailed must still be
    visible on the release, or the signatory waits for a reply to a message that
    never left.
    """
    from Inventory.models import DiscussionRequest, Notification
    from Inventory.services.approvals import preparing_officer, send_link_email

    note = (note or '').strip()
    if not note:
        raise DiscussionError(
            "Say what you would like to discuss. The officer sees this note, "
            "so a line of context saves a phone call.")
    if len(note) > MAX_NOTE:
        raise DiscussionError("That note is too long. Keep it to the essentials.")

    if document_kind not in ('memo', 'letter'):
        document_kind = ''

    officer = preparing_officer(release_letter)

    request = DiscussionRequest.objects.create(
        release_letter=release_letter,
        document_kind=document_kind,
        raised_by=raised_by,
        officer=officer,
        note=note,
    )

    if officer is None:
        # Nothing on the release says who prepared it. Record it anyway; the
        # note is still on file and the release page still shows it.
        logger.warning("ReleaseLetter %s: discussion raised but no preparing officer "
                       "could be identified.", release_letter.pk)
        return request

    code = release_letter.code or release_letter.request_code
    who = (raised_by.get_full_name() or raised_by.username) if raised_by else 'A signatory'
    subject = f"{code}: {who} would like to discuss this release"
    body = (f"{who} has asked to discuss {code} before signing.\n\n{note}")

    Notification.objects.create(
        notification_type='discussion_request',
        title=subject,
        message=body,
        recipient_group='Schedule Officers',
        recipient_user=officer,
        sender=raised_by,
    )

    sent = send_link_email(raised_by, officer, subject,
                           body.replace('\n', '<br>'), release_letter,
                           cta='Open the release in MOEN-IMS')
    request.email_sent = bool(sent)
    if not sent:
        request.email_error = (
            "The email could not be sent from your mailbox — the officer has "
            "been notified in-app instead.")
    request.save(update_fields=['email_sent', 'email_error'])

    logger.info("ReleaseLetter %s: discussion raised by %s, officer %s notified "
                "(email_sent=%s)", release_letter.pk, raised_by, officer, sent)
    return request
