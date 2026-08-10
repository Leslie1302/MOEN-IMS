# A notification type for "I am blocked on a Bill of Quantity line I cannot fix".
#
# Unmatched BoQ lines now block document generation, and unlike an over-issuance
# the officer has no way to clear one himself — the BoQ may need importing,
# correcting, or the item code may simply be wrong. A block with no door produces
# either a release that stalls silently or an officer who finds a way around the
# check, so the block ships with a route to a system administrator.
#
# Choices-only change: nothing about the column changes, and no data moves.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0090_alter_signingstep_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('material_request', 'Material Request'),
                    ('material_processed', 'Material Processed'),
                    ('transport_assigned', 'Transport Assigned'),
                    ('material_delivered', 'Material Delivered'),
                    ('site_receipt_logged', 'Site Receipt Logged'),
                    ('boq_updated', 'BOQ Updated'),
                    ('staff_prompt', 'Staff Prompt'),
                    ('security_alert', 'Security Alert'),
                    ('signature_requested', 'Signature Requested'),
                    ('discussion_request', 'Call for Discussion'),
                    ('release_urgent', 'Release Marked Urgent'),
                    ('boq_assistance', 'BoQ Assistance Requested'),
                ]),
        ),
    ]
