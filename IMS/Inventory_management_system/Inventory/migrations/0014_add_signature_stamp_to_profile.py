# Generated manually for adding signature_stamp field to Profile model

from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Migration to add signature_stamp field to the Profile model.
    This field stores a unique digital signature stamp for each user.
    """

    dependencies = [
        ('Inventory', '0013_add_consignment_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='signature_stamp',
            field=models.CharField(
                blank=True,
                help_text='Unique digital signature stamp for this user',
                max_length=500,
                null=True
            ),
        ),
    ]
