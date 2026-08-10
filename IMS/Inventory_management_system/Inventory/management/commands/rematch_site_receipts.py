"""Retry the BoQ match for site receipts that never posted.

Receipts logged before their Bill of Quantity line existed are stranded: the
match is resolved once, at creation, so uploading the BoQ afterwards does not go
back and draw down the contract. They sit in the over-issuance summary as
off-BoQ deliveries indefinitely.

Run after any BoQ upload that backfills lines for deliveries already recorded:

    python manage.py rematch_site_receipts --dry-run     # preview, writes nothing
    python manage.py rematch_site_receipts               # apply

Idempotent — a receipt that posts is flagged, so it can never post twice.
"""

from django.core.management.base import BaseCommand

from Inventory.services.boq_rematch import rematch_unposted_receipts


class Command(BaseCommand):
    help = "Retry the Bill of Quantity match for site receipts that never posted."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Report what would post without writing anything.")
        parser.add_argument(
            '--limit', type=int, default=None,
            help="Only process the first N unmatched receipts (oldest first).")
        parser.add_argument(
            '--verbose', action='store_true',
            help="List every receipt and its outcome.")

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        result = rematch_unposted_receipts(
            dry_run=dry_run, limit=options['limit'])

        if dry_run:
            self.stdout.write(self.style.WARNING(
                "DRY RUN — nothing was written."))

        if options['verbose']:
            for detail in result.details:
                style = {
                    'posted': self.style.SUCCESS,
                    'unmatched': self.style.WARNING,
                    'error': self.style.ERROR,
                }.get(detail['outcome'], self.style.NOTICE)
                self.stdout.write(style(
                    f"  receipt {detail['id']}: {detail['outcome']} — {detail['note']}"))

        self.stdout.write(self.style.SUCCESS(result.summary()))

        if result.still_unmatched:
            self.stdout.write(
                "Receipts still without a BoQ line are genuine off-BoQ deliveries, "
                "or the BoQ line does not match on item code, package or community. "
                "Re-run after correcting the BoQ.")
