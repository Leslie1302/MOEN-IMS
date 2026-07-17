"""
Site progress views (consultant entry).

Three URL endpoints:

  * :func:`site_progress_list`   -- filterable table of ProjectSites with
                                    the current progress columns inline.
  * :func:`site_progress_edit`   -- single-site form to update works_status
                                    + progress_percent + progress_notes.
  * :func:`site_progress_api`    -- thin JSON endpoint the map's drill-down
                                    can hit to refresh a region's totals
                                    without a full page reload.

The page is the **interim** source of truth for the Ghana map headline:
consultants update sites here, and ``map_views.ghana_map_data_api`` reads
the same columns to compute the regional and national access rate. The
meter-driven formula in ``services/access_rate.py`` stays available for
the post-Energy-Commission flow.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Avg, Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..forms.site_progress import SiteProgressForm
from ..models import Community, MeterInstallation, Project, ProjectSite
from ..utils import is_consultant, is_management


def _sync_meter_installations(site, prev_1ph, prev_3ph, user):
    """Log the *increase* in a site's meter totals as MeterInstallation rows.

    The Site Progress page stores cumulative meter counts on the ProjectSite.
    Each time those counts go up, we record the difference as a
    MeterInstallation so the national access-rate formula (which reads
    verified MeterInstallation rows) reflects the new connections without
    double-counting. Decreases are corrections and create no row.

    The row is auto-verified only when the saving user can verify meters
    (``Inventory.change_meterinstallation``); otherwise it lands in the
    normal verification queue and contributes to the rate once a manager
    signs it off.

    Returns a short human-readable summary, or '' if nothing was logged.
    Never raises for the caller — a missing Community is reported, not fatal.
    """
    deltas = [
        ('1ph', (site.meters_1ph_installed or 0) - (prev_1ph or 0)),
        ('3ph', (site.meters_3ph_installed or 0) - (prev_3ph or 0)),
    ]
    deltas = [(phase, d) for phase, d in deltas if d > 0]
    if not deltas:
        return '', None

    community_obj = Community.objects.filter(
        region__iexact=site.region,
        district__iexact=site.district,
        community__iexact=(site.community or ''),
        is_active=True,
    ).first()
    if community_obj is None:
        return '', (
            f"Meter totals were saved on the site, but no active community "
            f"matches {site.region}/{site.district}/{site.community or '—'}, "
            f"so the access rate could not be updated. Add the community "
            f"record, then re-enter the meter count."
        )

    can_verify = user.has_perm('Inventory.change_meterinstallation')
    logged = []
    for phase, qty in deltas:
        install = MeterInstallation(
            community=community_obj,
            project_site=site,
            phase_type=phase,
            quantity=qty,
            installation_date=timezone.localdate(),
            reported_by=user,
            notes=f"Auto-logged from Site Progress update for {site.name}.",
        )
        if can_verify:
            install.mark_verified(user)
        install.save()
        logged.append(f"{qty} × {install.get_phase_type_display()}")

    summary = ", ".join(logged)
    if can_verify:
        return f"Access rate updated: +{summary} meters.", None
    return (
        f"Logged +{summary} meters for verification — the access rate "
        f"updates once a manager verifies them.",
        None,
    )


@login_required
def site_progress_list(request):
    """Filterable list of ProjectSites with inline progress columns."""
    qs = (
        ProjectSite.objects
        .select_related('project')
        .order_by('region', 'district', 'community')
    )

    region   = request.GET.get('region', '').strip()
    district = request.GET.get('district', '').strip()
    works_status = request.GET.get('works_status', '').strip()
    project_id   = request.GET.get('project', '').strip()
    search       = request.GET.get('q', '').strip()

    if region:
        qs = qs.filter(region__iexact=region)
    if district:
        qs = qs.filter(district__iexact=district)
    if works_status:
        qs = qs.filter(works_status=works_status)
    if project_id and project_id.isdigit():
        qs = qs.filter(project_id=int(project_id))
    if search:
        qs = qs.filter(
            Q(community__icontains=search)
            | Q(name__icontains=search)
            | Q(code__icontains=search),
        )

    # Headline counters for the filter strip. Computed off the filtered
    # queryset so the user sees what's in scope, not a stale national total.
    aggregates = qs.aggregate(
        total=Count('id'),
        energised=Count('id', filter=Q(works_status__in=('Energised', 'Commissioned'))),
        avg_progress=Avg('progress_percent'),
    )
    energised_pct = (
        round((aggregates['energised'] or 0) / (aggregates['total'] or 1) * 100, 1)
        if aggregates['total'] else 0
    )

    # Build the dropdown options off the unfiltered table so the user can
    # always navigate to a different region.
    regions   = (ProjectSite.objects.values_list('region', flat=True)
                                    .exclude(region='').distinct().order_by('region'))
    districts = (ProjectSite.objects.values_list('district', flat=True)
                                    .exclude(district='').distinct().order_by('district'))
    projects  = Project.objects.order_by('name')

    return render(request, 'Inventory/site_progress_list.html', {
        'sites': qs[:300],   # cap for page weight; pagination is a follow-up
        'regions': regions,
        'districts': districts,
        'projects': projects,
        'works_status_choices': ProjectSite.WORKS_STATUS_CHOICES,
        'filters': {
            'region': region, 'district': district,
            'works_status': works_status, 'project': project_id, 'q': search,
        },
        'aggregates': {
            'total':         aggregates['total'] or 0,
            'energised':     aggregates['energised'] or 0,
            'energised_pct': energised_pct,
            'avg_progress':  round(aggregates['avg_progress'] or 0, 1),
        },
        'page_title': 'Site progress',
    })


@login_required
@user_passes_test(lambda u: is_consultant(u) or is_management(u))
def site_progress_edit(request, pk: int):
    """Update one ProjectSite's progress fields."""
    site = get_object_or_404(
        ProjectSite.objects.select_related('project'), pk=pk,
    )

    if request.method == 'POST':
        # Snapshot the meter totals before the form mutates the instance, so
        # we can log only the increase as a MeterInstallation (access rate).
        prev_1ph = site.meters_1ph_installed
        prev_3ph = site.meters_3ph_installed
        form = SiteProgressForm(request.POST, instance=site)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.progress_updated_at = timezone.now()
            updated.progress_updated_by = request.user

            # Keep the legacy combined totals in sync as the sum of the HT+LV
            # lifecycle, so older readers (the breakdown aggregator) stay
            # correct until they're migrated to the granular fields.
            updated.poles_erected = (updated.ht_poles_erected or 0) + (updated.lv_poles_erected or 0)
            updated.conductor_laid_m = (
                (updated.ht_conductor_strung_m or 0) + (updated.lv_conductor_strung_m or 0)
            )

            # Derive the completion percentage from the 5-stage works model
            # against the community's frozen targets (replaces the old manual
            # entry). The Ghana map keeps reading progress_percent unchanged.
            from ..services.community_progress import recalc_site_progress_percent
            recalc_site_progress_percent(updated)

            # actual_completion_date keeps tracking the works state so the
            # existing map drill-downs that read it stay accurate.
            if (updated.works_status in ('Energised', 'Commissioned')
                    and not updated.actual_completion_date):
                updated.actual_completion_date = timezone.localdate()
            updated.save()

            meter_msg, meter_warning = _sync_meter_installations(
                updated, prev_1ph, prev_3ph, request.user,
            )

            messages.success(
                request,
                f"{site.community}: {updated.get_works_status_display()} "
                f"@ {updated.progress_percent}%.",
            )
            if meter_msg:
                messages.info(request, meter_msg)
            if meter_warning:
                messages.warning(request, meter_warning)
            next_url = request.POST.get('next') or 'site_progress_list'
            return redirect(next_url)
    else:
        form = SiteProgressForm(instance=site)

    # Recent deliveries to this community — surfaced as a popup so the
    # consultant enters works against what has actually arrived. Sourced from
    # BOTH confirmed site receipts (Received) and live transports (Delivered /
    # In transit), so it shows as soon as materials head to the site rather
    # than only after a receipt is logged.
    from ..models import SiteReceipt, MaterialTransport
    _loc = {
        'region__iexact': (site.region or ''),
        'district__iexact': (site.district or ''),
        'community__iexact': (site.community or ''),
    }
    deliveries = []
    receipts = (
        SiteReceipt.objects
        .filter(**{f'material_transport__material_order__{k}': v for k, v in _loc.items()})
        .select_related('material_transport__material_order')
        .order_by('-received_date')[:15]
    )
    for sr in receipts:
        deliveries.append({
            'material': sr.material_transport.material_name if sr.material_transport else '—',
            'qty': sr.received_quantity, 'when': sr.received_date,
            'status': 'Received on site', 'badge': 'success', 'condition': sr.condition or '',
        })
    transports = (
        MaterialTransport.objects
        .filter(status__in=['Delivered', 'In Transit'], site_receipt__isnull=True,
                **{f'material_order__{k}': v for k, v in _loc.items()})
        .select_related('material_order')
        .order_by('-date_dispatched')[:15]
    )
    for tr in transports:
        delivered = tr.status == 'Delivered'
        deliveries.append({
            'material': tr.material_name, 'qty': tr.quantity,
            'when': tr.date_delivered or tr.date_dispatched,
            'status': 'Delivered — awaiting receipt' if delivered else 'In transit — arriving',
            'badge': 'primary' if delivered else 'warning', 'condition': '',
        })
    deliveries.sort(key=lambda d: d['when'] or timezone.make_aware(timezone.datetime.min), reverse=True)
    recent_deliveries = deliveries[:12]

    return render(request, 'Inventory/site_progress_edit.html', {
        'form': form,
        'site': site,
        'recent_deliveries': recent_deliveries,
        'page_title': f'Update progress — {site.community or site.name}',
    })


@login_required
def site_progress_api(request):
    """JSON: per-region progress totals.

    Returned as ``{'regions': {'Greater Accra': {...}, ...}, 'national': {...}}``
    so the map drill-down and any external dashboard can poll one URL.
    """
    qs = ProjectSite.objects.all()

    region = request.GET.get('region', '').strip()
    if region:
        qs = qs.filter(region__iexact=region)

    rows = (
        qs.values('region')
          .annotate(
              total=Count('id'),
              energised=Count('id', filter=Q(works_status__in=('Energised', 'Commissioned'))),
              avg_progress=Avg('progress_percent'),
          )
    )

    regions = {}
    for row in rows:
        region_name = row['region'] or '—'
        total       = row['total'] or 0
        energised   = row['energised'] or 0
        regions[region_name] = {
            'total_sites':       total,
            'energised_sites':   energised,
            'energised_pct':     round((energised / total) * 100, 2) if total else 0,
            'avg_progress':      round(row['avg_progress'] or 0, 2),
        }

    nat = ProjectSite.objects.aggregate(
        total=Count('id'),
        energised=Count('id', filter=Q(works_status__in=('Energised', 'Commissioned'))),
        avg_progress=Avg('progress_percent'),
    )
    national_total     = nat['total'] or 0
    national_energised = nat['energised'] or 0

    return JsonResponse({
        'regions':  regions,
        'national': {
            'total_sites':     national_total,
            'energised_sites': national_energised,
            'energised_pct':   (round(national_energised / national_total * 100, 2)
                                if national_total else 0),
            'avg_progress':    round(nat['avg_progress'] or 0, 2),
        },
    })
