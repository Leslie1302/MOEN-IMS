# Ministry letterhead for generated release documents + free-text notes fields
# on ReleaseLetter (the HTMS `notes` equivalent, editable on Adjust & preview).

import auto_prefetch
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0075_projectconsultant_area'),
    ]

    operations = [
        migrations.CreateModel(
            name='Letterhead',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='Ministry Letterhead', help_text='Label for this letterhead configuration (admin only).', max_length=120)),
                ('image', models.ImageField(blank=True, null=True, help_text='The Ministry letterhead image (PNG/JPG). Rendered as the page header band.', upload_to='letterhead/')),
                ('pre_printed', models.BooleanField(default=False, help_text="Printing on pre-printed Ministry paper: leave the header blank and only reserve the top inset.")),
                ('inset_top', models.PositiveSmallIntegerField(default=45, help_text='Top margin (mm). Space reserved for the letterhead band.')),
                ('inset_right', models.PositiveSmallIntegerField(default=22, help_text='Right margin (mm).')),
                ('inset_bottom', models.PositiveSmallIntegerField(default=22, help_text='Bottom margin (mm).')),
                ('inset_left', models.PositiveSmallIntegerField(default=22, help_text='Left margin (mm).')),
                ('org_name', models.CharField(blank=True, default='Ministry of Energy and Green Transition', max_length=200)),
                ('org_address', models.CharField(blank=True, default='P.O. Box SD 40, Accra', max_length=300)),
                ('org_contact', models.CharField(blank=True, default='', max_length=300)),
                ('active', models.BooleanField(default=True, help_text='Only the most recently updated active row is used.')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'letterhead',
                'verbose_name_plural': 'letterheads',
                'ordering': ['-updated_at'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='memo_notes',
            field=models.TextField(blank=True, help_text='Optional extra paragraph added to the approval memo body.'),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='letter_notes',
            field=models.TextField(blank=True, help_text='Optional extra paragraph added to the release letter body.'),
        ),
    ]
