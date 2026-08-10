"""
Re-post site receipts that never found a Bill of Quantity line.

`SiteReceipt.save()` resolves the BoQ match **once, on creation**:

    if is_new:
        self.boq_matched, self.boq_match_note = self._post_to_boq()

That is right for the normal case, but it means a receipt logged before its BoQ
line existed is stranded. Uploading the BoQ afterwards does not go back and post
it — the receipt keeps `boq_matched=False`, no contract quantity is drawn down,
and it sits in the over-issuance summary as an off-BoQ delivery for good.

This module retries those, and only those.

**Safety.** Only receipts with `boq_matched=False` are considered, so a receipt
that already drew down its line can never be posted twice. A successful re-match
flips the flag, which makes the operation idempotent: run it as often as you
like and each receipt posts at most once.
"""

import logging
from dataclasses import dataclass, field
from typing import List

from django.db import transaction

logger = logging.getLogger(__name__)


@dataclass
class RematchResult:
    considered: int = 0
    posted: int = 0
    still_unmatched: int = 0
    errors: int = 0
    details: List[dict] = field(default_factory=list)

    def summary(self) -> str:
        if not self.considered:
            return "No unmatched receipts to retry."
        parts = [f"{self.considered} considered", f"{self.posted} posted"]
        if self.still_unmatched:
            parts.append(f"{self.still_unmatched} still without a BoQ line")
        if self.errors:
            parts.append(f"{self.errors} errored")
        return ", ".join(parts) + "."


def rematch_unposted_receipts(dry_run=False, limit=None, receipt_ids=None):
    """Retry the BoQ match for receipts that never posted.

    `dry_run` reports what would post without writing anything — including
    without incrementing any BoQ quantity, since the whole operation runs inside
    a transaction that is rolled back.

    Returns a `RematchResult`. Never raises for a single bad receipt: one
    unparseable row must not stop the rest of a backlog from posting.
    """
    from Inventory.models import SiteReceipt

    qs = (SiteReceipt.objects
          .filter(boq_matched=False)
          .select_related('material_transport', 'material_transport__material_order')
          .order_by('received_date'))
    if receipt_ids:
        qs = qs.filter(pk__in=receipt_ids)
    if limit:
        qs = qs[:limit]

    result = RematchResult()

    # A dry run still calls _post_to_boq, which mutates the BoQ line — so the
    # whole thing runs in a transaction and is rolled back at the end. That is
    # what makes the preview honest rather than approximate.
    with transaction.atomic():
        for receipt in qs:
            result.considered += 1
            try:
                matched, note = receipt._post_to_boq()
            except Exception as exc:  # noqa: BLE001
                result.errors += 1
                result.details.append({
                    'id': receipt.pk, 'outcome': 'error', 'note': str(exc)})
                logger.exception("Re-match failed for SiteReceipt %s", receipt.pk)
                continue

            if matched:
                result.posted += 1
                receipt.boq_matched = True
                receipt.boq_match_note = note
                if not dry_run:
                    # pk exists, so save() takes the is_new=False path: no
                    # second BoQ post, no re-marking the transport delivered.
                    receipt.save(update_fields=['boq_matched', 'boq_match_note'])
                result.details.append({
                    'id': receipt.pk, 'outcome': 'posted', 'note': note})
            else:
                result.still_unmatched += 1
                result.details.append({
                    'id': receipt.pk, 'outcome': 'unmatched', 'note': note})

        if dry_run:
            transaction.set_rollback(True)

    logger.info("BoQ re-match (%s): %s",
                'dry run' if dry_run else 'applied', result.summary())
    return result


def count_unposted_receipts():
    """How many receipts are stranded. Cheap enough for a page header."""
    from Inventory.models import SiteReceipt
    return SiteReceipt.objects.filter(boq_matched=False).count()
