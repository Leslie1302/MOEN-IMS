from django.db import migrations, models


class Migration(migrations.Migration):
    """Add BoQ-match tracking fields to SiteReceipt so off-BoQ deliveries
    (releases that post against no contract line) are recorded and reportable."""

    dependencies = [
        ('Inventory', '0049_alter_district_unique_together_alter_district_code_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='sitereceipt',
            name='boq_matched',
            field=models.BooleanField(
                default=True,
                help_text='Whether this receipt was successfully posted to a '
                          'Bill of Quantity line. False marks an off-BoQ '
                          'delivery - materials released against no contract line.',
            ),
        ),
        migrations.AddField(
            model_name='sitereceipt',
            name='boq_match_note',
            field=models.TextField(
                blank=True,
                help_text='Explains how this receipt was matched to the Bill '
                          'of Quantity, or why it could not be matched.',
            ),
        ),
    ]
