"""
One-shot backfill: ensure every active Community has a ProjectSite.

New communities sync automatically via the post_save signal; this
command covers the registry rows that existed before Phase 4.

    python manage.py sync_community_sites
"""
from django.core.management.base import BaseCommand

from Inventory.models import Community
from Inventory.services.map_sync import ensure_site_for_community


class Command(BaseCommand):
    help = 'Create a ProjectSite for every active Community missing one.'

    def handle(self, *args, **options):
        created = reused = 0
        for community in Community.objects.filter(is_active=True):
            before = community.pk and _site_exists(community)
            site = ensure_site_for_community(community)
            if site is None:
                continue
            if before:
                reused += 1
            else:
                created += 1
        self.stdout.write(self.style.SUCCESS(
            f'Done. Sites created: {created}, already present: {reused}.'))


def _site_exists(community):
    from Inventory.models import ProjectSite
    return ProjectSite.objects.filter(
        community__iexact=(community.community or '').strip(),
        region__iexact=(community.region or '').strip(),
        district__iexact=(community.district or '').strip(),
    ).exists()
