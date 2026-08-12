# Second scoping dimension: project_type on Profile + ProjectConsultant.
#
# NOTE: this feature was reverted. The file is retained because it was already
# applied to databases and a merge migration (0092) references it by name, so
# removing it breaks the migration graph. Migration 0093 drops the columns this
# adds, leaving models/migrations/DB consistent with the feature removed.

from django.db import migrations, models

_CHOICES = [('SHEP', 'SHEP'), ('COST', 'Cost-sharing'),
            ('STREET', 'Streetlights'), ('SPEC', 'Special/other')]


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0076_letterhead_and_doc_notes'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='project_type',
            field=models.CharField(
                blank=True, max_length=10, choices=_CHOICES,
                help_text="Restrict this user to one programme within their area. "
                          "Blank = all programmes in the area."),
        ),
        migrations.AddField(
            model_name='projectconsultant',
            name='project_type',
            field=models.CharField(
                blank=True, db_index=True, max_length=10, choices=_CHOICES,
                help_text="Programme this consultant covers within the area. Blank = all "
                          "programmes. Lets different consultants hold the same area for "
                          "different projects."),
        ),
    ]
