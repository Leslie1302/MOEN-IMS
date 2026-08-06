# Phase 0 + Phase 1 of IMPLEMENTATION_PLAN_signing_2026-08-06.md
#
#   * ReleaseCodeSequence — a registry-grade allocator. The old Max(code)+1
#     emitted `SELECT MAX(...) FOR UPDATE`, which PostgreSQL rejects outright,
#     and raced besides. The data migration seeds the counter past every code
#     already issued so the switchover cannot collide.
#   * SigningStep / DocumentSignature — the configurable approval chain and the
#     audit record of each signature.
#   * Designations on Profile, a user link on Signatory, version/lock/urgency
#     fields on ReleaseLetter, and sent-version fields on DocumentDispatch.

import auto_prefetch
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def seed_code_sequence(apps, schema_editor):
    """Advance each year's counter past codes issued by the old allocator.

    Without this the new counter starts at 0 and immediately collides with
    existing codes. Parses the trailing digit group rather than assuming a
    format, so codes issued under any earlier convention are still understood.
    """
    import re

    ReleaseLetter = apps.get_model('Inventory', 'ReleaseLetter')
    ReleaseCodeSequence = apps.get_model('Inventory', 'ReleaseCodeSequence')

    trailing_digits = re.compile(r'(\d+)\D*$')
    highest_by_year = {}

    for code in ReleaseLetter.objects.filter(code__isnull=False).values_list('code', flat=True):
        if not code:
            continue
        years = re.findall(r'(20\d{2})', code)
        if not years:
            continue
        year = int(years[0])
        match = trailing_digits.search(code)
        if not match:
            continue
        sequence = int(match.group(1))
        if sequence > highest_by_year.get(year, 0):
            highest_by_year[year] = sequence

    for year, sequence in highest_by_year.items():
        ReleaseCodeSequence.objects.update_or_create(
            year=year, defaults={'last_sequence': sequence})


def unseed(apps, schema_editor):
    apps.get_model('Inventory', 'ReleaseCodeSequence').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0081_document_dispatch'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Phase 0: the allocator ──────────────────────────────────────────
        migrations.CreateModel(
            name='ReleaseCodeSequence',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveIntegerField(db_index=True, unique=True)),
                ('last_sequence', models.PositiveIntegerField(
                    default=0,
                    help_text='Highest sequence number issued for this year. Never decreases.')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'release code sequence',
                'verbose_name_plural': 'release code sequences',
                'ordering': ['-year'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
        ),
        migrations.RunPython(seed_code_sequence, unseed),

        # ── Phase 1: people ─────────────────────────────────────────────────
        migrations.AddField(
            model_name='profile',
            name='designation',
            field=models.CharField(
                blank=True, max_length=200,
                help_text="Substantive post, e.g. 'Director, Finance'. Printed in signature stamps."),
        ),
        migrations.AddField(
            model_name='profile',
            name='office',
            field=models.CharField(
                blank=True, max_length=200,
                help_text="Directorate or unit, e.g. 'Power Directorate'."),
        ),
        migrations.AddField(
            model_name='signatory',
            name='user',
            field=auto_prefetch.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='signatory_roles', to=settings.AUTH_USER_MODEL,
                help_text='The login that signs as this signatory. Change it when someone acts '
                          'in the office — no deploy needed.'),
        ),

        # ── Phase 1: versioning, locking, urgency ───────────────────────────
        migrations.AddField(model_name='releaseletter', name='memo_version',
                            field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='releaseletter', name='letter_version',
                            field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='releaseletter', name='memo_locked',
                            field=models.BooleanField(default=False)),
        migrations.AddField(model_name='releaseletter', name='letter_locked',
                            field=models.BooleanField(default=False)),
        migrations.AddField(
            model_name='releaseletter', name='is_urgent',
            field=models.BooleanField(
                default=False, db_index=True,
                help_text='Management directive to fast-track. MMU may release before the signed scan.')),
        migrations.AddField(model_name='releaseletter', name='urgent_reason',
                            field=models.TextField(blank=True)),
        migrations.AddField(
            model_name='releaseletter', name='urgent_declared_by',
            field=auto_prefetch.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='urgent_releases', to=settings.AUTH_USER_MODEL)),
        migrations.AddField(model_name='releaseletter', name='urgent_declared_at',
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='documentdispatch', name='memo_version',
                            field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='documentdispatch', name='letter_version',
                            field=models.PositiveIntegerField(default=0)),

        # ── Phase 1: the chain ──────────────────────────────────────────────
        migrations.CreateModel(
            name='SigningStep',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_kind', models.CharField(
                    choices=[('memo', 'Approval memo'), ('letter', 'Release letter')],
                    db_index=True, max_length=10)),
                ('order', models.PositiveSmallIntegerField(
                    default=1,
                    help_text='Signing position, lowest first. Steps are enforced in order.')),
                ('required', models.BooleanField(
                    default=True,
                    help_text='A required step must be signed before the chain completes.')),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('signatory', auto_prefetch.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='signing_steps',
                    to='Inventory.signatory',
                    help_text='Whose name and title print on the signature line.')),
                ('user', auto_prefetch.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='signing_steps', to=settings.AUTH_USER_MODEL,
                    help_text='The login allowed to sign this step. Change this when someone acts '
                              'in the office. Leave blank for a print-only signatory who never '
                              'signs in the system.')),
            ],
            options={
                'verbose_name': 'signing step',
                'verbose_name_plural': 'signing steps',
                'ordering': ['document_kind', 'order'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
        ),
        migrations.AddConstraint(
            model_name='signingstep',
            constraint=models.UniqueConstraint(
                condition=models.Q(('active', True)),
                fields=('document_kind', 'order'),
                name='unique_active_step_order_per_document'),
        ),
        migrations.CreateModel(
            name='DocumentSignature',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_kind', models.CharField(
                    choices=[('memo', 'Approval memo'), ('letter', 'Release letter')],
                    db_index=True, max_length=10)),
                ('signatory_name', models.CharField(max_length=200)),
                ('signatory_title', models.CharField(
                    blank=True, max_length=200,
                    help_text="The office signed in, e.g. 'Ag. Chief Director'.")),
                ('signatory_designation', models.CharField(
                    blank=True, max_length=200,
                    help_text="Substantive post, e.g. 'Director, Finance'. Differs from the office "
                              "when someone is acting — the record must show both.")),
                ('signs_for', models.CharField(blank=True, max_length=200)),
                ('signature_image', models.ImageField(
                    blank=True, null=True, upload_to='signatures/%Y/%m/',
                    help_text='PNG of the signature drawn at signing time. Access-controlled.')),
                ('document_version', models.PositiveIntegerField(
                    default=1,
                    help_text='Document version signed, so a signature ties to exact content.')),
                ('verification_token', models.CharField(blank=True, db_index=True, max_length=20, unique=True)),
                ('signed_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=400)),
                ('superseded', models.BooleanField(
                    default=False, db_index=True,
                    help_text='Set when the document is reissued. The signature stays on record but '
                              'no longer applies to the current document.')),
                ('release_letter', auto_prefetch.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name='signatures',
                    to='Inventory.releaseletter')),
                ('signed_by', auto_prefetch.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='document_signatures', to=settings.AUTH_USER_MODEL)),
                ('step', auto_prefetch.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='signatures', to='Inventory.signingstep')),
            ],
            options={
                'verbose_name': 'document signature',
                'verbose_name_plural': 'document signatures',
                'ordering': ['document_kind', 'signed_at'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
        ),
    ]
