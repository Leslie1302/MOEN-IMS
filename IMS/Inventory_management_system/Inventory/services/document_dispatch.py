"""
Email release documents (approval memo / release letter) to named recipients
via Microsoft Graph.

Graph sends **on behalf of the signed-in officer** (`/me/sendMail`), so the
message arrives from their own Ministry mailbox rather than a no-reply address.
That is the point: the Chief Director receives a normal email from the officer
who prepared the release, and can simply reply. The cost is that the officer
must have signed in through Microsoft at least once — a password-only account
has no Graph token, and this module says so plainly rather than failing opaquely.

Every attempt is recorded as a `DocumentDispatch`, successes and failures alike.
A release whose documents were never sent must be distinguishable from one where
the send was rejected, or chasing a missing approval becomes guesswork.
"""

import base64
import logging

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

# Imported at module scope (accounts.notifications does not import Inventory, so
# there is no circular-import risk) so it is patchable here as
# document_dispatch.send_email_notification — which is where the send is invoked.
from accounts.notifications import send_email_notification

logger = logging.getLogger(__name__)

# Graph rejects messages over ~4 MB when attachments are inlined as base64.
# Above that the API requires an upload session, which is a lot of machinery for
# documents that are normally well under 1 MB — so we refuse clearly instead.
MAX_ATTACHMENT_BYTES = 3 * 1024 * 1024


class DispatchError(RuntimeError):
    """Anything that stops a send, phrased for the officer rather than the log."""


def _attachment(name, content_bytes):
    return {
        "@odata.type": "#microsoft.graph.fileAttachment",
        "name": name,
        "contentType": "application/pdf",
        "contentBytes": base64.b64encode(content_bytes).decode('ascii'),
    }


def _read_document(release_letter, kind):
    """Bytes of the stored memo/letter PDF, or None when it hasn't been generated."""
    field = getattr(release_letter, f'{kind}_pdf', None)
    if not field:
        return None
    try:
        field.open('rb')
        data = field.read()
        field.close()
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not read %s_pdf for ReleaseLetter %s: %s",
                       kind, release_letter.pk, exc)
        return None


def resolve_recipients(users=None, extra_emails=None):
    """→ (addresses, matched_users). Raises DispatchError on a bad address.

    Users without an email address are reported by name: silently dropping them
    would mean an officer believing the Chief Director was copied when they
    were not.
    """
    addresses, matched, missing = [], [], []

    for user in (users or []):
        email = (user.email or '').strip()
        if not email:
            missing.append(user.get_full_name() or user.username)
            continue
        if email.lower() not in [a.lower() for a in addresses]:
            addresses.append(email)
            matched.append(user)

    if missing:
        raise DispatchError(
            "No email address on file for: " + ", ".join(missing) +
            ". Add it to their profile, or type the address in directly.")

    for raw in (extra_emails or []):
        email = (raw or '').strip()
        if not email:
            continue
        try:
            validate_email(email)
        except ValidationError:
            raise DispatchError(f"'{email}' is not a valid email address.")
        if email.lower() not in [a.lower() for a in addresses]:
            addresses.append(email)

    if not addresses:
        raise DispatchError("Choose at least one recipient.")
    return addresses, matched


def build_body(release_letter, sender, message=''):
    """The covering email. Deliberately plain — the PDFs carry the content."""
    code = release_letter.code or release_letter.request_code or 'this release'
    sender_name = (sender.get_full_name() or sender.username) if sender else 'MOEN-IMS'
    note = ''
    if (message or '').strip():
        safe = (message.strip()
                .replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                .replace('\n', '<br>'))
        note = f"<p>{safe}</p>"

    return (
        f"<p>Please find attached the release documents for <b>{code}</b>"
        f"{' — ' + release_letter.title if release_letter.title else ''}.</p>"
        f"{note}"
        f"<p>Kindly sign the release letter and return the signed copy so it can be "
        f"uploaded against this release event.</p>"
        f"<p>Regards,<br>{sender_name}<br>"
        f"<span style='color:#666;font-size:12px'>Sent from MOEN-IMS</span></p>"
    )


@transaction.atomic
def send_release_documents(release_letter, sender, users=None, extra_emails=None,
                           include_memo=True, include_letter=True,
                           subject=None, message='', advance_workflow=True):
    """Email the selected documents and record the attempt.

    Returns the `DocumentDispatch` row. Raises `DispatchError` with an officer-
    readable message for anything that prevents the send — nothing is recorded
    in that case, because no attempt reached Graph.
    """
    from Inventory.models import DocumentDispatch

    if not (include_memo or include_letter):
        raise DispatchError("Select at least one document to attach.")

    addresses, matched_users = resolve_recipients(users, extra_emails)

    attachments, missing = [], []
    for kind, wanted in (('memo', include_memo), ('letter', include_letter)):
        if not wanted:
            continue
        data = _read_document(release_letter, kind)
        if not data:
            missing.append(kind)
            continue
        attachments.append(_attachment(
            f"{kind}_{release_letter.code or release_letter.pk}.pdf", data))

    if missing:
        raise DispatchError(
            f"The {' and '.join(missing)} has not been generated yet. "
            "Generate the documents first, then send.")

    total = sum(len(a['contentBytes']) for a in attachments)
    if total > MAX_ATTACHMENT_BYTES * 1.37:      # base64 inflates by ~37%
        raise DispatchError(
            "The attachments are too large to email directly. Reduce the "
            "letterhead image size, or send one document at a time.")

    subject = (subject or '').strip() or (
        f"Release documents — {release_letter.code or release_letter.request_code}")

    dispatch = DocumentDispatch(
        release_letter=release_letter, sent_by=sender,
        recipients=', '.join(addresses),
        include_memo=include_memo, include_letter=include_letter,
        # Record which versions actually went out. Without this the history
        # implies the document on file today is what the recipient received —
        # false the moment anything is regenerated, and the QR would not catch
        # it because it encodes the release code, not the version.
        memo_version=getattr(release_letter, 'memo_version', 0) or 0,
        letter_version=getattr(release_letter, 'letter_version', 0) or 0,
        subject=subject, message=(message or '').strip(),
    )

    try:
        send_email_notification(
            user=sender, to=addresses, subject=subject,
            body=build_body(release_letter, sender, message),
            body_type='HTML', attachments=attachments,
        )
    except Exception as exc:  # noqa: BLE001
        # Record the failure, then surface it. The row is what tells an officer
        # later that a send was attempted and did not land.
        dispatch.status = 'failed'
        dispatch.error = str(exc)[:2000]
        dispatch.save()
        dispatch.recipient_users.set(matched_users)
        logger.error("Dispatch failed for ReleaseLetter %s: %s", release_letter.pk, exc)

        if 'credentials' in str(exc).lower() or 'token' in str(exc).lower():
            raise DispatchError(
                "Your Microsoft account isn't connected, so the email could not be "
                "sent from your mailbox. Sign in with Microsoft, then try again."
            ) from exc
        raise DispatchError(f"The email could not be sent: {exc}") from exc

    dispatch.status = 'sent'
    dispatch.save()
    dispatch.recipient_users.set(matched_users)

    # Sending to the signatory means the release is now with them for signature.
    if advance_workflow and include_letter and release_letter.workflow_status in (
            'draft', 'memo_generated'):
        release_letter.workflow_status = 'awaiting_signature'
        release_letter.save(update_fields=['workflow_status'])
        logger.info("ReleaseLetter %s advanced to awaiting_signature on dispatch",
                    release_letter.pk)

    return dispatch
