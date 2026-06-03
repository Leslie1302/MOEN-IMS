"""
Backfill ProjectSite.status from BoQ completion.

Run once after the BoQ→Ghana-map signal lands so existing communities
flip to the right status without waiting for every BoQ row to be re-saved:

    python manage.py sync_sites_from_boq
    python manage.py sync_sites_from_boq --dry-run
"""

from collections import defaultdict
from django.core.management.base import BaseCommand
from django.utils import timezone

from Inventory.models import BillOfQuantity
from Inventory.models.projects import ProjectSite


class Command(BaseCommand):
    help = "Recompute ProjectSite.status from current BoQ completion per community."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Show what would change without writing.',
        )

    def _bucket(self, lines):
        """Return ('Completed' / 'Active' / 'Planned') for a community's lines."""
        if not lines:
            return None
        all_done = all(
            (l['received'] or 0) >= (l['contract'] or 0) > 0 for l in lines
        )
        if all_done:
            return 'Completed'
        any_progress = any((l['received'] or 0) > 0 for l in lines)
        return 'Active' if any_progress else 'Planned'

    def handle(self, *args, **opts):
        dry = opts['dry_run']

        # Group BoQ lines by (community lower, project_type) → list.
        groups = defaultdict(list)
        for row in BillOfQuantity.objects.values(
            'community', 'project_type', 'contract_quantity', 'quantity_received'
        ):
            community = (row['community'] or '').strip().lower()
            if not community:
                continue
            groups[(community, row['project_type'] or '')].append({
                'contract': row['contract_quantity'],
                'received': row['quantity_received'],
            })

        flipped = 0
        skipped_hold = 0
        unchanged = 0
        for (community_lower, project_type), lines in groups.items():
            new_status = self._bucket(lines)
            if not new_status:
                continue
            site_qs = ProjectSite.objects.filter(community__iexact=community_lower)
            if project_type:
                type_filtered = site_qs.filter(project__project_type=project_type)
                if type_filtered.exists():
                    site_qs = type_filtered
            for site in site_qs:
                if site.status == 'On Hold':
                    skipped_hold += 1
                    continue
                if site.status == new_status:
                    unchanged += 1
                    continue
                self.stdout.write(
                    f"  {site.community} ({project_type or '-'}): "
                    f"{site.status} → {new_status}"
                )
                flipped += 1
                if dry:
                    continue
                site.status = new_status
                if new_status == 'Completed' and not site.actual_completion_date:
                    site.actual_completion_date = timezone.now().date()
                site.save(update_fields=['status', 'actual_completion_date', 'updated_at'])

        verb = 'Would flip' if dry else 'Flipped'
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {flipped} ProjectSite rows. "
            f"{unchanged} already in sync, {skipped_hold} on hold (skipped)."
        ))
