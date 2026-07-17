# Phase 5: merge legacy role-group aliases into the canonical groups.
#
# 'Store Officer' / 'Storekeeper(s)' / 'Stores Officer(s)' members move into
# 'Store Officers'; 'Consultant' members move into 'Consultants'. Kills the
# trap where a user could be assignable (singular-group check) but unable to
# see their queue (plural-group check).
from django.db import migrations

CANONICAL = {
    'Store Officers': [
        'Store Officer', 'Storekeeper', 'Storekeepers',
        'Stores Officer', 'Stores Officers',
    ],
    'Consultants': ['Consultant'],
}


def merge_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    for canonical_name, aliases in CANONICAL.items():
        canonical, _ = Group.objects.get_or_create(name=canonical_name)
        for alias in aliases:
            legacy = Group.objects.filter(name=alias).first()
            if legacy is None:
                continue
            for user in legacy.user_set.all():
                user.groups.add(canonical)
            legacy.delete()


class Migration(migrations.Migration):
    dependencies = [
        ('Inventory', '0067_alter_district_unique_together'),
    ]
    operations = [
        migrations.RunPython(merge_groups, migrations.RunPython.noop),
    ]
