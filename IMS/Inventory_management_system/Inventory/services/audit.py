"""
Phase G helper: write entries to the `audit_log` app from anywhere in the
codebase with a single function call. The app was installed but never
actually written to before this phase; this module is the entry point for
that work.

Usage:
    from Inventory.services.audit import audit
    audit(user=request.user, target=release_letter,
          action='release.documents_generated',
          message=f"Generated memo + letter for {release_letter.code}")
"""

import logging

logger = logging.getLogger(__name__)


def audit(user, target, action: str, message: str = '', ip_address: str = None):
    """
    Record one audit event. `target` is any model instance (we record its
    class name + pk). `action` should be a dot-separated stable identifier
    so reports can filter on it.

    Failures are swallowed and logged -- audit writes must never break a
    user-facing transaction.
    """
    try:
        from audit_log.models import AuditLog
        AuditLog.objects.create(
            user=user if (user is not None and getattr(user, 'is_authenticated', True)) else None,
            model_name=target.__class__.__name__ if target is not None else '',
            object_id=getattr(target, 'pk', 0) or 0,
            action=action[:50],
            change_message=message,
            ip_address=ip_address,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Audit log write failed (action=%s): %s", action, exc)
