# A requisition and the release letter it produced are two documents, and the
# letter is usually the one an auditor asks for — it carries the authorising
# signature. Archiving the requisition alone left half the record.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0084_archived_requisition'),
    ]

    operations = [
        migrations.AddField(
            model_name='archivedrequisition',
            name='release_letter_reference',
            field=models.CharField(
                blank=True, db_index=True, max_length=100,
                help_text='Reference of the release letter issued against this requisition.'),
        ),
        migrations.AddField(
            model_name='archivedrequisition',
            name='release_letter_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='archivedrequisition',
            name='release_letter_scan',
            field=models.FileField(
                blank=True, null=True, upload_to='archive/release_letters/%Y/',
                help_text='Scan of the signed release letter.'),
        ),
        migrations.AlterField(
            model_name='archivedrequisition',
            name='scan',
            field=models.FileField(
                blank=True, null=True, upload_to='archive/requisitions/%Y/',
                help_text='Scan of the original requisition (PDF or image).'),
        ),
    ]
