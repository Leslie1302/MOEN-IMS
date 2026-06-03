"""
Add project_type to BillOfQuantity so the BoQ table can be segregated by
project (SHEP / Cost Sharing / Streetlights / Turnkey / etc.) the same way
the request form and Project model are.

Default 'SHEP' keeps legacy rows usable; new rows can be set explicitly,
and the field is editable from both the BoQ admin and the BoQ table.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0051_receipt_supply_contract_and_overissuance'),
    ]

    operations = [
        migrations.AddField(
            model_name='billofquantity',
            name='project_type',
            field=models.CharField(
                max_length=50,
                db_index=True,
                default='SHEP',
                help_text=(
                    'Project type this BoQ line belongs to. Mirrors the '
                    'ProjectType registry the request form uses so the BoQ '
                    'rolls up correctly under the right programme.'
                ),
            ),
        ),
    ]
