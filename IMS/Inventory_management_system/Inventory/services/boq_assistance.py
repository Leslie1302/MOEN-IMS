"""
"Contact system admin for assistance" — the way out of an unmatched BoQ line.

An unmatched material blocks generation, and unlike an over-issuance the officer
cannot clear it himself. The causes all sit above his desk: the Bill of Quantity
for that community was never imported, or was imported against a different
package, or the material's item code does not match the one on the BoQ, or the
release genuinely falls outside any contract and someone senior needs to say so.

Without a route out, a blocker like that produces one of two outcomes, both bad:
the release stalls silently until somebody chases it, or an officer finds a way
around the check. So the block comes with a door, and the door is this — a
request that names the exact lines, reaches a named administrator, and is on
record so the delay is attributable.

**Who counts as an administrator**, in order:

  1. `settings.SYSTEM_ADMIN_EMAILS` — an explicit list, for deployments that
     route this to a mailbox rather than a person;
  2. members of the `System Administrators` group;
  3. active superusers with an email address.

The fallback chain exists so this can never quietly reach nobody. A support
request that vanishes is worse than no support request, because the officer
believes he has asked.
"""

import logging

logger = logging.getLogger(__name__)

ADMIN_GROUP = 'System Administrators'


class AssistanceError(RuntimeError):
    """Anything that stops a request being raised, phrased for the officer."""


def admin_recipients():
    """→ (users, extra_emails). Never both empty unless the system has no admins."""
    from django.conf import settings
    from django.contrib.auth.models import User

    extra = [e.strip() for e in (getattr(settings, 'SYSTEM_ADMIN_EMAILS', None) or [])
             if e and e.strip()]

    users = list(User.objects.filter(
        is_active=True, groups__name=ADMIN_GROUP).exclude(email='').distinct())

    if not users and not extra:
        # Last resort. A deployment that never created the group still has
        # superusers, and reaching one of them beats reaching nobody.
        users = list(User.objects.filter(
            is_active=True, is_superuser=True).exclude(email='').distinct())

    return users, extra


def request_assistance(release_letter, raised_by, note=''):
    """Ask an administrator to resolve the unmatched Bill of Quantity lines.

    Records a notification per administrator and emails each one from the
    officer's own mailbox, so the reply lands where the conversation started.
    Returns `(recipients, emailed)`.

    Raises `AssistanceError` only when there is genuinely nobody to ask — which
    is a configuration fault worth surfacing loudly rather than a failure to
    swallow.
    """
    from Inventory.models import Notification
    from Inventory.services.approvals import send_link_email
    from Inventory.services.audit import audit
    from Inventory.services.reconciliation import generation_blockers

    blockers, _result = generation_blockers(release_letter)
    unmatched = blockers['unmatched']

    users, extra = admin_recipients()
    if not users and not extra:
        raise AssistanceError(
            "No system administrator is configured to receive this. Add a user to "
            f"the '{ADMIN_GROUP}' group, or set SYSTEM_ADMIN_EMAILS, and try again.")

    code = release_letter.code or release_letter.request_code
    who = (raised_by.get_full_name() or raised_by.username) if raised_by else 'An officer'

    # Name the lines. An administrator who has to open the release to find out
    # which materials are unmatched will do it later rather than now.
    if unmatched:
        detail = "\n".join(
            f"  • {line['material']} ({line['item_code'] or 'no item code'}) "
            f"at {line['community'] or 'no community'}"
            f"{', package ' + line['package_number'] if line['package_number'] else ''}"
            for line in unmatched)
    else:
        detail = "  (no unmatched lines are outstanding at the moment of asking)"

    subject = f"{code}: Bill of Quantity assistance required"
    body = (
        f"{who} cannot generate the release documents for {code} because the "
        f"following material(s) have no Bill of Quantity entry for their community:\n\n"
        f"{detail}\n\n"
        f"Document generation is blocked until this is resolved. Typically the Bill "
        f"of Quantity for the community has not been imported, was imported against a "
        f"different package number, or the item code does not match."
        + (f"\n\nFrom {who}:\n{note.strip()}" if (note or '').strip() else ""))

    emailed = 0
    for user in users:
        Notification.objects.create(
            notification_type='boq_assistance',
            title=subject, message=body,
            recipient_group='Management', recipient_user=user,
            sender=raised_by,
        )
        if send_link_email(raised_by, user, subject, body.replace('\n', '<br>'),
                           release_letter, cta='Open the release in MOEN-IMS'):
            emailed += 1

    for address in extra:
        # A bare mailbox with no user account — notify by email only, since
        # there is no in-app inbox to write to.
        if _email_address(raised_by, address, subject, body, release_letter):
            emailed += 1

    audit(raised_by, release_letter, 'release.boq_assistance_requested',
          f"{len(unmatched)} unmatched BoQ line(s); "
          f"{len(users) + len(extra)} administrator(s) contacted")

    logger.info("ReleaseLetter %s: BoQ assistance requested by %s, %s recipient(s), "
                "%s emailed", release_letter.pk, raised_by,
                len(users) + len(extra), emailed)
    return users + extra, emailed


def _email_address(sender, address, subject, body, release_letter):
    """Send to a bare address. Mirrors `send_link_email` without a User object."""
    from accounts.notifications import send_email_notification
    from Inventory.services.approvals import _absolute_url

    link = _absolute_url(release_letter)
    html = (f"<p>{body.replace(chr(10), '<br>')}</p>"
            f"<p><a href=\"{link}\">Open the release in MOEN-IMS</a></p>")
    try:
        send_email_notification(user=sender, to=[address], subject=subject,
                                body=html, body_type='HTML')
        return True
    except Exception as exc:  # noqa: BLE001 — a Graph failure must not lose the record
        logger.warning("Could not email system admin %s about ReleaseLetter %s: %s",
                       address, release_letter.pk, exc)
        return False
