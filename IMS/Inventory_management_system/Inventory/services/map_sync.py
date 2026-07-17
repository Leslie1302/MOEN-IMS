"""
Community registry → Ghana map sync (Phase 4).

The Ghana map and the community progress page both roll up from
ProjectSite rows, but before Phase 4 nothing created those rows — every
community had to be hand-registered as a site through the project admin,
or its progress and deliveries rolled up to nothing.

:func:`ensure_site_for_community` closes that gap: every active
Community in the registry gets a matching ProjectSite, attached to one
umbrella Project per programme (SHEP, Cost Sharing, …). Called from the
Community post_save signal and the ``sync_community_sites`` backfill
command.
"""
import logging

from ..models.projects import Project, ProjectSite

logger = logging.getLogger(__name__)

# Falls back to this when a community has no project_type set yet
DEFAULT_PROGRAMME = 'SHEP'


def ensure_site_for_community(community):
    """Create (or find) the ProjectSite representing this Community.

    Idempotent. An existing site for the same region/district/community
    (however it was created) is reused, never duplicated.
    Returns the site, or None for inactive communities.
    """
    if not getattr(community, 'is_active', True):
        return None

    existing = ProjectSite.objects.filter(
        community__iexact=(community.community or '').strip(),
        region__iexact=(community.region or '').strip(),
        district__iexact=(community.district or '').strip(),
    ).first()
    if existing:
        return existing

    programme = (
        community.project_type.name if community.project_type_id else DEFAULT_PROGRAMME
    )
    # One umbrella Project per programme keeps the map's per-type
    # breakdown working without inventing per-community projects.
    project, _ = Project.objects.get_or_create(
        code=f'PRG-{programme.upper().replace(" ", "-")}',
        defaults={
            'name': f'{programme} Programme',
            'description': f'Umbrella project for {programme} community sites '
                           f'(auto-created by map sync).',
            'project_type': programme,
            'status': 'Active',
            'consultant': '',
            'contractor': '',
        },
    )

    site = ProjectSite.objects.create(
        project=project,
        name=community.community,
        code=f'CTY-{community.pk}',  # deterministic, unique per community
        region=community.region,
        district=community.district,
        community=community.community,
        latitude=community.latitude,
        longitude=community.longitude,
        gps_coordinates=community.gps_coordinates,
        status='Planned',
    )
    logger.info(
        f"Map sync: created ProjectSite {site.pk} for community "
        f"'{community.community}' ({community.region}/{community.district}) "
        f"under {project.code}."
    )
    return site


def boq_communities_without_registry():
    """BoQ community names with no matching Community registry row.

    These are the silent string-match failures: their deliveries roll up
    to nothing on the map. Surfaced on the community progress page.
    """
    from ..models import BillOfQuantity, Community

    registered = {
        (r or '').strip().lower()
        for r in Community.objects.values_list('community', flat=True)
    }
    seen, missing = set(), []
    rows = (
        BillOfQuantity.objects.exclude(community__isnull=True)
        .exclude(community='')
        .values_list('region', 'district', 'community')
        .distinct()
    )
    for region, district, community in rows:
        key = community.strip().lower()
        if key and key not in registered and key not in seen:
            seen.add(key)
            missing.append(
                {'region': region, 'district': district, 'community': community})
    return sorted(missing, key=lambda m: (m['region'], m['community']))
