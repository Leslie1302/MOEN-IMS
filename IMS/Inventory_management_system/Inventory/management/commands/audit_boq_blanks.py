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

        # Contracts are per-package: package_number and region are what matter
        # (reconciliation key + map). community is optional, reported for info.
        counts = {
            f: BillOfQuantity.objects.filter(blank(f)).count()
            for f in ('package_number', 'region', 'district', 'community')
        }
        any_blank = BillOfQuantity.objects.filter(
            blank('package_number') | blank('region')).count()

        distinct_regions = (BillOfQuantity.objects
                            .exclude(blank('region'))
                            .values_list('region', flat=True).distinct().count())

        self.stdout.write(f"Total BoQ rows: {total:,}")
        self.stdout.write(f"  blank package_number: {counts['package_number']:,} "
                          f"({counts['package_number'] / total:.0%})   <- can't reconcile")
        self.stdout.write(f"  blank region:         {counts['region']:,} "
                          f"({counts['region'] / total:.0%})   <- won't map / filter")
        self.stdout.write(f"  blank district:       {counts['district']:,} "
                          f"({counts['district'] / total:.0%})")
        self.stdout.write(f"  blank community:      {counts['community']:,} "
                          f"({counts['community'] / total:.0%})   (optional — package-level, informational)")
        self.stdout.write(f"  rows missing package_number or region: {any_blank:,}")
        self.stdout.write(f"  distinct non-blank regions (what the filter can show): "
                          f"{distinct_regions}")

        if any_blank:
            self.stdout.write("\nSample of rows missing package_number or region:")
            fields = ('id', 'package_number', 'item_code', 'region', 'district', 'community')
            for r in (BillOfQuantity.objects
                      .filter(blank('package_number') | blank('region'))
                      .values(*fields)[:opts['sample']]):
                self.stdout.write(
                    f"  #{r['id']}  pkg={r['package_number'] or '—'}  "
                    f"item={r['item_code'] or '—'}  "
                    f"region={r['region'] or '∅'}  district={r['district'] or '∅'}  "
                    f"community={r['community'] or '∅'}")
            self.stdout.write(self.style.WARNING(
                "\nMissing package_number blocks package reconciliation; missing "
                "region hides the row from the map/filters. Re-upload with those "
                "filled, or fix in BoQ bulk-edit. (community may stay blank.)"))
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nEvery BoQ row has a package_number and region — reconciliation-ready."))
