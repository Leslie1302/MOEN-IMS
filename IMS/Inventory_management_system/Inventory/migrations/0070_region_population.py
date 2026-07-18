# Creates RegionPopulation and seeds the 16 regions from the standardised
# access-rate snapshot (ACCESS_RATE_STANDARDISED_V3_1 — "Latest Snapshot
# (Mar 2026)"). Gives each region its own denominator + already-electrified
# baseline so regional access rates are real, not national-denominator
# contributions. Verified meters installed after 2026-03-01 accrue on top.

import datetime

import auto_prefetch
import django.db.models.manager
from django.db import migrations, models


# (region, total_population, baseline_population_access, notes)
SNAPSHOT = [
    ('Ashanti', 5_998_426, 5_583_667, ''),
    ('Ahafo', 530_387, 427_568, 'From Brong Ahafo (2019)'),
    ('Bono', 1_337_483, 1_270_820, 'From Brong Ahafo (2019)'),
    ('Bono East', 1_105_649, 840_402, 'From Brong Ahafo (2019)'),
    ('Central', 2_411_881, 2_325_024, ''),
    ('Eastern', 3_439_905, 3_119_451, ''),
    ('Greater Accra', 5_484_566, 5_407_133, ''),
    ('Northern', 1_930_963, 1_411_054, ''),
    ('North East', 534_461, 357_145, 'From Northern (2019)'),
    ('Savannah', 533_002, 367_285, 'From Northern (2019)'),
    ('Upper East', 1_280_510, 957_191, ''),
    ('Upper West', 876_178, 660_575, ''),
    ('Oti', 816_875, 596_154, 'From Volta (2019)'),
    ('Volta', 2_283_271, 2_106_500, ''),
    ('Western', 1_974_334, 1_859_611, ''),
    ('Western North', 955_634, 779_427, 'From Western (2019)'),
]
SNAPSHOT_DATE = datetime.date(2026, 3, 1)


def seed_region_population(apps, schema_editor):
    RegionPopulation = apps.get_model('Inventory', 'RegionPopulation')
    if RegionPopulation.objects.exists():
        return  # idempotent: never overwrite admin-curated values
    RegionPopulation.objects.bulk_create([
        RegionPopulation(
            region=region,
            total_population=total,
            baseline_population_access=electrified,
            effective_from=SNAPSHOT_DATE,
            notes=notes or 'GSS/Ministry standardised snapshot, Mar 2026.',
        )
        for region, total, electrified, notes in SNAPSHOT
    ])


def unseed_region_population(apps, schema_editor):
    RegionPopulation = apps.get_model('Inventory', 'RegionPopulation')
    RegionPopulation.objects.filter(
        region__in=[r for r, *_ in SNAPSHOT],
        effective_from=SNAPSHOT_DATE,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0069_remove_dead_order_statuses'),
    ]

    operations = [
        migrations.CreateModel(
            name='RegionPopulation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('region', models.CharField(db_index=True, help_text='Region name. Must match the map GeoJSON and Community.region spelling exactly (16 standard regions).', max_length=100, unique=True)),
                ('total_population', models.PositiveBigIntegerField(help_text='Region population — the denominator for this region.')),
                ('baseline_population_access', models.PositiveBigIntegerField(help_text='Population already electrified as at effective_from. The additive constant in the regional numerator.')),
                ('effective_from', models.DateField(help_text='Date the baseline snapshot was struck. Only meters installed after this date add to the regional rate.')),
                ('notes', models.TextField(blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'region population',
                'verbose_name_plural': 'region populations',
                'ordering': ['region'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('prefetch_manager', django.db.models.manager.Manager()),
            ],
        ),
        migrations.RunPython(seed_region_population, reverse_code=unseed_region_population),
    ]
