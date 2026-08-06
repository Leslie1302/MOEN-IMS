# Historical paper requisitions, captured for the record.
#
# A SEPARATE table on purpose. Routing old requisitions through MaterialOrder
# would run them through `order_flow`, which decrements InventoryItem.quantity —
# deducting today's stock for materials that physically left years ago — and
# would consume release codes from the sequence the Registry is adopting.
# Isolation by construction rather than by remembering to filter.

import auto_prefetch
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0083_releaseletter_verify_token'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ArchivedRequisition',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reference', models.CharField(
                    db_index=True, max_length=100, unique=True,
                    help_text='Reference exactly as printed on the original document.')),
                ('document_date', models.DateField(
                    blank=True, db_index=True, null=True,
                    help_text='Date on the document. Leave blank if illegible.')),
                ('request_type', models.CharField(
                    choices=[('Release', 'Release'), ('Receipt', 'Receipt'), ('Unknown', 'Unknown')],
                    db_index=True, default='Release', max_length=20)),
                ('description', models.TextField(
                    help_text='What the requisition was for, in a line or two. Searchable.')),
                ('quantity_summary', models.CharField(
                    blank=True, max_length=300,
                    help_text="Free text, e.g. '2,000 sets stay equipment'. Not used in any calculation.")),
                ('requested_by_name', models.CharField(
                    blank=True, max_length=200,
                    help_text='Name as written on the document. Not linked to a system user — '
                              'the requester may have left the Ministry.')),
                ('approved_by_name', models.CharField(blank=True, max_length=200)),
                ('community', models.CharField(blank=True, db_index=True, max_length=200)),
                ('district', models.CharField(blank=True, max_length=200)),
                ('region', models.CharField(blank=True, db_index=True, max_length=200)),
                ('package_number', models.CharField(blank=True, db_index=True, max_length=200)),
                ('project_type', models.CharField(blank=True, max_length=50)),
                ('scan', models.FileField(
                    blank=True, null=True, upload_to='archive/requisitions/%Y/',
                    help_text='Scan of the original document (PDF or image).')),
                ('notes', models.TextField(blank=True)),
                ('archived_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('import_batch', models.CharField(
                    blank=True, db_index=True, max_length=64,
                    help_text='Groups rows loaded together, so a bad bulk import can be found and undone.')),
                ('archived_by', auto_prefetch.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='archived_requisitions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'archived requisition',
                'verbose_name_plural': 'archived requisitions',
                'ordering': ['-document_date', '-archived_at'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
        ),
        migrations.AddIndex(
            model_name='archivedrequisition',
            index=models.Index(fields=['document_date', 'request_type'],
                               name='inv_arch_date_type_idx'),
        ),
    ]
