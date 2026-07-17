# Phase 6 decision 1: drop 'Pending' and 'Ready for Pickup' from
# MaterialOrder.STATUS_CHOICES — unreachable states nothing ever set.
# Choices-only change; stored rows are untouched.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('Inventory', '0068_merge_role_group_aliases'),
    ]
    operations = [
        migrations.AlterField(
            model_name='materialorder',
            name='status',
            field=models.CharField(
                choices=[
                    ('Draft', 'Draft'), ('Seen', 'Seen'),
                    ('Approved', 'Approved'), ('In Progress', 'In Progress'),
                    ('Partially Fulfilled', 'Partially Fulfilled'),
                    ('In Transit', 'In Transit'), ('Delivered', 'Delivered'),
                    ('Completed', 'Completed'), ('Rejected', 'Rejected'),
                    ('Cancelled', 'Cancelled'),
                ],
                db_index=True, default='Draft', max_length=20,
            ),
        ),
    ]
