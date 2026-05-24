"""
Refresh canonical user groups so production picks up the new role layout
without anyone running a management command.

What this migration does on apply:
  - Ensures the canonical group set exists (Schedule Officers, Store
    Officers, Stores Management, Transport Officers, Transporters,
    Consultants, Management).
  - Resets each group's permission list to the spec in
    `Inventory/management/commands/setup_groups.py` so role drift caused
    by hand-editing in admin gets corrected.
  - Renames any pre-existing legacy / typo'd group names into the
    canonical names (e.g. singular "Transporter" -> "Transporters"),
    preserving the membership of those legacy groups.
  - Deletes empty legacy duplicate groups.

Reverse is a no-op (groups aren't dropped on rollback — they're soft
infrastructure).
"""

from django.db import migrations


# Legacy / typo'd group names mapped to their canonical replacement.
# If both names exist in production, members of the legacy group are
# moved over and the legacy group is deleted.
LEGACY_GROUP_RENAMES = {
    'Schedule Officer': 'Schedule Officers',
    'Store Officer': 'Store Officers',
    'Transport Officer': 'Transport Officers',
    'Transporter': 'Transporters',
    'Consultant': 'Consultants',
}

# Canonical group permission spec — keeps this migration in lockstep with
# setup_groups.py without having to import the management command.
GROUP_SPEC = [
    ('Schedule Officers', [
        'add_materialorder', 'change_materialorder', 'view_materialorder',
        'view_materialtransport', 'view_sitereceipt',
    ]),
    ('Store Officers', [
        'add_materialorder', 'change_materialorder', 'view_materialorder',
        'add_materialtransport', 'change_materialtransport', 'view_materialtransport',
        'add_releaseletter', 'change_releaseletter', 'view_releaseletter',
        'add_sitereceipt', 'change_sitereceipt', 'view_sitereceipt',
    ]),
    ('Stores Management', [
        'add_materialorder', 'change_materialorder', 'view_materialorder',
        'add_materialtransport', 'change_materialtransport', 'view_materialtransport',
        'add_releaseletter', 'change_releaseletter', 'view_releaseletter',
        'add_sitereceipt', 'change_sitereceipt', 'view_sitereceipt',
        'view_billofquantity',
    ]),
    ('Transport Officers', [
        'view_materialorder',
        'add_materialtransport', 'change_materialtransport', 'view_materialtransport',
        'view_releaseletter', 'view_sitereceipt',
    ]),
    ('Transporters', [
        'view_materialorder', 'view_materialtransport',
        'add_sitereceipt', 'change_sitereceipt', 'view_sitereceipt',
    ]),
    ('Consultants', [
        'view_materialorder', 'view_materialtransport',
        'add_sitereceipt', 'change_sitereceipt', 'view_sitereceipt',
    ]),
    ('Management', [
        'view_materialorder', 'view_materialtransport',
        'view_releaseletter', 'view_sitereceipt',
        'view_billofquantity', 'add_billofquantity', 'change_billofquantity',
    ]),
]

# Models the permission codenames above belong to (model_label -> permission prefix).
PERMISSION_MODEL_HINTS = {
    'billofquantity': 'BillOfQuantity',
    'materialorder': 'MaterialOrder',
    'materialtransport': 'MaterialTransport',
    'releaseletter': 'ReleaseLetter',
    'sitereceipt': 'SiteReceipt',
}


def _resolve_permissions(apps, codenames):
    Permission = apps.get_model('auth', 'Permission')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    resolved = []
    for codename in codenames:
        # codename looks like "view_materialorder" — strip the action prefix.
        for hint, model_name in PERMISSION_MODEL_HINTS.items():
            if hint in codename:
                model = apps.get_model('Inventory', model_name)
                ct = ContentType.objects.get_for_model(model)
                try:
                    resolved.append(Permission.objects.get(content_type=ct, codename=codename))
                except Permission.DoesNotExist:
                    pass
                break
    return resolved


def refresh_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')

    # 1. Rename legacy groups into canonical names. Preserve members.
    for legacy, canonical in LEGACY_GROUP_RENAMES.items():
        try:
            legacy_g = Group.objects.get(name=legacy)
        except Group.DoesNotExist:
            continue
        canonical_g, _ = Group.objects.get_or_create(name=canonical)
        # Move members.
        for user in legacy_g.user_set.all():
            user.groups.add(canonical_g)
            user.groups.remove(legacy_g)
        # Drop the now-empty legacy group.
        legacy_g.delete()

    # 2. Ensure canonical groups exist with the right permissions.
    for name, codenames in GROUP_SPEC:
        group, _ = Group.objects.get_or_create(name=name)
        perms = _resolve_permissions(apps, codenames)
        group.permissions.set(perms)


def noop_reverse(apps, schema_editor):
    """Groups are soft infrastructure — don't drop them on rollback."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0042_transporter_consultant_user_link'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(refresh_groups, noop_reverse),
    ]
