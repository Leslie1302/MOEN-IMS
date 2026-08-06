# WYSIWYG document editing: the officer's hand-edited memo/letter body HTML
# becomes the source of truth for both the preview and the minted PDF, with a
# fingerprint of the underlying data so drift after an edit can be flagged.

import auto_prefetch
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0076_letterhead_and_doc_notes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='releaseletter',
            name='memo_html',
            field=models.TextField(blank=True, help_text='Hand-edited approval-memo body (sanitised HTML). Blank = generated from the template.'),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='letter_html',
            field=models.TextField(blank=True, help_text='Hand-edited release-letter body (sanitised HTML). Blank = generated from the template.'),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='memo_html_edited_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='letter_html_edited_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='memo_html_edited_by',
            field=auto_prefetch.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='memo_html_edits', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='letter_html_edited_by',
            field=auto_prefetch.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='letter_html_edits', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='memo_html_fingerprint',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='letter_html_fingerprint',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
