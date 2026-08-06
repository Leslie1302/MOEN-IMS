# Letterhead rework:
#   * accept a PDF (or PNG/JPEG) scan of the printed letterhead, not just an
#     image — so `image` (ImageField) becomes `file` (FileField + extension
#     validator), with a generated `preview_image` raster for the calibration UI;
#   * store the printable-area insets in POINTS rather than millimetres, which
#     is the unit WeasyPrint's @page rule and PyMuPDF both work in and what the
#     drag-to-calibrate editor displays.
#
# Existing rows are converted mm -> pt so a letterhead calibrated before this
# migration keeps the same physical margins.

import django.core.validators
from django.db import migrations, models

PT_PER_MM = 2.834645669


def mm_to_pt(apps, schema_editor):
    Letterhead = apps.get_model('Inventory', 'Letterhead')
    for lh in Letterhead.objects.all():
        lh.inset_top = min(32767, round(lh.inset_top * PT_PER_MM))
        lh.inset_bottom = min(32767, round(lh.inset_bottom * PT_PER_MM))
        lh.inset_left = min(32767, round(lh.inset_left * PT_PER_MM))
        lh.inset_right = min(32767, round(lh.inset_right * PT_PER_MM))
        lh.save(update_fields=['inset_top', 'inset_bottom', 'inset_left', 'inset_right'])


def pt_to_mm(apps, schema_editor):
    Letterhead = apps.get_model('Inventory', 'Letterhead')
    for lh in Letterhead.objects.all():
        lh.inset_top = round(lh.inset_top / PT_PER_MM)
        lh.inset_bottom = round(lh.inset_bottom / PT_PER_MM)
        lh.inset_left = round(lh.inset_left / PT_PER_MM)
        lh.inset_right = round(lh.inset_right / PT_PER_MM)
        lh.save(update_fields=['inset_top', 'inset_bottom', 'inset_left', 'inset_right'])


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0077_releaseletter_document_html'),
    ]

    operations = [
        # Convert the stored millimetres BEFORE the field help text changes, so
        # the data and the semantics flip together.
        migrations.RunPython(mm_to_pt, pt_to_mm),

        migrations.RenameField(
            model_name='letterhead', old_name='image', new_name='file',
        ),
        migrations.AlterField(
            model_name='letterhead',
            name='file',
            field=models.FileField(
                blank=True, null=True, upload_to='letterhead/',
                validators=[django.core.validators.FileExtensionValidator(['pdf', 'png', 'jpg', 'jpeg'])],
                help_text='Scan of the printed letterhead - full A4 page, PDF/PNG/JPEG.'),
        ),
        migrations.AddField(
            model_name='letterhead',
            name='preview_image',
            field=models.ImageField(
                blank=True, null=True, editable=False, upload_to='letterhead/preview/',
                help_text='Auto-generated raster preview of page 1.'),
        ),
        migrations.AlterField(
            model_name='letterhead',
            name='inset_top',
            field=models.PositiveSmallIntegerField(
                default=184, help_text='Points from the top edge - where the letterhead header ends.'),
        ),
        migrations.AlterField(
            model_name='letterhead',
            name='inset_bottom',
            field=models.PositiveSmallIntegerField(
                default=106, help_text='Points from the bottom edge - where the footer begins.'),
        ),
        migrations.AlterField(
            model_name='letterhead',
            name='inset_left',
            field=models.PositiveSmallIntegerField(
                default=73, help_text='Points from the left edge.'),
        ),
        migrations.AlterField(
            model_name='letterhead',
            name='inset_right',
            field=models.PositiveSmallIntegerField(
                default=62, help_text='Points from the right edge.'),
        ),
        migrations.AlterField(
            model_name='letterhead',
            name='pre_printed',
            field=models.BooleanField(
                default=False,
                help_text='Printing on pre-printed Ministry paper: draw nothing, just reserve the insets.'),
        ),
    ]
