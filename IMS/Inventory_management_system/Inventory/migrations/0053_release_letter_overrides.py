"""
Per-release-event overrides so the schedule officer can pick a different
TO line, FROM line, or Signatory at generation time without a code deploy.

Mirrors the existing Signatory model but on the ReleaseLetter row, so
when someone is acting in place of the default signing officer, the
generated memo + letter pick up the correct names.
"""

from django.db import migrations, models
import django.db.models.deletion
import auto_prefetch


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0052_boq_project_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='releaseletter',
            name='memo_to_override',
            field=models.CharField(
                max_length=200, blank=True,
                help_text="Memo TO line. Defaults to 'CHIEF DIRECTOR'."
            ),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='memo_from_override',
            field=models.CharField(
                max_length=200, blank=True,
                help_text="Memo FROM line. Defaults to the memo signatory's title."
            ),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='memo_signatory_override',
            field=auto_prefetch.ForeignKey(
                to='Inventory.Signatory',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='memo_overrides',
                help_text="Pick a specific signatory for the approval memo. Leave blank to use the default.",
            ),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='letter_signatory_override',
            field=auto_prefetch.ForeignKey(
                to='Inventory.Signatory',
                on_delete=django.db.models.deletion.SET_NULL,
                null=True, blank=True,
                related_name='letter_overrides',
                help_text="Pick a specific signatory for the release letter. Leave blank to use the default.",
            ),
        ),
    ]
