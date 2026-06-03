"""
Add supplier-contract + receipt-category fields to MaterialOrder so receipts
mirror the way releases are tied to consultants via release letters.

- supply_contract:    FK to SupplyContract (the contract this receipt is
                      drawn from). Mirrors how a release is linked to a
                      ReleaseLetter.
- receipt_category:   distinguishes "New Supply" from "Overissuance Return"
                      and other receipt types. Returns are the link into
                      the BoQ overissuance system.
- linked_boq_item:    when the receipt is an Overissuance Return, points
                      at the BoQ line the return is offsetting so the
                      overissuance ledger updates correctly.
"""

from django.db import migrations, models
import django.db.models.deletion
import auto_prefetch


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0050_sitereceipt_boq_match'),
    ]

    operations = [
        migrations.AddField(
            model_name='materialorder',
            name='receipt_category',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('new_supply', 'New Supply'),
                    ('overissuance_return', 'Overissuance Return'),
                    ('transfer_in', 'Inter-Warehouse Transfer In'),
                    ('adjustment', 'Stock Adjustment'),
                ],
                default='new_supply',
                help_text=(
                    'Category for Receipt orders. "Overissuance Return" '
                    'links this receipt into the BoQ overissuance ledger '
                    'so the return offsets the overdrawn quantity.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='materialorder',
            name='supply_contract',
            field=auto_prefetch.ForeignKey(
                to='Inventory.SupplyContract',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='receipt_orders',
                help_text=(
                    'Supply contract this receipt is drawn against. '
                    'Mirrors how a release links to a ReleaseLetter.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='materialorder',
            name='linked_boq_item',
            field=auto_prefetch.ForeignKey(
                to='Inventory.BillOfQuantity',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name='return_receipts',
                help_text=(
                    'For Overissuance Return receipts, the BoQ line being '
                    'offset. quantity_received on that line is reduced by '
                    'the processed quantity of this return.'
                ),
            ),
        ),
    ]
