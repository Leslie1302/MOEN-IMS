# Generated migration for Phase P.2: Supplier-contract FK on SiteReceipt
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0044_phase_p1_stock_deduction_lifecycle'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitereceipt',
            name='supply_contract',
            field=models.ForeignKey(
                blank=True,
                help_text='SupplyContract this receipt was issued under. Used for reconciliation against supplier deliverables.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='site_receipts',
                to='Inventory.supplycontract'
            ),
        ),
    ]
