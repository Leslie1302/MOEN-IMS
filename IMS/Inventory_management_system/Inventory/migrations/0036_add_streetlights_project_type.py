# Phase C foundation: extends MaterialOrder.project_type CharField choices
# to include 'STREET' so Streetlights material requests can be saved via
# the two-step request flow added in this phase.
#
# This is a state-only migration -- the underlying SQLite column is just a
# VARCHAR(10) and doesn't enforce choices, but Django's migration history
# needs to record the choice change so future makemigrations runs are clean.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0035_community_unique_per_project'),
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
    ]
