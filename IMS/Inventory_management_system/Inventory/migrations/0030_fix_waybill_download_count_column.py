from django.db import migrations


def add_waybill_download_count_column(apps, schema_editor):
    connection = schema_editor.connection
    table_name = "Inventory_materialtransport"

    with connection.cursor() as cursor:
        # Backend-agnostic column check (the original used SQLite-only PRAGMA,
        # which crashes on PostgreSQL). On a fresh database the column already
        # exists via the model's earlier migrations, so this becomes a no-op.
        existing_columns = {
            col.name
            for col in connection.introspection.get_table_description(cursor, table_name)
        }

        if "waybill_download_count" not in existing_columns:
            cursor.execute(
                f'ALTER TABLE "{table_name}" '
                'ADD COLUMN "waybill_download_count" integer NOT NULL DEFAULT 0'
            )


class Migration(migrations.Migration):

    dependencies = [
        ("Inventory", "0029_alter_billofquantity_community_and_more"),
    ]

    operations = [
        migrations.RunPython(add_waybill_download_count_column, migrations.RunPython.noop),
    ]
