from django.db import migrations


def add_waybill_download_count_column(apps, schema_editor):
    connection = schema_editor.connection
    table_name = "Inventory_materialtransport"

    with connection.cursor() as cursor:
        existing_columns = {
            row[1] for row in cursor.execute(f'PRAGMA table_info("{table_name}")').fetchall()
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
