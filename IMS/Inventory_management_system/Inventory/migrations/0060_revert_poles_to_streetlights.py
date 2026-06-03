"""
Revert migration 0055.

The 'streetlights' -> 'poles' rename was made in error: the programme is
in fact Streetlights (the SKU encodes pole specs). This migration:

  1. Renames the ProjectType row back: code='poles' -> 'streetlights',
     name='Poles' -> 'Streetlights'.
  2. Remaps MaterialOrder.project_type and ReleaseLetter.project_type
     CharField values from 'POLES' back to 'STREET'.
  3. Restores the state-only AlterField choices on those two models so
     Django's migration history stays clean going forward.

Idempotent: re-runs are safe. Forward = undo 0055; reverse = redo 0055.
"""

from django.db import migrations, models


def revert_poles_to_streetlights(apps, schema_editor):
    """Forward: undo the 0055 rename."""
    ProjectType   = apps.get_model('Inventory', 'ProjectType')
    MaterialOrder = apps.get_model('Inventory', 'MaterialOrder')
    ReleaseLetter = apps.get_model('Inventory', 'ReleaseLetter')

    poles        = ProjectType.objects.filter(code='poles').first()
    streetlights = ProjectType.objects.filter(code='streetlights').first()

    if streetlights is None and poles is not None:
        poles.code = 'streetlights'
        poles.name = 'Streetlights'
        poles.description = 'Streetlight installations. Releases consign to the constituency MP.'
        poles.save()
    elif streetlights is not None and poles is not None:
        Community = apps.get_model('Inventory', 'Community')
        Community.objects.filter(project_type=poles).update(project_type=streetlights)
        poles.delete()

    MaterialOrder.objects.filter(project_type='POLES').update(project_type='STREET')
    ReleaseLetter.objects.filter(project_type='POLES').update(project_type='STREET')


def redo_rename_to_poles(apps, schema_editor):
    """Reverse: re-apply 0055."""
    ProjectType   = apps.get_model('Inventory', 'ProjectType')
    MaterialOrder = apps.get_model('Inventory', 'MaterialOrder')
    ReleaseLetter = apps.get_model('Inventory', 'ReleaseLetter')

    streetlights = ProjectType.objects.filter(code='streetlights').first()
    if streetlights is not None:
        streetlights.code = 'poles'
        streetlights.name = 'Poles'
        streetlights.description = 'Poles releases. Releases consign to the constituency MP.'
        streetlights.save()

    MaterialOrder.objects.filter(project_type='STREET').update(project_type='POLES')
    ReleaseLetter.objects.filter(project_type='STREET').update(project_type='POLES')


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0059_projectsite_works_status_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='materialorder',
            name='project_type',
            field=models.CharField(
                choices=[
                    ('SHEP', 'SHEP'),
                    ('COST', 'Cost-sharing'),
                    ('STREET', 'Streetlights'),
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
                    ('STREET', 'Streetlights'),
                    ('SPEC', 'Special/other'),
                ],
                blank=True,
                null=True,
                help_text='Project type stamped from the underlying MaterialOrders. Drives consignee label rendering.',
                max_length=10,
            ),
        ),
        migrations.RunPython(revert_poles_to_streetlights, reverse_code=redo_rename_to_poles),
    ]
