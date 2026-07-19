"""Register BoQ communities that are missing from the Community registry.

The registry is the spine: the community progress page lists Community rows,
BoQ targets are stored *on* Community, and the Ghana map builds a ProjectSite
per Community. So a BoQ community with no registry row is invisible three
ways at once — no map site, nowhere to write targets, no progress row.

This creates the missing rows using the exact BoQ spelling (so the
region/district/community match the BoQ joins use), then pulls each one's
targets from the BoQ. Creating a Community fires the map_sync signal, which
creates its ProjectSite automatically.

    python manage.py register_boq_communities --dry-run
    python manage.py register_boq_communities
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from Inventory.models import Community, ProjectType
from Inventory.services.map_sync import boq_communities_without_registry
from Inventory.services.community_progress import pull_targets_from_boq


class Command(BaseCommand):
    help = ("Create Community rows for BoQ communities missing from the "
            "registry, then pull their BoQ targets.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List what would be created and change nothing.')
        parser.add_argument(
            '--project-type', default='shep',
            help="ProjectType code to assign (default: shep).")
        parser.add_argument(
            '--no-targets', action='store_true',
            help='Only register the communities; skip the BoQ target pull.')

    def handle(self, *args, **opts):
        missing = boq_communities_without_registry()
        if not missing:
            self.stdout.write(self.style.SUCCESS(
                'Registry is already complete — no BoQ communities missing.'))
            return

        self.stdout.write(f"{len(missing)} BoQ communities missing from the registry.")

        if opts['dry_run']:
            for m in missing[:20]:
                self.stdout.write(
                    f"  would create: {m['community']} ({m['district']}, {m['region']})")
            if len(missing) > 20:
                self.stdout.write(f"  … and {len(missing) - 20} more")
            self.stdout.write(self.style.WARNING('Dry run — nothing written.'))
            return

        ptype = ProjectType.objects.filter(code=opts['project_type']).first()
        if ptype is None:
            self.stderr.write(self.style.ERROR(
                f"No ProjectType with code '{opts['project_type']}'. "
                f"Available: {', '.join(ProjectType.objects.values_list('code', flat=True)) or 'none'}"))
            return

        created = targeted = 0
        with transaction.atomic():
            for m in missing:
                # Case-insensitive lookup first: "KPIRI-FRAFRA NO. 3" and
                # "Kpiri-Frafra No. 3" are the same community, so we must not
                # create a second row that differs only by case.
                community = Community.objects.filter(
                    region__iexact=m['region'] or '',
                    district__iexact=m['district'] or '',
                    community__iexact=m['community'],
                ).first()
                if community is None:
                    community = Community.objects.create(
                        region=m['region'] or '',
                        district=m['district'] or '',
                        community=m['community'],
                        project_type=ptype,
                        is_active=True,
                    )
                    created += 1
                if not opts['no_targets']:
                    # Writes planned_ht_poles / planned_connections / … from
                    # the community's BoQ lines. Skips locked communities.
                    pull_targets_from_boq(community, apply=True)
                    targeted += 1

        self.stdout.write(self.style.SUCCESS(
            f"Registered {created} communities"
            + ('' if opts['no_targets'] else f"; pulled BoQ targets for {targeted}")
            + ". Their map sites are created automatically by the community signal."
        ))
