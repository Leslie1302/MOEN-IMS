"""
Access-rate calculator.

Implements the national electricity-access formula agreed with the Ministry:

    access_rate = (
        persons_per_connection × (meters_1ph_installed + meters_3ph_installed)
        + baseline_population_access
    ) / total_population

The three constants are read from the active ``AccessRateConfig`` row at
call time so changes to the assumptions land without a code deploy.

Only :class:`Inventory.models.MeterInstallation` rows with a non-null
``verified_at`` contribute to the numerator -- unverified installs sit in
the review queue and do not move the published number.

Geographic filters (``region`` / ``district``) narrow the meter count but
keep the baseline + denominator at their national values; that turns the
result into a *contribution* rate, not a regional access rate. The
returned :class:`AccessRateResult` flags this via ``scope``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from django.db.models import Q, Sum
from django.utils import timezone

from ..models.access_rate import AccessRateConfig, MeterInstallation


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
        Optional case-insensitive name filters. When supplied, only meter
        installations whose ``community`` matches are counted; the
        baseline and denominator stay at the national config values.
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

    qs = MeterInstallation.objects.filter(installation_date__lte=when)
    if not include_unverified:
        qs = qs.filter(verified_at__isnull=False)
    if region:
        qs = qs.filter(community__region__iexact=region)
    if district:
        qs = qs.filter(community__district__iexact=district)

    totals = qs.aggregate(
        m1=Sum('quantity', filter=Q(phase_type='1ph')),
        m3=Sum('quantity', filter=Q(phase_type='3ph')),
    )
    m1 = int(totals['m1'] or 0)
    m3 = int(totals['m3'] or 0)

    newly_served = cfg.persons_per_connection * (m1 + m3)
    numerator    = newly_served + cfg.baseline_population_access
    denominator  = cfg.total_population
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
        baseline_population=cfg.baseline_population_access,
        total_population=cfg.total_population,
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
