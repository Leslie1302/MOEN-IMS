"""Report BoQ rows with blank region / district / community.

These are the rows that break the BoQ filters (no value to filter on),
strand communities off the map, and can't be reconciled. Read-only — it
counts and samples, it changes nothing.

    python manage.py audit_boq_blanks
    python manage.py audit_boq_blanks --sample 30
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from Inventory.models import BillOfQuantity

BLANK = Q(region__isnull=True) | Q(region__exact="")


class Command(BaseCommand):
    help = "Count and sample BoQ rows missing region / district / community."

    def add_arguments(self, parser):
        parser.add_argument('--sample', type=int, default=15,
                            help='How many example rows to print (default 15).')

    def handle(self, *args, **opts):
        total = BillOfQuantity.objects.count()
        if not total:
            self.stdout.write(self.style.WARNING('BoQ table is empty.'))
            return

        def blank(field):
            return Q(**{f"{field}__isnull": True}) | Q(**{f"{field}__exact": ""})

        counts = {
            f: BillOfQuantity.objects.filter(blank(f)).count()
            for f in ('region', 'district', 'community')
        }
        any_blank = BillOfQuantity.objects.filter(
            blank('region') | blank('district') | blank('community')).count()

        distinct_regions = (BillOfQuantity.objects
                            .exclude(blank('region'))
                            .values_list('region', flat=True).distinct().count())

        self.stdout.write(f"Total BoQ rows: {total:,}")
        self.stdout.write(f"  blank region:    {counts['region']:,} "
                          f"({counts['region'] / total:.0%})")
        self.stdout.write(f"  blank district:  {counts['district']:,} "
                          f"({counts['district'] / total:.0%})")
        self.stdout.write(f"  blank community: {counts['community']:,} "
                          f"({counts['community'] / total:.0%})")
        self.stdout.write(f"  rows missing at least one: {any_blank:,}")
        self.stdout.write(f"  distinct non-blank regions (what the filter can show): "
                          f"{distinct_regions}")

        if any_blank:
            self.stdout.write("\nSample of incomplete rows:")
            fields = ('id', 'package_number', 'item_code', 'region', 'district', 'community')
            for r in (BillOfQuantity.objects
                      .filter(blank('region') | blank('district') | blank('community'))
                      .values(*fields)[:opts['sample']]):
                self.stdout.write(
                    f"  #{r['id']}  pkg={r['package_number'] or '—'}  "
                    f"item={r['item_code'] or '—'}  "
                    f"region={r['region'] or '∅'}  district={r['district'] or '∅'}  "
                    f"community={r['community'] or '∅'}")
            self.stdout.write(self.style.WARNING(
                "\nThese rows won't appear under region/community filters and can't "
                "reconcile. Re-upload them with the missing columns filled, or fix "
                "in BoQ bulk-edit."))
        else:
            self.stdout.write(self.style.SUCCESS("\nNo incomplete BoQ rows — data is clean."))
