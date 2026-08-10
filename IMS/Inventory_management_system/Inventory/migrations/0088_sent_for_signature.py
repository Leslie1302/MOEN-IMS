# Records the explicit "send for signature" handover.
#
# Generation notifies nobody — otherwise every draft pesters the Ag. Director
# and people learn to ignore the emails, which is how a signature queue dies.
# Handing a release to the first signatory is therefore a separate act, and
# these two fields are its record.
#
# No backfill. A null here means "never formally sent", which is exactly true of
# every release that predates the button. Guessing a timestamp from the first
# signature would invent a handover that never happened, and the officer's own
# "has this been sent?" question would then be answered with a fabrication.

import auto_prefetch
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Inventory', '0087_approval_queue_and_mmu_fast_track'),
    ]

    operations = [
        migrations.AddField(
            model_name='releaseletter',
            name='sent_for_signature_at',
            field=models.DateTimeField(
                blank=True, null=True, db_index=True,
                help_text='When the preparing officer last sent this release to the '
                          'next signatory.'),
        ),
        migrations.AddField(
            model_name='releaseletter',
            name='sent_for_signature_by',
            field=auto_prefetch.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='releases_sent_for_signature',
                to=settings.AUTH_USER_MODEL),
        ),
    ]
