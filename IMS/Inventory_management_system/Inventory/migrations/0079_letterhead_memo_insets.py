# The letterhead applies to the RELEASE LETTER only. The approval memo is an
# internal document printed on a plain sheet, so it gets its own margins rather
# than inheriting insets calibrated to clear letterhead artwork that isn't there.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0078_letterhead_pdf_and_points'),
    ]

    operations = [
        migrations.AddField(
            model_name='letterhead',
            name='memo_inset_top',
            field=models.PositiveSmallIntegerField(
                default=62, help_text='Approval memo top margin in points (plain sheet).'),
        ),
        migrations.AddField(
            model_name='letterhead',
            name='memo_inset_bottom',
            field=models.PositiveSmallIntegerField(
                default=62, help_text='Approval memo bottom margin in points.'),
        ),
        migrations.AddField(
            model_name='letterhead',
            name='memo_inset_left',
            field=models.PositiveSmallIntegerField(
                default=62, help_text='Approval memo left margin in points.'),
        ),
        migrations.AddField(
            model_name='letterhead',
            name='memo_inset_right',
            field=models.PositiveSmallIntegerField(
                default=62, help_text='Approval memo right margin in points.'),
        ),
    ]
