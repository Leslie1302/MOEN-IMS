# Adds region/district fields to ProjectConsultant and a project_consultant
# FK to Community, mirroring the existing MP binding pattern. This lets the
# consignee resolver look up SHEP consultants by community region the same
# way it looks up MPs by constituency, fixing the "no consultant assigned"
# unresolved-consignee error in the request flow.

from django.db import migrations, models
import auto_prefetch


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0037_releaseletter_project_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectconsultant',
            name='region',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Region this consultant covers. Used by the consignee resolver to auto-bind SHEP communities in this region to the consultant.',
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name='projectconsultant',
            name='district',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Optional. Narrows binding to specific districts within the region.',
                max_length=100,
            ),
        ),
        migrations.AlterModelOptions(
            name='projectconsultant',
            options={
                'base_manager_name': 'prefetch_manager',
                'ordering': ['region', 'name'],
                'verbose_name': 'project consultant',
                'verbose_name_plural': 'project consultants',
            },
        ),
        migrations.AddField(
            model_name='community',
            name='project_consultant',
            field=auto_prefetch.ForeignKey(
                blank=True,
                help_text='Optional explicit consultant binding. If set, used as the consignee for SHEP releases at this community. Otherwise the resolver looks up a consultant by region.',
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name='communities',
                to='Inventory.projectconsultant',
            ),
        ),
    ]
