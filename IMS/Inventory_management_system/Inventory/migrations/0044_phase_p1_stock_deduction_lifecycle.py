# Generated migration for Phase P.1: Stock & BoQ deduction lifecycle
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0043_canonical_groups_refresh'),
    ]

    operations = [
        migrations.AddField(
            model_name='materialorder',
            name='reserved_quantity',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Quantity reserved (soft hold) from warehouse stock. Set on order creation, cleared on release.',
                max_digits=10
            ),
        ),
        migrations.AddField(
            model_name='materialorder',
            name='stock_deducted_quantity',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Quantity actually deducted from warehouse stock. Set when order status='Completed' (storekeeper marks issued).",
                max_digits=10
            ),
        ),
        migrations.AddField(
            model_name='materialorder',
            name='boq_deducted_quantity',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text='Quantity deducted from BoQ after site receipt confirmed. Updated by SiteReceipt.save().',
                max_digits=10
            ),
        ),
    ]
