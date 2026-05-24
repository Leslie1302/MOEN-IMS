# Bug fix: lets the same physical community be served under multiple
# project types. The previous unique_together (region, district, community,
# package_number) failed for non-SHEP rows because package_number is empty
# for Cost Sharing and Streetlights -- two rows for the same community
# under different non-SHEP projects collide on ('Greater Accra', 'Ga East',
# 'Abokobi', '').
#
# Adding project_type to the tuple disambiguates the non-SHEP case while
# preserving the SHEP behaviour (each SHEP row has its own package_number,
# so the constraint is still tight there too).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0034_rename_shep_to_community'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='community',
            unique_together={
                ('region', 'district', 'community', 'package_number', 'project_type'),
            },
        ),
    ]
