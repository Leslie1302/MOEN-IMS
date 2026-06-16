"""
Seed ProjectSite rows (and Community works targets) from the Kobo field
progress export.

BoQ carries no community and the system had no way to create ProjectSites,
so Site Progress and the works% on Community Progress were empty. This
command reads a compact CSV extracted from Kobo_Progress.xlsx (committed at
``commands/data/kobo_site_progress.csv``) and, per community:

  * upserts a ProjectSite under an umbrella Project, filling the works
    fields (HT/LV poles erected/dressed/strung, transformers installed/
    commissioned, single/three-phase connections);
  * sets the Community's planned_* targets from the Kobo contract
    quantities (the denominators the 5-stage % needs), skipping any
    community whose targets are locked, and never zeroing an existing
    target when Kobo has no figure;
  * recomputes progress_percent and works_status.

Idempotent — safe to re-run. Match key is (project, region, district,
community), case-insensitive.

    python manage.py seed_sites_from_kobo --dry-run
    python manage.py seed_sites_from_kobo
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from Inventory.models import Community
from Inventory.models.projects import Project, ProjectSite

DATA_FILE = Path(__file__).resolve().parent / 'data' / 'kobo_site_progress.csv'

UMBRELLA = {
    'code': 'SHEP-4',
    'name': 'SHEP Phase 4',
    'phase': 'SHEP-4',
    'project_type': 'SHEP',
    'description': 'Self-Help Electrification Programme — Phase 4 (seeded from field progress).',
    'status': 'Active',
}


def _i(row, key):
    try:
        return max(0, int(round(float(row.get(key) or 0))))
    except (ValueError, TypeError):
        return 0


def _works_status(percent, connections):
    if percent >= 100:
        return 'Commissioned'
    if connections > 0:
        return 'Energised'
    if percent > 0:
        return 'In Progress'
    return 'Planned'


class Command(BaseCommand):
    help = "Seed ProjectSites and Community targets from the Kobo field-progress CSV."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Report what would change without writing.')
        parser.add_argument('--no-targets', action='store_true',
                            help='Do not touch Community planned_* targets.')

    def handle(self, *args, **opts):
        dry = opts['dry_run']
        set_targets = not opts['no_targets']

        if not DATA_FILE.exists():
            self.stderr.write(self.style.ERROR(f"Missing data file: {DATA_FILE}"))
            return

        # Lazy import so the command still loads if the service moves.
        from Inventory.services.community_progress import recalc_site_progress_percent

        with DATA_FILE.open(newline='') as f:
            rows = list(csv.DictReader(f))
        self.stdout.write(f"Loaded {len(rows)} community rows from {DATA_FILE.name}")

        if dry:
            project = None
            self.stdout.write(self.style.WARNING("DRY RUN — no writes."))
        else:
            project, created = Project.objects.get_or_create(
                code=UMBRELLA['code'], defaults=UMBRELLA)
            self.stdout.write(
                f"Umbrella project: {project.name} ({project.code}) "
                f"[{'created' if created else 'existing'}]")

        sites_created = sites_updated = targets_set = locked_skipped = no_community = 0

        for row in rows:
            region = (row.get('region') or '').strip()
            district = (row.get('district') or '').strip()
            community = (row.get('community') or '').strip()
            if not community:
                continue

            ht_e, ht_d, ht_s = _i(row, 'ht_planted'), _i(row, 'ht_dressed'), _i(row, 'ht_strung')
            lv_e, lv_d, lv_s = _i(row, 'lv_planted'), _i(row, 'lv_dressed'), _i(row, 'lv_strung')
            tx_i, tx_c = _i(row, 'tx_dressed'), _i(row, 'tx_commissioned')
            cs1, cs3 = _i(row, 'cs_1ph'), _i(row, 'cs_3ph')
            connections = cs1 + cs3

            ht_ct, lv_ct, tx_ct = _i(row, 'ht_contract'), _i(row, 'lv_contract'), _i(row, 'tx_contract')

            works_fields = dict(
                ht_poles_erected=ht_e, ht_poles_dressed=ht_d, ht_poles_strung=ht_s,
                lv_poles_erected=lv_e, lv_poles_dressed=lv_d, lv_poles_strung=lv_s,
                transformers_installed=tx_i, transformers_commissioned=tx_c,
                meters_1ph_installed=cs1, meters_3ph_installed=cs3,
            )

            # Resolve the canonical Community (targets live here).
            comm_obj = Community.objects.filter(
                region__iexact=region, district__iexact=district,
                community__iexact=community).order_by('id').first()
            if comm_obj is None:
                no_community += 1

            if dry:
                # Just account for what would happen.
                exists = ProjectSite.objects.filter(
                    region__iexact=region, district__iexact=district,
                    community__iexact=community).exists()
                sites_updated += 1 if exists else 0
                sites_created += 0 if exists else 1
                if set_targets and comm_obj is not None and not comm_obj.targets_locked:
                    targets_set += 1
                elif comm_obj is not None and comm_obj.targets_locked:
                    locked_skipped += 1
                continue

            with transaction.atomic():
                # Set Community targets from Kobo contract quantities.
                if set_targets and comm_obj is not None:
                    if comm_obj.targets_locked:
                        locked_skipped += 1
                    else:
                        changed = False
                        if ht_ct:
                            comm_obj.planned_ht_poles = ht_ct; changed = True
                        if lv_ct:
                            comm_obj.planned_lv_poles = lv_ct; changed = True
                        if tx_ct:
                            comm_obj.planned_transformers = tx_ct; changed = True
                        if connections:
                            comm_obj.planned_connections = connections; changed = True
                        if changed:
                            comm_obj.save()
                            targets_set += 1

                site, created = ProjectSite.objects.update_or_create(
                    project=project, region=region, district=district,
                    community=community,
                    defaults=dict(
                        name=community[:200],
                        code=(row.get('package_number') or 'SITE')[:50],
                        **works_fields,
                    ),
                )
                sites_created += 1 if created else 0
                sites_updated += 0 if created else 1

                result = recalc_site_progress_percent(site, community=comm_obj, save=False)
                site.works_status = _works_status(result['percent'], connections)
                site.save(update_fields=['progress_percent', 'works_status'])

        self.stdout.write(self.style.SUCCESS(
            f"\nDone{' (dry run)' if dry else ''}: "
            f"sites created={sites_created}, updated={sites_updated}, "
            f"targets set={targets_set}, locked skipped={locked_skipped}, "
            f"no matching community={no_community}"))
        if no_community:
            self.stdout.write(
                "Note: rows with no matching Community still get a ProjectSite, "
                "but their % stays 0 until a Community with targets exists.")
