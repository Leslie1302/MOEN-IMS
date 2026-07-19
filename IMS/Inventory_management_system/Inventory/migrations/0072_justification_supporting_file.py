# Adds a real file upload to BoQ overissuance justifications so submitters can
# attach evidence (waybill, memo, photo, signed approval) for managerial review.
# The existing free-text `supporting_documents` field stays as a reference note.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0071_seed_march2026_access_config'),
    ]

    operations = [
        migrations.AddField(
            model_name='boqoverissuancejustification',
            name='supporting_file',
            field=models.FileField(
                blank=True, null=True,
                upload_to='overissuance_justifications/',
                help_text='Upload evidence (waybill, memo, photo, signed approval) '
                          'for the reviewing manager.',
            ),
        ),
    ]
