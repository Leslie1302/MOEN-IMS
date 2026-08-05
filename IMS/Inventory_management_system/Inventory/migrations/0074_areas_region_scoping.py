# Operational areas for region scoping. Creates Area + AreaRegion, adds
# Profile.area, and seeds the 10 areas (each a group of whole regions that
# share a consultant + officer team).

import auto_prefetch
import django.db.models.deletion
from django.db import migrations, models


AREAS = {
    'Ashanti': ['Ashanti'],
    'Greater Accra & Eastern': ['Greater Accra', 'Eastern'],
    'Ahafo, Bono & Bono East': ['Ahafo', 'Bono', 'Bono East'],
    'Volta & Oti': ['Volta', 'Oti'],
    'Central': ['Central'],
    'Western & Western North': ['Western', 'Western North'],
    'Upper East': ['Upper East'],
    'Northern & Savannah': ['Northern', 'Savannah'],
    'North East': ['North East'],
    'Upper West': ['Upper West'],
}


def seed_areas(apps, schema_editor):
    Area = apps.get_model('Inventory', 'Area')
    AreaRegion = apps.get_model('Inventory', 'AreaRegion')
    if Area.objects.exists():
        return  # idempotent
    for name, regions in AREAS.items():
        area = Area.objects.create(name=name)
        AreaRegion.objects.bulk_create(
            [AreaRegion(area=area, region=r) for r in regions])


def unseed_areas(apps, schema_editor):
    Area = apps.get_model('Inventory', 'Area')
    Area.objects.filter(name__in=list(AREAS)).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0073_add_security_alert_notification_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='Area',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={'verbose_name': 'area', 'verbose_name_plural': 'areas', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='AreaRegion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('region', models.CharField(db_index=True, max_length=100)),
                ('area', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='regions', to='Inventory.area')),
            ],
            options={'ordering': ['region'], 'unique_together': {('area', 'region')}},
        ),
        migrations.AddField(
            model_name='profile',
            name='area',
            field=auto_prefetch.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='members', to='Inventory.area', help_text="Operational area. Scoped roles (consultants, schedule officers) only see data for this area's regions. Leave blank for management/superusers."),
        ),
        migrations.RunPython(seed_areas, reverse_code=unseed_areas),
    ]
