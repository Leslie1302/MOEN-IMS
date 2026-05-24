# Phase F.5: adds 'Awaiting Transporter' to MaterialTransport.STATUS_CHOICES.
# State-only migration -- the CharField doesn't enforce choices at the DB
# layer, but Django's migration state needs to record the change so future
# makemigrations runs stay clean.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0039_signatory_and_release_workflow_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='materialtransport',
            name='status',
            field=models.CharField(
                choices=[
                    ('Awaiting Transporter', 'Awaiting Transporter Assignment'),
                    ('Loaded', 'Loaded / Ready'),
                    ('In Transit', 'In Transit'),
                    ('Delivered', 'Delivered'),
                    ('Issue', 'Issue Reported'),
                ],
                default='Loaded',
                max_length=20,
            ),
        ),
    ]
