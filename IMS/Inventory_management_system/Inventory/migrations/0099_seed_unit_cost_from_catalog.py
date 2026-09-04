"""Seed each item's unit_cost from its latest active supplier-catalogue price.

The valuation report values stock at ``quantity x unit_cost``. Rather than make
the report join to the price catalogue every time (and pick a rule inline), we
snapshot a starting unit_cost per item here from the most recent active
catalogue entry. It stays editable afterwards, so a price correction is a field
update, not a catalogue dig. Items with no catalogue price keep 0 (unpriced) and
are flagged on the report until someone sets a price.

Idempotent: only fills items whose unit_cost is still 0, so a re-run never
overwrites a price someone has since edited.
"""
from django.db import migrations
from django.utils import timezone


def seed_unit_cost(apps, schema_editor):
    InventoryItem = apps.get_model('Inventory', 'InventoryItem')
    SupplierPriceCatalog = apps.get_model('Inventory', 'SupplierPriceCatalog')

    today = timezone.now().date()
    for item in InventoryItem.objects.filter(unit_cost=0).iterator():
        price = (SupplierPriceCatalog.objects
                 .filter(material_id=item.id, effective_date__lte=today)
                 .exclude(expiry_date__lt=today)
                 .order_by('-effective_date', '-id')
                 .first())
        if price and price.unit_rate:
            item.unit_cost = price.unit_rate
            item.save(update_fields=['unit_cost'])


def unseed(apps, schema_editor):
    # No safe reverse — we can't tell seeded values from later manual edits.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0098_inventoryitem_unit_cost'),
    ]

    operations = [
        migrations.RunPython(seed_unit_cost, unseed),
    ]
