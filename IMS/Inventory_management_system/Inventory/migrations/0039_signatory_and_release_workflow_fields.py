# Phase F.1 foundation:
#   - Creates Signatory model + seeds the current signatories.
#   - Adds workflow fields to ReleaseLetter: code (RE-yyyy-NNNN),
#     workflow_status, memo_pdf/letter_pdf FileFields, two-person scan
#     review fields.
#
# All ReleaseLetter additions are nullable/optional so this slots onto
# existing rows without breaking the legacy upload-the-scan flow.

from django.db import migrations, models
import django.db.models.deletion
import auto_prefetch


SEED_SIGNATORIES = [
    {
        'name': 'Ing. Sulemana Abubakari',
        'title': 'Ag. Director, Power',
        'is_default_for_release_memo': True,
        'is_default_for_release_letter': False,
        'is_default_for_payment_memo': True,
        'signs_for': '',
        'notes': 'Signs the approval memos for both release-side (Phase F) and payment-side (Phase I) workflows.',
    },
    {
        'name': 'Solomon Adjetey Sowah',
        'title': 'Chief Director',
        'is_default_for_release_memo': False,
        'is_default_for_release_letter': True,
        'is_default_for_payment_memo': False,
        'signs_for': 'HON. MINISTER',
        'notes': 'Signs release letters to MMU on behalf of the Hon. Minister of Energy and Green Transition.',
    },
]


def seed_signatories(apps, schema_editor):
    Signatory = apps.get_model('Inventory', 'Signatory')
    for row in SEED_SIGNATORIES:
        Signatory.objects.update_or_create(
            name=row['name'], title=row['title'],
            defaults={
                'is_default_for_release_memo': row['is_default_for_release_memo'],
                'is_default_for_release_letter': row['is_default_for_release_letter'],
                'is_default_for_payment_memo': row['is_default_for_payment_memo'],
                'signs_for': row['signs_for'],
                'notes': row['notes'],
                'active': True,
            },
        )


def unseed_signatories(apps, schema_editor):
    Signatory = apps.get_model('Inventory', 'Signatory')
    for row in SEED_SIGNATORIES:
        Signatory.objects.filter(name=row['name'], title=row['title']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0038_consultant_region_binding'),
    ]

    operations = [
        migrations.CreateModel(
            name='Signatory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text="Full name as it should appear on the signature line (e.g. 'Ing. Sulemana Abubakari').", max_length=200)),
                ('title', models.CharField(help_text="Official title as it should appear under the signature line (e.g. 'Ag. Director, Power').", max_length=200)),
                ('is_default_for_release_memo', models.BooleanField(default=False, help_text='Signs the Director-Power approval memo (Phase F).')),
                ('is_default_for_release_letter', models.BooleanField(default=False, help_text="Signs the release letter to MMU (Phase F). Typically Chief Director 'FOR: HON. MINISTER'.")),
                ('is_default_for_payment_memo', models.BooleanField(default=False, help_text='Signs the payment-approval memo (Phase I).')),
                ('signs_for', models.CharField(blank=True, help_text="Optional. Appears under the title as 'FOR: <value>'. Used on the release letter where the Chief Director signs on behalf of the Hon. Minister.", max_length=200)),
                ('active', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'signatory',
                'verbose_name_plural': 'signatories',
                'ordering': ['-updated_at'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
        ),
        migrations.RunPython(seed_signatories, reverse_code=unseed_signatories),

        # ReleaseLetter workflow fields
        migrations.AddField(
            model_name='releaseletter',
            name='code',
            field=models.CharField(
                blank=True, db_index=True, max_length=30, null=True, unique=True,
                help_text='System-generated release event code in the format RE-{year}-{4-digit-seq}. Printed on both the memo and the release letter, encoded in the QR code on the letter. Auto-populated on save when blank.',
            ),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='workflow_status',
            field=models.CharField(
                choices=[
                    ('draft', 'Draft'),
                    ('memo_generated', 'Memo & letter generated'),
                    ('awaiting_signature', 'Awaiting CD signature'),
                    ('awaiting_scan_upload', 'Awaiting scan upload'),
                    ('approved', 'Approved (signed scan on file)'),
                    ('released', 'Released'),
                    ('voided', 'Voided'),
                    ('reissued', 'Reissued'),
                ],
                default='draft', max_length=30,
                help_text="State-machine position. 'memo_generated' is set automatically when the PDFs are produced; 'approved' is set when a signed scan is uploaded and confirmed.",
            ),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='memo_pdf',
            field=models.FileField(
                blank=True, null=True, upload_to='release_events/%Y/%m/memo/',
                help_text='System-generated approval memo (PDF, before wet signature).',
            ),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='letter_pdf',
            field=models.FileField(
                blank=True, null=True, upload_to='release_events/%Y/%m/letter/',
                help_text='System-generated release letter to MMU (PDF, before wet signature). Carries QR code with the release code.',
            ),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='documents_generated_at',
            field=models.DateTimeField(blank=True, null=True, help_text='When the memo + letter PDFs were generated.'),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='documents_generated_by',
            field=auto_prefetch.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='generated_release_documents',
                to='auth.user',
            ),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='scan_uploaded_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='scan_confirmed_by',
            field=auto_prefetch.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='confirmed_release_scans',
                to='auth.user',
                help_text='The second person who verified the uploaded scan matches the physical letter. Must differ from the uploader.',
            ),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='scan_confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
