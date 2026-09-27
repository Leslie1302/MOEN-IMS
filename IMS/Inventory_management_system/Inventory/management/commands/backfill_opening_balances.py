"""Give every stock item that has no ledger rows an opening-balance line.

A tally card should never open blank: each item should start with an 'opening'
movement equal to its current stock. The go-live data migration seeds this, and
the bulk upload / add-item flows record it going forward — but an item created
by some other path (or on an environment where the seed migration did not run)
can end up with an empty card, which also shows on the integrity report as
'no ledger'. This command fills those gaps.

Idempotent: only items with zero movements are touched, so re-running is safe.
Use --dry-run to preview.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Create an opening-balance stock movement for any item that has none."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Report what would change without writing.")

    def handle(self, *args, **options):
        from Inventory.models import InventoryItem, StockMovement

        dry = options['dry_run']
        with_history = set(
            StockMovement.objects.values_list('item_id', flat=True).distinct())
        missing = [i for i in InventoryItem.objects.all().iterator()
                   if i.id not in with_history]

        if not missing:
            self.stdout.write(self.style.SUCCESS(
                "Every item already has at least one ledger row. Nothing to do."))
            return

        self.stdout.write(f"{len(missing)} item(s) have no ledger rows:")
        for i in missing:
            wh = i.warehouse.name if i.warehouse else '—'
            self.stdout.write(f"  {i.code or i.pk} @ {wh}: opening balance {i.quantity or 0}")

        if dry:
            self.stdout.write(self.style.WARNING("Dry run — no rows written."))
            return

        now = timezone.now()
        rows = [StockMovement(
            item_id=i.id, movement_type='opening',
            qty_in=(i.quantity or 0), qty_out=0, balance_after=(i.quantity or 0),
            reference='Opening balance', note='Opening balance (backfill).',
            created_at=now) for i in missing]
        StockMovement.objects.bulk_create(rows, batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"Wrote {len(rows)} opening-balance row(s)."))
