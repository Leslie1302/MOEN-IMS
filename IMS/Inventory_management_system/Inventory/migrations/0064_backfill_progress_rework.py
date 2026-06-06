"""
Data backfill for the community-progress rework.

1. BillOfQuantity.voltage_class — classify existing rows with the same
   heuristic the community breakdown used (transformer/meter/HT/LV), so the
   new explicit field starts populated. Truly ambiguous rows are left blank
   for manual review rather than guessed.

2. ProjectSite pole lifecycle — the legacy combined ``poles_erected`` /
   ``conductor_laid_m`` are folded into the LV lifecycle (the common SHEP
   reticulation case): erected count -> lv_poles_erected, conductor metres
   -> lv_conductor_strung_m. Dressed/strung stay 0 (unknown historically).

Both steps are idempotent: they only write where the new field is still at
its default, so re-running causes no double-application.
"""

from django.db import migrations
from decimal import Decimal


def _classify(description):
    """Mirror of _categorise_boq_material + meter detection. Returns a
    voltage_class value or '' when it cannot be determined confidently."""
    if not description:
        return ''
    d = description.lower()
    if 'transformer' in d or 'xfmr' in d:
        return 'XFMR'
    if 'meter' in d:
        return 'METER'
    is_pole = 'pole' in d
    is_ht = any(k in d for k in ('h.t', 'ht ', 'high tension', 'high voltage',
                                 'hv ', '11kv', '33kv', 'primary'))
    is_lv = any(k in d for k in ('l.v', 'lv ', 'low tension', 'low voltage',
                                 'secondary', '415v', '400v', '0.4kv'))
    if is_ht and not is_lv:
        return 'HT'
    if is_lv and not is_ht:
        return 'LV'
    if is_pole:
        # Generic/ambiguous pole defaults to LV reticulation, as the
        # heuristic always has.
        return 'LV'
    return ''


def forwards(apps, schema_editor):
    BillOfQuantity = apps.get_model('Inventory', 'BillOfQuantity')
    ProjectSite = apps.get_model('Inventory', 'ProjectSite')

    for boq in BillOfQuantity.objects.filter(voltage_class=''):
        vc = _classify(boq.material_description)
        if vc:
            boq.voltage_class = vc
            boq.save(update_fields=['voltage_class'])

    for site in ProjectSite.objects.all():
        changed = []
        if (site.poles_erected or 0) and not (site.lv_poles_erected or 0):
            site.lv_poles_erected = site.poles_erected
            changed.append('lv_poles_erected')
        if (site.conductor_laid_m or 0) and not (site.lv_conductor_strung_m or 0):
            site.lv_conductor_strung_m = Decimal(str(site.conductor_laid_m))
            changed.append('lv_conductor_strung_m')
        if changed:
            site.save(update_fields=changed)


def backwards(apps, schema_editor):
    # Non-destructive: clearing the backfilled values is unnecessary and the
    # legacy columns are untouched, so reverse is a no-op.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0063_billofquantity_voltage_class_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
