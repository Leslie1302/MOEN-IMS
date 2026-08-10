# Phases 3-5: the approval queue, calls for discussion, and the MMU fast-track.
#
# Three additions, none of which change existing behaviour on its own:
#
#   * `DiscussionRequest` — a signatory asking the preparing officer to talk.
#     Deliberately not a reject state; nothing here moves the workflow.
#   * `ReleaseLetter.advance_notice_at` — when the signing chain completed, so
#     MMU's list can filter on "signed, may prepare". Stored rather than derived
#     because `signing_complete()` walks the chain per row.
#   * Notification types for the signing chain, addressed to a named user. A
#     signature request addressed to "Management" is addressed to nobody.
#
# Backfill note: `advance_notice_at` is set for releases already fully signed,
# so MMU's list is correct on the morning after deployment rather than only for
# releases signed from then on.

import auto_prefetch
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def backfill_advance_notice(apps, schema_editor):
    """Put already-signed releases on advance notice.

    Without this, every release signed before the upgrade is invisible to MMU's
    new filter, and the first thing MMU learns about the feature is that it
    appears to be empty.

    `signing_complete()` is not available on a historical model, so the chain is
    walked here directly against the same rule: every active required step must
    carry an unsuperseded signature.
    """
    SigningStep = apps.get_model('Inventory', 'SigningStep')
    ReleaseLetter = apps.get_model('Inventory', 'ReleaseLetter')
    DocumentSignature = apps.get_model('Inventory', 'DocumentSignature')

    required = set(SigningStep.objects.filter(active=True, required=True)
                   .values_list('pk', flat=True))
    if not required:
        return

    candidates = ReleaseLetter.objects.filter(
        advance_notice_at__isnull=True).exclude(
        workflow_status__in=('released', 'voided'))

    for release in candidates:
        signatures = list(DocumentSignature.objects.filter(
            release_letter=release, superseded=False))
        if not signatures:
            continue
        if not required.issubset({s.step_id for s in signatures}):
            continue
        # The moment the chain completed is the moment of the last signature —
        # a truer record than "when this migration happened to run".
        release.advance_notice_at = max(s.signed_at for s in signatures)
        release.save(update_fields=['advance_notice_at'])


def noop(apps, schema_editor):
    """Clearing the field on reverse would discard nothing that matters."""


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('Inventory', '0086_signing_step_single_sequence'),
    ]

    operations = [
        migrations.AddField(
            model_name='releaseletter',
            name='advance_notice_at',
            field=models.DateTimeField(
                blank=True, null=True, db_index=True,
                help_text='When the digital signing chain completed. Advance notice to '
                          'MMU: prepare only, do not release.'),
        ),
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
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
                ],
                max_length=30),
        ),
        migrations.CreateModel(
            name='DiscussionRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('document_kind', models.CharField(
                    blank=True, max_length=10,
                    choices=[('memo', 'Approval memo'), ('letter', 'Release letter')],
                    help_text='The document prompting the call, if the signatory named one.')),
                ('note', models.TextField(help_text='What the signatory wants to discuss.')),
                ('created_at', models.DateTimeField(
                    db_index=True, default=django.utils.timezone.now)),
                ('email_sent', models.BooleanField(default=False)),
                ('email_error', models.CharField(blank=True, max_length=400)),
                ('officer', auto_prefetch.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='discussion_requests_received',
                    to=settings.AUTH_USER_MODEL,
                    help_text='The officer who prepared the release, and who is being called.')),
                ('raised_by', auto_prefetch.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='discussion_requests_raised',
                    to=settings.AUTH_USER_MODEL)),
                ('release_letter', auto_prefetch.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='discussion_requests', to='Inventory.releaseletter')),
            ],
            options={
                'verbose_name': 'discussion request',
                'verbose_name_plural': 'discussion requests',
                'ordering': ['-created_at'],
                'base_manager_name': 'prefetch_manager',
            },
        ),
        migrations.RunPython(backfill_advance_notice, noop),
    ]
