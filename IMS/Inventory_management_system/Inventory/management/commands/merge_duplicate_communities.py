"""Collapse case/whitespace-variant duplicate Community rows into one canonical row.

"KPIRI-FRAFRA NO. 3" and "Kpiri-Frafra No. 3" are the same place, but as
separate registry rows they split targets, progress and map sites in two. This
is the prerequisite for moving BoQ/ProjectSite onto a real Community foreign
key — an FK is only meaningful once there is exactly one row per community.

Merging keeps the richest row, folds the others into it (targets take the max,
blank coordinates/package numbers are filled in), repoints the only FK that
references Community (MeterInstallation), and then deactivates the leftovers
rather than deleting them, so history and any string matches still resolve.

    python manage.py merge_duplicate_communities --dry-run
    python manage.py merge_duplicate_communities
"""

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from Inventory.models import Community, MeterInstallation
from Inventory.services.community_progress import TARGET_FIELDS

FILL_IF_BLANK = ['package_number', 'latitude', 'longitude', 'gps_coordinates']


def _key(c):
    return (
        (c.region or '').strip().lower(),
        (c.district or '').strip().lower(),
        (c.community or '').strip().lower(),
    )


def _richness(c):
    """Prefer the row carrying the most target data; tie-break on lowest pk."""
    filled = sum(1 for f, _ in TARGET_FIELDS if (getattr(c, f, 0) or 0) > 0)
    return (-filled, c.pk)


class Command(BaseCommand):
    help = ("Merge Community rows that differ only by case/whitespace into a "
            "single canonical row.")

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would merge and change nothing.')

    def handle(self, *args, **opts):
        groups = defaultdict(list)
        for c in Community.objects.filter(is_active=True):
            groups[_key(c)].append(c)
        dupes = {k: v for k, v in groups.items() if len(v) > 1}

        if not dupes:
            self.stdout.write(self.style.SUCCESS(
                'No duplicate communities — registry is already canonical.'))
            return

        total_extra = sum(len(v) - 1 for v in dupes.values())
        self.stdout.write(
            f"{len(dupes)} communities have duplicates ({total_extra} extra rows).")

        if opts['dry_run']:
            for rows in list(dupes.values())[:20]:
                rows = sorted(rows, key=_richness)
                keep, drop = rows[0], rows[1:]
                self.stdout.write(
                    f"  keep #{keep.pk} '{keep.community}' ({keep.district}, {keep.region})"
                    f"  ← merge {', '.join('#%d %r' % (d.pk, d.community) for d in drop)}")
            if len(dupes) > 20:
                self.stdout.write(f"  … and {len(dupes) - 20} more")
            self.stdout.write(self.style.WARNING('Dry run — nothing written.'))
            return

        merged = moved = 0
        with transaction.atomic():
            for rows in dupes.values():
                rows = sorted(rows, key=_richness)
                keep, drop = rows[0], rows[1:]

                for d in drop:
                    # Targets: keep the larger of the two (a zero means "never
                    # pulled", not "genuinely zero").
                    for field, _ in TARGET_FIELDS:
                        theirs = getattr(d, field, 0) or 0
                        if theirs > (getattr(keep, field, 0) or 0):
                            setattr(keep, field, theirs)
                    # Fill blanks on the canonical row from the duplicate.
                    for field in FILL_IF_BLANK:
                        if not getattr(keep, field, None) and getattr(d, field, None):
                            setattr(keep, field, getattr(d, field))
                    # Repoint the only FK that references Community.
                    moved += MeterInstallation.objects.filter(
                        community=d).update(community=keep)
                    d.is_active = False
                    d.save(update_fields=['is_active'])
                    merged += 1

                keep.save()

        self.stdout.write(self.style.SUCCESS(
            f"Merged {merged} duplicate rows into {len(dupes)} canonical communities; "
            f"repointed {moved} meter installations. Duplicates deactivated, not deleted."))
