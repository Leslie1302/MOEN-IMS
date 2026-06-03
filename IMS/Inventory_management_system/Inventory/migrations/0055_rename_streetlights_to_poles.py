"""
Rename the 'streetlights' project type to 'poles'.

The programme had been mis-labelled as 'Streetlights' since 0033; in
practice the form releases poles (with the SKU encoding height/material),
not streetlight fixtures. This migration:

  1. Updates the ProjectType row: code='streetlights' → 'poles',
     name='Streetlights' → 'Poles', description refreshed.
  2. Remaps existing MaterialOrder.project_type rows from 'STREET' to
     'POLES' so the historical record matches the new label.
  3. Same for ReleaseLetter.project_type.
  4. Updates the MaterialOrder.project_type and ReleaseLetter.project_type
     CharField choices in Django's migration history (state-only — the
     underlying column is a plain VARCHAR).

Idempotent: re-runs are safe. The ProjectType update is an
``update_or_create``-style upsert keyed by code; the data remap is a
no-op once 'STREET' values have been converted.
"""

from django.db import migrations, models


def rename_streetlights_to_poles(apps, schema_editor):
    """Forward: rename the ProjectType row and remap legacy CharField values."""
    ProjectType   = apps.get_model('Inventory', 'ProjectType')
    MaterialOrder = apps.get_model('Inventory', 'MaterialOrder')
    ReleaseLetter = apps.get_model('Inventory', 'ReleaseLetter')

    # 1. Rename the canonical row. If a 'poles' row somehow already exists
    #    (re-run, manual seed), defer to it and delete the orphan
    #    'streetlights' row if its only purpose was placeholder seeding.
    streetlights = ProjectType.objects.filter(code='streetlights').first()
    poles        = ProjectType.objects.filter(code='poles').first()

    if poles is None and streetlights is not None:
        streetlights.code = 'poles'
        streetlights.name = 'Poles'
        streetlights.description = (
            'Poles releases. Releases consign to the constituency MP. '
            'Pole specs (height / material) live on the InventoryItem SKU; '
            'the request form does not duplicate them as free-text fields.'
        )
        streetlights.save()
    elif poles is not None and streetlights is not None:
        # Both exist — point all FK-bearing rows at 'poles', then drop the
        # 'streetlights' row. Communities are the only known FK referent.
        Community = apps.get_model('Inventory', 'Community')
        Community.objects.filter(project_type=streetlights).update(project_type=poles)
        streetlights.delete()
    # else: poles exists, streetlights doesn't — nothing to do.

    # 2. Remap MaterialOrder.project_type CharField values.
    MaterialOrder.objects.filter(project_type='STREET').update(project_type='POLES')

    # 3. Remap ReleaseLetter.project_type CharField values.
    ReleaseLetter.objects.filter(project_type='STREET').update(project_type='POLES')


def rename_poles_to_streetlights(apps, schema_editor):
    """Reverse: best-effort revert. Keeps system bootable if rolled back."""
    ProjectType   = apps.get_model('Inventory', 'ProjectType')
    MaterialOrder = apps.get_model('Inventory', 'MaterialOrder')
    ReleaseLetter = apps.get_model('Inventory', 'ReleaseLetter')

    poles = ProjectType.objects.filter(code='poles').first()
    if poles is not None:
        poles.code = 'streetlights'
        poles.name = 'Streetlights'
        poles.description = 'Streetlight installations. Releases consign to the constituency MP.'
        poles.save()

    MaterialOrder.objects.filter(project_type='POLES').update(project_type='STREET')
    ReleaseLetter.objects.filter(project_type='POLES').update(project_type='STREET')


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0054_merge_20260531_1651'),
    ]

    operations = [
        # State-only choice updates: the underlying VARCHAR doesn't enforce
        # these, but Django's migration history needs to record the change
        # so `makemigrations` runs cleanly going forward.
        migrations.AlterField(
            model_name='materialorder',
            name='project_type',
            field=models.CharField(
                choices=[
                    ('SHEP', 'SHEP'),
                    ('COST', 'Cost-sharing'),
                    ('POLES', 'Poles'),
                    ('SPEC', 'Special/other'),
                ],
                default='SHEP',
                help_text='Type of project this request is for',
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name='releaseletter',
            name='project_type',
            field=models.CharField(
                choices=[
                    ('SHEP', 'SHEP'),
                    ('COST', 'Cost-sharing'),
                    ('POLES', 'Poles'),
                    ('SPEC', 'Special/other'),
                ],
                blank=True,
                null=True,
                help_text='Project type stamped from the underlying MaterialOrders. Drives consignee label rendering.',
                max_length=10,
            ),
        ),
        migrations.RunPython(rename_streetlights_to_poles, reverse_code=rename_poles_to_streetlights),
    ]
