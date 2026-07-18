# Seeds the national AccessRateConfig from the standardised snapshot
# (ACCESS_RATE_STANDARDISED_V3_1 — National row, March 2026) so the map
# headline reflects the real figure (89.13%) instead of the 0058 placeholder
# (88.85%). Baseline = population electrified as at the snapshot; verified
# meters logged after accrue on top. Added as a NEW dated row — 0058 stays
# for historical reproducibility.

import datetime

from django.db import migrations


NATIONAL = dict(
    persons_per_connection=7,
    baseline_population_access=28_069_007,
    total_population=31_493_525,
    effective_from=datetime.date(2026, 3, 1),
)


def seed(apps, schema_editor):
    AccessRateConfig = apps.get_model('Inventory', 'AccessRateConfig')
    if AccessRateConfig.objects.filter(effective_from=NATIONAL['effective_from']).exists():
        return  # idempotent
    AccessRateConfig.objects.create(
        notes='GSS/Ministry standardised snapshot, National row, March 2026.',
        **NATIONAL,
    )


def unseed(apps, schema_editor):
    AccessRateConfig = apps.get_model('Inventory', 'AccessRateConfig')
    AccessRateConfig.objects.filter(**NATIONAL).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0070_region_population'),
    ]

    operations = [
        migrations.RunPython(seed, reverse_code=unseed),
    ]
