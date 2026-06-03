from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Count, Sum, F
from django.db.models.functions import Coalesce

from django.db.models import Avg, Q

from ..models.projects import Project, ProjectSite, BillOfQuantity
from ..services.access_rate import compute_access_rate, regional_meter_breakdown


def _consultant_access_rate(qs):
    """Interim headline access rate (consultant-reported).

    Returns a percent in [0, 100] computed as the share of ProjectSites
    that consultants have flipped to 'Energised' or 'Commissioned' via
    the Site Progress page. Falls back to 0 when the queryset is empty
    so the front-end renders a defined number.

    This stands in for the meter-formula calculation in
    ``services/access_rate.py`` until the Energy Commission engagement
    settles on the canonical methodology.
    """
    total = qs.count()
    if not total:
        return 0.0, 0, 0, 0.0
    energised = qs.filter(works_status__in=('Energised', 'Commissioned')).count()
    avg_progress = qs.aggregate(p=Avg('progress_percent'))['p'] or 0
    return (
        round(energised / total * 100, 2),
        total,
        energised,
        round(avg_progress, 1),
    )


@login_required
def ghana_map_view(request):
    """View to render the Ghana Map Representation"""
    return render(request, 'Inventory/ghana_map.html')


@login_required
def ghana_map_data_api(request):
    """
    Region-by-region map payload for the Ghana access-rate view.

    Produces three different "completion" numbers per region so the map
    can show what each one means without conflating them:

      * ``material_delivery_rate``  -- share of contracted BoQ material
        that has been delivered. Material flow, not access.
      * ``site_completion_rate``    -- share of ProjectSites whose
        ``status == 'Completed'`` (BoQ-driven).
      * ``access_rate``             -- **headline** national access rate.
        Interim source: consultant-reported ``works_status`` ('Energised'
        / 'Commissioned') counts via the Site Progress page. The
        meter-formula calculator in ``services.access_rate`` is kept on
        the backend for the post-Energy-Commission methodology but is
        not surfaced in the API payload right now -- only the consultant
        signal feeds the map. Swap by re-pointing this view at
        ``compute_access_rate()`` when EC engagement closes.

    Each region payload also carries a per-project-type breakdown so the
    map can surface which programme is doing the heaviest lifting in a
    given region.
    """
    standard_regions = [
        'Upper West', 'Upper East', 'North East', 'Savannah', 'Northern',
        'Oti', 'Bono East', 'Bono', 'Western North', 'Ahafo', 'Ashanti',
        'Eastern', 'Volta', 'Western', 'Central', 'Greater Accra'
    ]

    # Distinct project types currently in use, regardless of registry. The
    # map shows them all so retired ones don't quietly vanish from history.
    project_types = sorted(set(
        Project.objects.exclude(project_type__isnull=True)
        .exclude(project_type='')
        .values_list('project_type', flat=True)
        .distinct()
    ))

    # Meter-formula data still exposed for future-state dashboards, but
    # is no longer the source for the headline access rate. The
    # consultant signal below replaces it.
    meter_by_region = regional_meter_breakdown()

    data = []
    national_totals = {
        'total_sites': 0,
        'completed_sites': 0,
        'active_sites': 0,
        'planned_sites': 0,
        'on_hold_sites': 0,
    }
    national_by_type = {pt: {'total': 0, 'completed': 0} for pt in project_types}

    for region in standard_regions:
        region_sites = ProjectSite.objects.filter(region__icontains=region)

        total_sites = region_sites.count()
        completed_sites = region_sites.filter(status='Completed').count()
        active_sites = region_sites.filter(status='Active').count()
        planned_sites = region_sites.filter(status='Planned').count()
        on_hold_sites = region_sites.filter(status='On Hold').count()

        # Site-completion rate: share of ProjectSites that the BoQ signal
        # has flipped to 'Completed'. Useful operationally but does NOT
        # mean people have electricity -- communities can be 100% green
        # here while no meters are energised. Renamed from access_rate to
        # site_completion_rate in Phase B3 to remove that ambiguity.
        site_completion_rate = (
            round((completed_sites / total_sites) * 100, 2) if total_sites > 0 else 0
        )

        # Consultant-driven access rate for this region. This is the
        # interim source of truth -- consultants update each site from
        # the Site Progress page and the map reads it directly.
        (regional_access_rate, _, energised_sites,
         regional_avg_progress) = _consultant_access_rate(region_sites)

        # Material-delivery rate for this region: share of contracted
        # BoQ quantities that have actually been received. Material flow
        # answer. Complements site_completion_rate and converges with it
        # over time via the post_save signal on BillOfQuantity.
        boq_region = BillOfQuantity.objects.filter(region__icontains=region).aggregate(
            contract=Coalesce(Sum('contract_quantity'), 0.0),
            received=Coalesce(Sum('quantity_received'), 0.0),
        )
        boq_contract = float(boq_region['contract'] or 0)
        boq_received = float(boq_region['received'] or 0)
        material_delivery_rate = (
            round((boq_received / boq_contract) * 100, 2) if boq_contract > 0 else 0
        )

        # Project-type contribution within this region. Sites tie to a
        # Project via FK, so we can read project_type off the related row.
        by_type = []
        for pt in project_types:
            pt_sites = region_sites.filter(project__project_type=pt)
            pt_total = pt_sites.count()
            pt_completed = pt_sites.filter(status='Completed').count()
            by_type.append({
                'project_type': pt,
                'total_sites': pt_total,
                'completed_sites': pt_completed,
                'access_rate': (
                    round((pt_completed / pt_total) * 100, 2) if pt_total > 0 else 0
                ),
            })
            national_by_type[pt]['total'] += pt_total
            national_by_type[pt]['completed'] += pt_completed

        national_totals['total_sites'] += total_sites
        national_totals['completed_sites'] += completed_sites
        national_totals['active_sites'] += active_sites
        national_totals['planned_sites'] += planned_sites
        national_totals['on_hold_sites'] += on_hold_sites

        meter_bucket = meter_by_region.get(region, {
            'meters_1ph': 0, 'meters_3ph': 0, 'pop_newly_served': 0,
        })

        data.append({
            'name': region,
            # The map's choropleth fill keys off `value`. Keep this on
            # site_completion_rate so existing front-end colour scales
            # continue to work; the formula-driven national access rate
            # is shown in the headline card, not the regional fill.
            'value': site_completion_rate,
            'total_sites': total_sites,
            'completed_sites': completed_sites,
            'active_sites': active_sites,
            'planned_sites': planned_sites,
            'on_hold_sites': on_hold_sites,
            # ----- consultant-driven access rate (headline source) -----
            'access_rate': regional_access_rate,
            'energised_sites': energised_sites,
            'consultant_avg_progress': regional_avg_progress,
            # Adjacent measures kept for context.
            'site_completion_rate': site_completion_rate,
            'material_delivery_rate': material_delivery_rate,
            # Deprecated aliases. Removed once front-end JS migrates.
            'boq_access_rate': material_delivery_rate,
            # BoQ totals (material-flow view).
            'boq_contract_quantity': boq_contract,
            'boq_received_quantity': boq_received,
            # ----- meter-driven contribution to the national access rate -----
            'meters_1ph': meter_bucket['meters_1ph'],
            'meters_3ph': meter_bucket['meters_3ph'],
            'pop_newly_served_in_region': meter_bucket['pop_newly_served'],
            'by_project_type': by_type,
        })

    national_site_completion_rate = round(
        (national_totals['completed_sites'] / national_totals['total_sites']) * 100, 2
    ) if national_totals['total_sites'] > 0 else 0

    # National BoQ material-delivery rate.
    boq_national = BillOfQuantity.objects.aggregate(
        contract=Coalesce(Sum('contract_quantity'), 0.0),
        received=Coalesce(Sum('quantity_received'), 0.0),
    )
    boq_national_contract = float(boq_national['contract'] or 0)
    boq_national_received = float(boq_national['received'] or 0)
    national_material_delivery_rate = round(
        (boq_national_received / boq_national_contract) * 100, 2
    ) if boq_national_contract > 0 else 0

    # National access rate -- the headline number. Interim source is
    # consultant-reported completion via the Site Progress page; the
    # meter-formula calculator lives on the backend at
    # ``services/access_rate.compute_access_rate()`` for the future flow
    # but is not exposed here.
    (national_access_rate, national_total_sites_for_access,
     national_energised, national_avg_progress) = _consultant_access_rate(
        ProjectSite.objects.all(),
    )
    access_payload = {
        'rate_pct': national_access_rate,
        'energised_sites': national_energised,
        'total_sites_in_scope': national_total_sites_for_access,
        'avg_consultant_progress': national_avg_progress,
        'source': 'consultant_inputs',
        'caveat': (
            'Interim: averaged from consultant-reported works status. '
            'Replaces the meter-formula calc until Energy Commission '
            'engagement closes.'
        ),
    }

    national_by_type_payload = []
    for pt, vals in national_by_type.items():
        national_by_type_payload.append({
            'project_type': pt,
            'total_sites': vals['total'],
            'completed_sites': vals['completed'],
            'access_rate': (
                round((vals['completed'] / vals['total']) * 100, 2)
                if vals['total'] > 0 else 0
            ),
        })

    return JsonResponse({
        'data': data,
        'national': {
            'total_sites': national_totals['total_sites'],
            'completed_sites': national_totals['completed_sites'],
            'active_sites': national_totals['active_sites'],
            'planned_sites': national_totals['planned_sites'],
            'on_hold_sites': national_totals['on_hold_sites'],
            # The headline access rate the hero card reads.
            'access_rate': access_payload,
            # Adjacent measures for the secondary tiles.
            'site_completion_rate': national_site_completion_rate,
            'material_delivery_rate': national_material_delivery_rate,
            # Deprecated aliases. Removed once front-end JS migrates.
            'boq_contract_quantity': boq_national_contract,
            'boq_received_quantity': boq_national_received,
            'boq_access_rate': national_material_delivery_rate,
            'by_project_type': national_by_type_payload,
            'headline': (
                'Nationwide electricity access — '
                'consultant-reported completion (interim)'
            ),
        }
    }, safe=False)
