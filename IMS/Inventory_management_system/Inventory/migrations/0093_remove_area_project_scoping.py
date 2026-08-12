# Revert the area+project scoping feature at the DB level: drop the project_type
# columns 0077 added to Profile and ProjectConsultant. The models no longer
# declare these fields, so this leaves models, migrations, and the database
# consistent. Depends on the 0092 merge (the current graph head).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0092_merge_20260811_2201'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='profile',
            name='project_type',
        ),
        migrations.RemoveField(
            model_name='projectconsultant',
            name='project_type',
        ),
    ]
