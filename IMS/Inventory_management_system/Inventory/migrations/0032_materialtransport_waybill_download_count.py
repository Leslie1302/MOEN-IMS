# Reconciles Django's migration state with the schema for
# MaterialTransport.waybill_download_count.
#
# Backstory: the column was deleted from the model (and migration state) in
# 0028, then re-added physically via raw SQL in 0030 -- but never re-added
# to Django's migration state. That left every future `makemigrations` run
# proposing to "add" the column, even though it exists in the database.
#
# This migration syncs the state without altering the schema. Important:
# we do NOT use a plain AddField, because on production the column is
# already physically present and AddField would fail with
# "duplicate column name: waybill_download_count". SeparateDatabaseAndState
# with empty database_operations makes the migration a state-only sync.
#
# On a fresh dev database, 0030's RunPython already creates the column
# before this migration runs, so the schema is in sync there too.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0031_create_canonical_groups'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='materialtransport',
                    name='waybill_download_count',
                    field=models.IntegerField(
                        default=0,
                        help_text='Number of times this waybill has been downloaded',
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
