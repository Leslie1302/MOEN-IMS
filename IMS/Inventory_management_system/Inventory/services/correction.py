"""Execute an approved CorrectionRequest — reverse a workflow done in error.

Three reversible workflows (see CorrectionRequest.KIND_CHOICES):

* ``release``        — a MaterialOrder released in error: restock the released
                       quantity (append a ``reversal`` ledger row) and re-open
                       the order to ``Approved``.
* ``order_approval`` — a MaterialOrder approved/assigned in error: roll the
                       status back to ``Draft`` and clear the assignment.
* ``stock_entry``    — a StockMovement (opening/receipt/adjustment) written in
                       error: append a compensating ``reversal`` row that nets
                       out its effect on the item's quantity.

All reversals are append-only at the ledger level — we never delete history,
we write the opposite movement. Wrapped in a transaction so a half-applied
reversal can't leave stock and status out of step.
"""
from decimal import Decimal

from django.db import transaction

from Inventory.models import InventoryItem, MaterialOrder, StockMovement
from Inventory.services.stock_ledger import record_movement


class ReversalError(Exception):
    """Raised when a correction cannot be reversed (e.g. nothing to undo)."""


@transaction.atomic
def execute_reversal(cr, admin):
    """Perform the reversal for an approved CorrectionRequest ``cr``.

    Returns a short human-readable summary of what was done (stored on
    ``cr.result``). Raises :class:`ReversalError` if there is nothing valid
    to reverse.
    """
    target = cr.target
    if target is None:
        raise ReversalError("The record this correction points to no longer exists.")

    if cr.kind == 'release':
        return _reverse_release(target, cr, admin)
    if cr.kind == 'order_approval':
        return _reverse_approval(target, cr, admin)
    if cr.kind == 'stock_entry':
        return _reverse_stock_entry(target, cr, admin)
    raise ReversalError(f"Unknown correction kind '{cr.kind}'.")


def _reverse_release(order, cr, admin):
    if not isinstance(order, MaterialOrder):
        raise ReversalError("Release corrections must target an order.")
    released = Decimal(str(order.processed_quantity or 0))
    if released <= 0:
        raise ReversalError("Nothing has been released on this order to reverse.")

    # Restock what was issued and log a reversal row against the tally card.
    from Inventory.services.order_flow import _pick_inventory_item
    item = _pick_inventory_item(order, released)
    restocked = ""
    if item is not None:
        item.quantity = (item.quantity or 0) + int(released)
        item.save(update_fields=['quantity'])
        record_movement(
            item, 'reversal', qty_in=released,
            reference=order.request_code or str(order.pk), user=admin,
            note=f"Reversal of release on order {order.request_code or order.pk} "
                 f"(correction #{cr.pk})")
        restocked = f"Restocked {released} to {item.code}. "

    order.processed_quantity = Decimal('0')
    order.remaining_quantity = order.quantity
    order.stock_deducted_quantity = Decimal('0')
    order.status = 'Approved'
    order.save()
    return f"{restocked}Order {order.request_code or order.pk} re-opened (Approved)."


def _reverse_approval(order, cr, admin):
    if not isinstance(order, MaterialOrder):
        raise ReversalError("Approval corrections must target an order.")
    if (order.processed_quantity or 0) > 0:
        raise ReversalError(
            "This order has already had stock released — reverse the release "
            "instead of the approval.")
    order.status = 'Draft'
    order.assigned_to = None
    order.assigned_by = None
    order.assigned_at = None
    order.save()
    return f"Order {order.request_code or order.pk} returned to Draft and unassigned."


def _reverse_stock_entry(mv, cr, admin):
    if not isinstance(mv, StockMovement):
        raise ReversalError("Stock-entry corrections must target a stock movement.")
    if mv.movement_type == 'reversal':
        raise ReversalError("This movement is itself a reversal — nothing to undo.")

    item = mv.item
    net_in = Decimal(str(mv.qty_in or 0)) - Decimal(str(mv.qty_out or 0))
    # Undo the net effect on live stock, then record the compensating row.
    new_qty = (item.quantity or 0) - int(net_in)
    if new_qty < 0:
        raise ReversalError(
            "Reversing this entry would drive stock negative — the quantity has "
            "already moved on. Post a stock-count adjustment instead.")
    item.quantity = new_qty
    item.save(update_fields=['quantity'])
    record_movement(
        item, 'reversal', qty_in=(mv.qty_out or 0), qty_out=(mv.qty_in or 0),
        reference=mv.reference, user=admin,
        note=f"Reversal of {mv.get_movement_type_display()} #{mv.pk} "
             f"(correction #{cr.pk})")
    return f"Reversed {mv.get_movement_type_display()} on {item.code}; balance now {new_qty}."
