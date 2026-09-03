"""Seed the stock ledger with an opening balance per existing item.

The ledger starts empty, but stock already exists. Without a starting row every
tally card would open with a balance of zero and then show only future
movements — which reads as "we have nothing," the opposite of the truth. Past
movements can't be reconstructed (they were never recorded), so go-live is day
zero: each existing InventoryItem gets one 'opening' row equal to its current
quantity. Items created later seed their own opening balance at creation time.

Idempotent: skips any item that already has a movement, so a re-run (or an item
that received stock between deploy steps) is never double-counted.
"""

from django.db import migrations
from django.utils import timezone


def seed_opening_balances(apps, schema_editor):
    InventoryItem = apps.get_model('Inventory', 'InventoryItem')
    StockMovement = apps.get_model('Inventory', 'StockMovement')

    now = timezone.now()
    items_with_history = set(
        StockMovement.objects.values_list('item_id', flat=True).distinct())

    rows = []
    for item in InventoryItem.objects.all().iterator():
        if item.id in items_with_history:
            continue
        qty = item.quantity or 0
        rows.append(StockMovement(
            item_id=item.id,
            movement_type='opening',
            qty_in=qty,
            qty_out=0,
            balance_after=qty,
            reference='Opening balance',
            note='Opening balance at tally-card go-live.',
            created_at=now,
        ))
    if rows:
        StockMovement.objects.bulk_create(rows, batch_size=500)


def unseed_opening_balances(apps, schema_editor):
    StockMovement = apps.get_model('Inventory', 'StockMovement')
    StockMovement.objects.filter(movement_type='opening',
                                 reference='Opening balance').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0095_inventoryitem_reorder_level_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_opening_balances, unseed_opening_balances),
    ]
