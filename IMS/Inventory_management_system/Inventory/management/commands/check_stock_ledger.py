"""Flag any tally card whose ledger balance has drifted from live stock.

Run manually or on a schedule (cron). Exit code 1 when drift is found, so it
can gate an alert:  `python manage.py check_stock_ledger || notify ...`
"""
from django.core.management.base import BaseCommand

from Inventory.services.stock_ledger import find_drift


class Command(BaseCommand):
    help = "Report InventoryItems whose stock ledger balance != live quantity."

    def handle(self, *args, **options):
        drift = find_drift()
        if not drift:
            self.stdout.write(self.style.SUCCESS(
                "Stock ledger is consistent — every card's balance matches live stock."))
            return
        self.stdout.write(self.style.ERROR(f"{len(drift)} card(s) drifted:"))
        for item, live, ledger in drift:
            wh = item.warehouse.name if item.warehouse else '—'
            if ledger is None:
                self.stdout.write(f"  {item.code or item.pk} @ {wh}: no ledger rows (live={live})")
            else:
                self.stdout.write(
                    f"  {item.code or item.pk} @ {wh}: live={live} ledger={ledger} "
                    f"gap={(live or 0) - ledger}")
        # Non-zero exit for cron alerting.
        import sys
        sys.exit(1)
