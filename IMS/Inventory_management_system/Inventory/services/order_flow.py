"""
Order processing — the ONE place quantity gets processed against an order.

Both processing endpoints (the officers' order table and the Store
Operations Hub) call :func:`process_quantity`. Before Phase 3 each view
had its own copy of this math and they had drifted: only one enforced
the signed-letter guard, and only one deducted warehouse stock inline.

Status transitions are EXPLICIT here. ``MaterialOrder.save()`` no longer
recomputes status, so whatever this function (or any other caller) sets
is what sticks.
"""
import logging
from decimal import Decimal

from django.utils import timezone

from ..models import InventoryItem

logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Validation failure the caller should surface to the user (HTTP 400)."""


def process_quantity(order, quantity, user):
    """Process ``quantity`` against ``order``: validate, enforce the
    signed-letter guard, deduct warehouse stock, update quantities and
    status, and save.

    Raises :class:`ProcessingError` with a user-facing message on any
    validation failure. Returns the saved order.

    Caller is responsible for permission checks (who may process) —
    those legitimately differ per page.
    """
    quantity = Decimal(str(quantity))

    if quantity <= 0:
        raise ProcessingError('Quantity must be greater than zero')

    current_processed = order.processed_quantity or Decimal('0')
    remaining = order.quantity - current_processed
    if quantity > remaining:
        raise ProcessingError(
            f'Cannot process {quantity}. Only {remaining} remaining.')

    # SIGNED LETTER GUARD: a Release cannot draw down stock until the
    # signed scan is on file. Applies on EVERY path (the Store Hub used
    # to skip this).
    if order.request_type == 'Release':
        rl = order.release_letter
        if rl is None:
            raise ProcessingError(
                'Cannot release: no release letter has been created for '
                'this order. Generate the release letter first.')
        if not rl.pdf_file:
            raise ProcessingError(
                f'Cannot release: signed copy of release letter '
                f'{rl.code or rl.reference_number or ""} is not attached. '
                f'Upload the signed scan before processing.')

    # Warehouse stock. Deduct inline (with a user-facing error when stock
    # is short) and record the amount on stock_deducted_quantity so the
    # post_save deduction signal — which works on the delta — does not
    # deduct again. Missing inventory item logs a warning but does not
    # block, matching long-standing behaviour for off-inventory releases.
    inventory_item = _pick_inventory_item(order, quantity)
    if inventory_item is None:
        logger.warning(
            f"Inventory item with code '{order.code}' not found "
            f"(warehouse={order.warehouse}). Skipping inventory update.")
    else:
        if order.request_type == 'Release':
            if inventory_item.quantity < quantity:
                raise ProcessingError(
                    f'Insufficient inventory. Available: '
                    f'{inventory_item.quantity}, Requested: {quantity}')
            inventory_item.quantity -= quantity
        elif order.request_type == 'Receipt':
            inventory_item.quantity += quantity
        inventory_item.save()
        order.stock_deducted_quantity = (
            (order.stock_deducted_quantity or 0) + quantity)
        if not order.warehouse_id and inventory_item.warehouse_id:
            order.warehouse = inventory_item.warehouse

    # Quantities + explicit status transition.
    new_processed = current_processed + quantity
    order.processed_quantity = new_processed
    order.remaining_quantity = max(Decimal('0'), order.quantity - new_processed)
    order.status = 'Completed' if order.remaining_quantity <= 0 else 'Partially Fulfilled'

    order.processed_by = user
    order.processed_at = timezone.now()
    order.last_updated_by = user
    order.save()

    logger.info(
        f"Order {order.request_code} processed: +{quantity}, "
        f"total={new_processed}/{order.quantity}")
    return order


def _pick_inventory_item(order, quantity):
    """Locate the InventoryItem to draw from / deposit into.

    Explicit warehouse on the order wins. 'Any warehouse' requests pick
    the warehouse that can satisfy the draw, falling back to the largest
    holder so error messages report a real number.
    """
    if not order.code:
        return None
    if order.warehouse:
        return InventoryItem.objects.filter(
            code=order.code, warehouse=order.warehouse).first()

    candidates = list(
        InventoryItem.objects.filter(code=order.code).order_by('-quantity'))
    if not candidates:
        return None
    if order.request_type == 'Release':
        for cand in candidates:
            if (cand.quantity or 0) >= quantity:
                return cand
    return candidates[0]
