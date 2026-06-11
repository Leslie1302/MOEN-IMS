"""One-time cleanup: repair BillOfQuantity rows where blank Excel cells were
imported as the literal string 'nan' (pre-_cell() importer bug).

Usage: python manage.py fix_nan_boq [--dry-run]
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from Inventory.models import BillOfQuantity


BAD = ('nan', 'none', 'nat')


class Command(BaseCommand):
    help = "Replace literal 'nan' strings in BOQ text fields with blank/NULL."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report counts without modifying anything.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        fixes = [
            ('community', None),
            ('district', ''),
            ('region', ''),
            ('consultant', ''),
            ('contractor', ''),
            ('phase', None),
        ]
        total = 0
        for field, replacement in fixes:
            q = Q()
            for bad in BAD:
                q |= Q(**{f'{field}__iexact': bad})
            qs = BillOfQuantity.objects.filter(q)
            n = qs.count()
            total += n
            if n and not dry:
                qs.update(**{field: replacement})
            self.stdout.write(f"{field}: {n} row(s) {'found' if dry else 'fixed'}")
        self.stdout.write(self.style.SUCCESS(
            f"{'Would fix' if dry else 'Fixed'} {total} field value(s)."))
