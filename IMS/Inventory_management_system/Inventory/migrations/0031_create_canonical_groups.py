# Data migration: recreate the canonical auth Groups that were lost when the
# production SQLite file got wiped. Idempotent -- safe to re-run on every deploy.
#
# Group names match the *plural* forms used by Inventory/signals.py,
# Notification.recipient_group choices, and the various view-level
# group-name gates. Navigation templates already accept these via
# OR-aliases, so visibility "just works" once a user is assigned.
#
# This migration intentionally only creates the Group rows. Membership
# (which user belongs to which group) is left to Django admin so it stays
# the responsibility of an actual administrator. Permissions are also
# left untouched here -- the existing `setup_groups` management command
# handles that (note that it uses singular names; can be aligned later).

from django.db import migrations
import logging

logger = logging.getLogger(__name__)

# Canonical group names. Order is just for log readability.
CANONICAL_GROUPS = [
    "Store Officers",
    "Stores Management",
    "Schedule Officers",
    "Management",
    "Consultants",
]


def create_canonical_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    created, existed = [], []
    for name in CANONICAL_GROUPS:
        _, was_created = Group.objects.get_or_create(name=name)
        (created if was_created else existed).append(name)
    if created:
        logger.info("Created auth groups: %s", ", ".join(created))
    if existed:
        logger.info("Auth groups already present: %s", ", ".join(existed))
    # Keep stdout output too -- Azure log stream surfaces print() reliably.
    print(f"[0031_create_canonical_groups] created={created} existed={existed}")


def remove_canonical_groups(apps, schema_editor):
    """
    Reverse op deletes only groups we created here AND only if they have no
    members. This avoids accidentally wiping live group memberships during a
    migration rollback.
    """
    Group = apps.get_model("auth", "Group")
    for name in CANONICAL_GROUPS:
        try:
            group = Group.objects.get(name=name)
        except Group.DoesNotExist:
            continue
        if group.user_set.exists():
            logger.warning(
                "Refusing to delete group %r during reverse migration: it has %d members.",
                name, group.user_set.count(),
            )
            continue
        group.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("Inventory", "0030_fix_waybill_download_count_column"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(
            create_canonical_groups,
            reverse_code=remove_canonical_groups,
        ),
    ]
