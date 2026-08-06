# Unguessable per-document token carried in the QR link.
#
# Release codes are sequential (RE-2026-0001, 0002, ...) and therefore
# enumerable, so verifying by code alone proves only that a reference exists.
# A forger could enumerate to find a real, approved code and print it on a fake
# release letter — and the verify page would answer "issued by MOEN-IMS",
# because the code genuinely was. Possession of this token proves possession of
# the actual document, which is what verification is meant to establish.
#
# Backfilled for existing rows so documents already in circulation can be
# re-minted with a working QR; their old bare-code QR keeps resolving to the
# reduced, code-only answer.

import secrets

from django.db import migrations, models


def mint_tokens(apps, schema_editor):
    ReleaseLetter = apps.get_model('Inventory', 'ReleaseLetter')
    seen = set()
    to_update = []
    for letter in ReleaseLetter.objects.filter(verify_token='').only('id'):
        while True:
            token = secrets.token_urlsafe(12)[:16]
            if token not in seen:
                seen.add(token)
                break
        letter.verify_token = token
        to_update.append(letter)
    if to_update:
        ReleaseLetter.objects.bulk_update(to_update, ['verify_token'], batch_size=500)


def clear_tokens(apps, schema_editor):
    apps.get_model('Inventory', 'ReleaseLetter').objects.update(verify_token='')


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0082_signing_and_code_sequence'),
    ]

    operations = [
        migrations.AddField(
            model_name='releaseletter',
            name='verify_token',
            field=models.CharField(blank=True, db_index=True, max_length=32),
        ),
        migrations.RunPython(mint_tokens, clear_tokens),
    ]
