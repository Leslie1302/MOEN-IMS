# Generated migration for Phase P.2 refactor: Move supply_contract from SiteReceipt to InventoryItem
# Rationale: Store owns inventory once received from supplier. InventoryItem tracks source contract.
# SiteReceipt tracks what sites received from Store (supplier info is historical/irrelevant there).
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0045_phase_p2_supplier_contract_link'),
    ]

    operations = [
        # Remove supply_contract from SiteReceipt
        migrations.RemoveField(
            model_name='sitereceipt',
            name='supply_contract',
        ),

        # Add supply_contract to InventoryItem
        migrations.AddField(
            model_name='inventoryitem',
            name='supply_contract',
            field=models.ForeignKey(
                blank=True,
                help_text="SupplyContract this stock batch was delivered under. Used to reconcile: 'How much of Contract #123 have we released to sites?'",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='inventory_items',
                to='Inventory.supplycontract'
            ),
        ),
    ]
