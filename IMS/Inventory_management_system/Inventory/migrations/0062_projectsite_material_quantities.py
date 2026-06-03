# Site Progress: quantify materials used to progress works.
# Additive fields on ProjectSite; meter totals drive the access rate via
# MeterInstallation rows created in the site_progress_edit view.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0061_projectsite_progress_notes_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectsite',
            name='meters_1ph_installed',
            field=models.PositiveIntegerField(default=0, help_text='Single-phase meters installed at this site to date. Increasing this logs the difference as a MeterInstallation so the national access rate rises.'),
        ),
        migrations.AddField(
            model_name='projectsite',
            name='meters_3ph_installed',
            field=models.PositiveIntegerField(default=0, help_text='Three-phase meters installed at this site to date. Increasing this logs the difference as a MeterInstallation so the national access rate rises.'),
        ),
        migrations.AddField(
            model_name='projectsite',
            name='poles_erected',
            field=models.PositiveIntegerField(default=0, help_text='Poles erected at this site to date.'),
        ),
        migrations.AddField(
            model_name='projectsite',
            name='conductor_laid_m',
            field=models.DecimalField(decimal_places=2, default=0, help_text='Conductor / cable strung at this site to date, in metres.', max_digits=10),
        ),
        migrations.AddField(
            model_name='projectsite',
            name='transformers_installed',
            field=models.PositiveIntegerField(default=0, help_text='Distribution transformers installed at this site to date.'),
        ),
        migrations.AddField(
            model_name='projectsite',
            name='transformers_commissioned',
            field=models.PositiveIntegerField(default=0, help_text='Distribution transformers commissioned (energised and handed over) at this site to date.'),
        ),
    ]
