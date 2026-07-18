"""
Access-rate calculator.

Implements the national electricity-access formula agreed with the Ministry:

    access_rate = (
        persons_per_connection × (verified_meters + completion_connections)
        + baseline_population_access
    ) / total_population

``completion_connections`` credits communities marked Energised/Commissioned
on the Site Progress page for the un-metered remainder of their connection
target (see ``_completion_connection_topup``), so completions move the rate
even before every meter is logged.

The three constants are read from the active ``AccessRateConfig`` row at
call time so changes to the assumptions land without a code deploy.

Only :class:`Inventory.models.MeterInstallation` rows with a non-null
``verified_at`` contribute to the numerator -- unverified installs sit in
the review queue and do not move the published number.

A ``region`` filter uses that region's own baseline + denominator when a
:class:`RegionPopulation` row is seeded for it (a true regional access
rate); otherwise it falls back to the national values, giving a
*contribution* rate. A ``district`` filter always uses the national
denominator. ``AccessRateResult.scope`` reports which was used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from django.db.models import Q, Sum
from django.utils import timezone

from ..models.access_rate import AccessRateConfig, MeterInstallation, RegionPopulation


def _completion_connection_topup(*, region=None, district=None, after=None) -> int:
    """Connections credited to communities completed via Site Progress but
    not yet fully metered.

    For each ProjectSite marked Energised/Commissioned (and updated after
    ``after``), credit ``max(0, planned_connections - meters installed)``.
    Actual meters already count through MeterInstallation, so this only adds
    the *un-metered remainder* of a completed community's connection target —
    "target now, meters refine": completion moves the rate immediately, and
    real meter entries progressively replace the estimate.
    """
    from ..models import ProjectSite, Community  # local import avoids a cycle

    sites = ProjectSite.objects.filter(works_status__in=('Energised', 'Commissioned'))
    if after:
        sites = sites.filter(progress_updated_at__gt=after)
    if region:
        sites = sites.filter(region__iexact=region)
    if district:
        sites = sites.filter(district__iexact=district)

    total = 0
    # ponytail: one target lookup per completed site — fine at map scale;
    # batch by (region,district,community) if it ever gets slow.
    for site in sites.only('region', 'district', 'community',
                           'meters_1ph_installed', 'meters_3ph_installed'):
        target = Community.objects.filter(
            region__iexact=site.region or '',
            district__iexact=site.district or '',
            community__iexact=site.community or '',
            is_active=True,
        ).values_list('planned_connections', flat=True).first() or 0
        metered = (site.meters_1ph_installed or 0) + (site.meters_3ph_installed or 0)
        total += max(0, target - metered)
    return total


@dataclass(frozen=True)
class AccessRateResult:
    """Structured output of :func:`compute_access_rate`.

    Frozen so views/templates can't mutate aggregates while rendering. All
    counts are ints; ``rate`` is a float in ``[0, 1]`` and ``rate_pct`` is
    that value times 100 rounded to two decimal places.
    """

    rate: float
    rate_pct: float

    meters_1ph: int
    meters_3ph: int
    pop_newly_served: int

    persons_per_connection: int
    baseline_population: int
    total_population: int

    scope: str             # 'national' | 'region' | 'district'
    region: Optional[str]
    district: Optional[str]
    as_of: date
    config_id: int

    @property
    def total_meters(self) -> int:
        return self.meters_1ph + self.meters_3ph


def compute_access_rate(
    *,
    region: Optional[str] = None,
    district: Optional[str] = None,
    as_of: Optional[date] = None,
    include_unverified: bool = False,
) -> AccessRateResult:
    """Compute the access rate.

    Parameters
    ----------
    region, district:
        Optional case-insensitive name filters narrowing the meter count.
        A ``region`` with a seeded :class:`RegionPopulation` row also swaps
        the baseline + denominator to that region's own values and counts
        only meters installed after its snapshot date; otherwise the
        national config values apply.
    as_of:
        Optional date. Restricts meter installations to those on or
        before this date, and picks the ``AccessRateConfig`` row that was
        active on it. Defaults to today.
    include_unverified:
        Default ``False``. Set to ``True`` only for internal dashboards
        that want to show "what the rate *would* be once outstanding
        verifications land." The published rate must never include
        unverified rows.
    """

    when = as_of or timezone.localdate()
    if isinstance(when, datetime):
        when = when.date()

    cfg = AccessRateConfig.current(as_of=when)
    if cfg is None:
        raise RuntimeError(
            'No AccessRateConfig row is active. Seed one via migration '
            '0058 or create one in the admin before calling '
            'compute_access_rate().'
        )

    # A seeded RegionPopulation row gives this region its own denominator +
    # baseline (real regional rate); its baseline already counts everything
    # up to effective_from, so only meters installed after that date are
    # net-new. Without a row we fall back to the national config values.
    region_pop = (
        RegionPopulation.objects.filter(region__iexact=region).first()
        if region else None
    )

    qs = MeterInstallation.objects.filter(installation_date__lte=when)
    if not include_unverified:
        qs = qs.filter(verified_at__isnull=False)
    if region:
        qs = qs.filter(community__region__iexact=region)
    if district:
        qs = qs.filter(community__district__iexact=district)
    if region_pop:
        qs = qs.filter(installation_date__gt=region_pop.effective_from)

    totals = qs.aggregate(
        m1=Sum('quantity', filter=Q(phase_type='1ph')),
        m3=Sum('quantity', filter=Q(phase_type='3ph')),
    )
    m1 = int(totals['m1'] or 0)
    m3 = int(totals['m3'] or 0)

    baseline    = region_pop.baseline_population_access if region_pop else cfg.baseline_population_access
    denominator = region_pop.total_population if region_pop else cfg.total_population

    # Completions logged on the Site Progress page also raise the rate: a
    # community marked Energised/Commissioned credits its connection target
    # (over and above any meters already counted). Same post-baseline cutoff
    # as the meters so the snapshot isn't double-counted.
    cutoff = region_pop.effective_from if region_pop else cfg.effective_from
    completion_conns = _completion_connection_topup(
        region=region, district=district, after=cutoff,
    )

    newly_served = cfg.persons_per_connection * (m1 + m3 + completion_conns)
    numerator    = newly_served + baseline
    rate         = (numerator / denominator) if denominator else 0.0

    scope = 'national'
    if district:
        scope = 'district'
    elif region:
        scope = 'region'

    return AccessRateResult(
        rate=rate,
        rate_pct=round(rate * 100, 2),
        meters_1ph=m1,
        meters_3ph=m3,
        pop_newly_served=newly_served,
        persons_per_connection=cfg.persons_per_connection,
        baseline_population=baseline,
        total_population=denominator,
        scope=scope,
        region=region,
        district=district,
        as_of=when,
        config_id=cfg.pk,
    )


def regional_meter_breakdown(
    *,
    as_of: Optional[date] = None,
    include_unverified: bool = False,
) -> dict:
    """Per-region meter counts and population-served contribution.

    Returned as ``{region_name: {'meters_1ph': int, 'meters_3ph': int,
    'pop_newly_served': int}}``. Map views use this to colour and label
    each region without making 16 separate ``compute_access_rate`` calls.
    """

    when = as_of or timezone.localdate()
    if isinstance(when, datetime):
        when = when.date()
    cfg = AccessRateConfig.current(as_of=when)
    if cfg is None:
        return {}

    qs = MeterInstallation.objects.filter(installation_date__lte=when)
    if not include_unverified:
        qs = qs.filter(verified_at__isnull=False)

    rows = (
        qs.values('community__region', 'phase_type')
          .annotate(total=Sum('quantity'))
    )

    out: dict[str, dict[str, int]] = {}
    for row in rows:
        region = row['community__region'] or '—'
        bucket = out.setdefault(
            region,
            {'meters_1ph': 0, 'meters_3ph': 0, 'pop_newly_served': 0},
        )
        if row['phase_type'] == '1ph':
            bucket['meters_1ph'] = int(row['total'] or 0)
        elif row['phase_type'] == '3ph':
            bucket['meters_3ph'] = int(row['total'] or 0)

    # Second pass to fill pop_newly_served using the active config; cheap
    # in-Python so we avoid an extra DB roundtrip per region.
    for bucket in out.values():
        bucket['pop_newly_served'] = (
            cfg.persons_per_connection * (bucket['meters_1ph'] + bucket['meters_3ph'])
        )
    return out
