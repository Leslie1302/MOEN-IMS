"""Stock ledger — the single writer for the tally (bin) card.

Every place that changes ``InventoryItem.quantity`` calls ``record_movement``
right after saving the new quantity, so the ledger always carries the balance
as it actually stood. Keeping this in one helper means the card's history can
never diverge in *shape* from the stock changes — only the set of call sites
decides completeness, and those are few (release/receipt, the completion
signal, and bulk upload).

Design choices, deliberately small:
  * The helper never mutates stock. It only records what already happened, so a
    caller can't accidentally double-deduct by logging.
  * ``balance_after`` is read straight off the (already-updated, already-saved)
    item, so it is the truth, not a recomputation that could drift.
  * A failure to write the ledger must not break the actual stock operation —
    a release that succeeded should not roll back because its history line
    failed. So write errors are swallowed with a log, never raised.
"""

import logging

logger = logging.getLogger(__name__)


def record_movement(item, movement_type, *, qty_in=0, qty_out=0,
                    reference='', user=None, note='', balance_after=None):
    """Append one immutable row to the stock ledger.

    ``item`` is the InventoryItem whose quantity was just changed and saved.
    Pass the movement's inbound quantity as ``qty_in`` OR outbound as
    ``qty_out`` (one of them). ``balance_after`` defaults to the item's current
    quantity; pass it explicitly only when seeding history for a known past
    balance. Returns the StockMovement, or ``None`` if there was nothing to
    record.
    """
    if item is None:
        return None
    try:
        from Inventory.models import StockMovement

        performer = user if getattr(user, 'pk', None) else None
        bal = item.quantity if balance_after is None else balance_after
        return StockMovement.objects.create(
            item=item,
            movement_type=movement_type,
            qty_in=qty_in or 0,
            qty_out=qty_out or 0,
            balance_after=bal or 0,
            reference=(reference or '')[:120],
            note=note or '',
            performed_by=performer,
        )
    except Exception:  # noqa: BLE001 — history must never break the operation
        logger.exception(
            "record_movement failed for item=%s type=%s (stock change already "
            "applied; ledger row skipped)",
            getattr(item, 'code', item), movement_type)
        return None


def find_drift(items=None):
    """Return cards whose ledger balance no longer matches live stock.

    The invariant the whole tally card rests on: the latest movement's
    ``balance_after`` equals the item's live ``quantity``. Any code path that
    changed stock without going through ``record_movement`` breaks it, and this
    is how we catch that — plus items that somehow have no ledger row at all.

    Returns a list of ``(item, live_quantity, ledger_balance)`` tuples;
    ``ledger_balance`` is ``None`` when the item has no movements. Empty list
    means every card is consistent.
    """
    from decimal import Decimal
    from Inventory.models import InventoryItem

    if items is None:
        items = InventoryItem.objects.all()

    drift = []
    for item in items.prefetch_related('movements'):
        movs = list(item.movements.all())  # model default ordering: oldest→newest
        if not movs:
            drift.append((item, item.quantity, None))
            continue
        ledger_balance = movs[-1].balance_after
        if Decimal(item.quantity or 0) != Decimal(ledger_balance):
            drift.append((item, item.quantity, ledger_balance))
    return drift
