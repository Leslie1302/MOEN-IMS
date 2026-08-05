# Reframe ProjectConsultant onto the area logic: add an `area` FK so a
# consultant covers a whole area (group of regions). region/district stay as
# legacy single-region fallbacks. Consignee resolution now binds by area first.

import auto_prefetch
import django.db.models.deletion
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0074_areas_region_scoping'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectconsultant',
            name='area',
            field=auto_prefetch.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='consultants', to='Inventory.area',
                help_text="Operational area this consultant covers. The consignee "
                          "resolver binds a community to this consultant when the "
                          "community's region is in this area. Primary binding.",
            ),
        ),
    ]
