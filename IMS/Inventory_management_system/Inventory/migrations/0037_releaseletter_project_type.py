# Phase D: adds project_type to ReleaseLetter and backfills from the
# underlying MaterialOrders. Each release letter inherits its project_type
# from its component orders; if those orders span multiple project types
# (which the future ReleaseLetterUploadView guard prevents), the letter
# is left unset and a warning is logged for manual review.

from django.db import migrations, models


def backfill_project_type_from_orders(apps, schema_editor):
    """For each existing ReleaseLetter, derive project_type from its orders."""
    ReleaseLetter = apps.get_model('Inventory', 'ReleaseLetter')
    MaterialOrder = apps.get_model('Inventory', 'MaterialOrder')

    for letter in ReleaseLetter.objects.all():
        types = set(
            MaterialOrder.objects.filter(release_letter=letter)
            .exclude(project_type='')
            .values_list('project_type', flat=True)
        )
        if len(types) == 1:
            letter.project_type = types.pop()
            letter.save(update_fields=['project_type'])
        # else: leave NULL; mixed letters can be reviewed via admin filter.


def reverse_backfill(apps, schema_editor):
    ReleaseLetter = apps.get_model('Inventory', 'ReleaseLetter')
    ReleaseLetter.objects.update(project_type=None)


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0036_add_streetlights_project_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='releaseletter',
            name='project_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('SHEP', 'SHEP'),
                    ('COST', 'Cost-sharing'),
                    ('STREET', 'Streetlights'),
                    ('SPEC', 'Special/other'),
                ],
                help_text='Project type stamped from the underlying MaterialOrders. Drives consignee label rendering.',
                max_length=10,
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_project_type_from_orders,
            reverse_code=reverse_backfill,
        ),
    ]
