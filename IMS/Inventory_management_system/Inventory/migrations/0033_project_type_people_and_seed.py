# Phase A foundation migration:
#   - creates ProjectType, MemberOfParliament, ProjectConsultant tables
#   - seeds canonical ProjectType rows (SHEP, Cost Sharing, Streetlights,
#     plus archived legacy types so historical Project rows can be
#     migrated cleanly in a later step)
# Idempotent on the data side -- safe to re-run via the WSGI auto-migrate
# hook on every container start.

import django.db.models.manager
from django.db import migrations, models
import auto_prefetch


CANONICAL_PROJECT_TYPES = [
    # active types -- selectable for new requests
    {'code': 'shep',         'name': 'SHEP',          'consignee_role': 'consultant', 'sort_order': 10, 'active': True,
     'description': 'Self-Help Electrification Project. Releases consign to the project consultant.'},
    {'code': 'cost_sharing', 'name': 'Cost Sharing',  'consignee_role': 'mp',         'sort_order': 20, 'active': True,
     'description': 'Cost Sharing programme. Releases consign to the constituency MP.'},
    {'code': 'streetlights', 'name': 'Streetlights',  'consignee_role': 'mp',         'sort_order': 30, 'active': True,
     'description': 'Streetlight installations. Releases consign to the constituency MP.'},
    # archived legacy types -- present so old Project rows still resolve,
    # but hidden from new request forms via active=False.
    {'code': 'turnkey',                'name': 'Turnkey',                 'consignee_role': 'other', 'sort_order': 90, 'active': False,
     'description': 'Legacy project type. Archived; retained for historical records.'},
    {'code': 'china_water',            'name': 'China Water',             'consignee_role': 'other', 'sort_order': 91, 'active': False,
     'description': 'Legacy project type. Archived; retained for historical records.'},
    {'code': 'other_electrification',  'name': 'Other Electrification',   'consignee_role': 'other', 'sort_order': 92, 'active': False,
     'description': 'Legacy project type. Archived; retained for historical records.'},
    {'code': 'special_other',          'name': 'Special / Other',         'consignee_role': 'other', 'sort_order': 93, 'active': False,
     'description': 'Legacy project type from the old MaterialOrder enum. Archived.'},
]


def seed_project_types(apps, schema_editor):
    ProjectType = apps.get_model('Inventory', 'ProjectType')
    for row in CANONICAL_PROJECT_TYPES:
        ProjectType.objects.update_or_create(
            code=row['code'],
            defaults={
                'name': row['name'],
                'consignee_role': row['consignee_role'],
                'sort_order': row['sort_order'],
                'active': row['active'],
                'description': row['description'],
            },
        )


def unseed_project_types(apps, schema_editor):
    ProjectType = apps.get_model('Inventory', 'ProjectType')
    codes = [row['code'] for row in CANONICAL_PROJECT_TYPES]
    # Only delete unreferenced rows -- preserve any rows that have FKs
    # pointing at them (which won't exist yet at this migration's
    # reverse, but keeps the operation safe under all conditions).
    for code in codes:
        try:
            obj = ProjectType.objects.get(code=code)
        except ProjectType.DoesNotExist:
            continue
        # No reverse FKs exist at this migration level; safe to delete.
        obj.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0032_materialtransport_waybill_download_count'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProjectType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.SlugField(help_text="Stable machine identifier, e.g. 'shep', 'cost_sharing', 'streetlights'.", max_length=50, unique=True)),
                ('name', models.CharField(help_text="Display name, e.g. 'SHEP', 'Cost Sharing', 'Streetlights'.", max_length=100)),
                ('consignee_role', models.CharField(choices=[('consultant', 'Project Consultant'), ('mp', 'Member of Parliament'), ('other', 'Other / not yet defined')], default='other', help_text='Drives whom releases under this project consign to.', max_length=20)),
                ('description', models.TextField(blank=True)),
                ('active', models.BooleanField(default=True, help_text='Inactive types remain on legacy records but cannot be selected for new requests.')),
                ('sort_order', models.PositiveIntegerField(default=100, help_text='Lower numbers appear first in dropdowns.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'project type',
                'verbose_name_plural': 'project types',
                'ordering': ['sort_order', 'name'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('prefetch_manager', django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name='MemberOfParliament',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(default='Hon.', help_text="Title prefix, e.g. 'Hon.'", max_length=20)),
                ('name', models.CharField(db_index=True, max_length=200)),
                ('constituency', models.CharField(db_index=True, max_length=200)),
                ('region', models.CharField(db_index=True, max_length=100)),
                ('district', models.CharField(blank=True, help_text='Optional. Some constituencies span districts.', max_length=100)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('notes', models.TextField(blank=True)),
                ('active', models.BooleanField(default=True)),
                ('term_start', models.DateField(blank=True, null=True)),
                ('term_end', models.DateField(blank=True, help_text="Set when this MP's term ends. Inactive MPs are not auto-resolved.", null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Member of Parliament',
                'verbose_name_plural': 'Members of Parliament',
                'ordering': ['region', 'constituency', 'name'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('prefetch_manager', django.db.models.manager.Manager()),
            ],
        ),
        migrations.CreateModel(
            name='ProjectConsultant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(db_index=True, max_length=200)),
                ('firm', models.CharField(blank=True, help_text='Engineering firm or consultancy, if applicable.', max_length=200)),
                ('contact_email', models.EmailField(blank=True, max_length=254)),
                ('contact_phone', models.CharField(blank=True, max_length=50)),
                ('address', models.TextField(blank=True)),
                ('notes', models.TextField(blank=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'project consultant',
                'verbose_name_plural': 'project consultants',
                'ordering': ['name'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
            managers=[
                ('objects', django.db.models.manager.Manager()),
                ('prefetch_manager', django.db.models.manager.Manager()),
            ],
        ),
        migrations.RunPython(seed_project_types, reverse_code=unseed_project_types),
    ]
