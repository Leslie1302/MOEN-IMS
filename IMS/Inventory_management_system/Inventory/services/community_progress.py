"""
Community progress services.

Two responsibilities, deliberately the *only* bridge between the BoQ and the
works-progress tracker:

  * :func:`pull_targets_from_boq`  — one-time, human-confirmed copy of BoQ
    contract quantities into a community's planned-target snapshot. After the
    pull the two are decoupled: completion never reads BoQ again, and BoQ
    revisions / over-issuance never move a completion denominator.

  * :func:`compute_site_completion` — the 5-stage (HT → LV → Transformer →
    Meters → Commissioning) works completion, each stage worth 20% and scored
    as recorded works ÷ frozen target. Materials may arrive out of order;
    completion still credits the stages strictly in sequence.

One community == one site in this deployment, so a site's completion is the
community's completion. ``compute_site_completion`` resolves the matching
Community for the frozen targets.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone


STAGE_WEIGHT = 20  # percentage points per stage; 5 stages × 20 = 100


# ───────────────────────── material-kind helpers ─────────────────────────

def _kind(description: str, item_code: str = '') -> str:
    """Classify a BoQ line as 'pole' / 'conductor' / 'transformer' / 'meter'
    / '' from its text. ``voltage_class`` carries HT vs LV; this carries the
    physical kind so HT poles and HT conductor don't conflate in the pull."""
    text = f"{description or ''} {item_code or ''}".lower()
    if 'transformer' in text or 'xfmr' in text:
        return 'transformer'
    if 'meter' in text:
        return 'meter'
    if 'pole' in text:
        return 'pole'
    if any(k in text for k in ('conductor', 'cable', 'acsr', 'abc')):
        return 'conductor'
    return ''


# ─────────────────────────── BoQ → targets pull ──────────────────────────

# Maps a community's target field -> a human label, for the diff preview.
TARGET_FIELDS = [
    ('planned_ht_poles',       'HT poles'),
    ('planned_lv_poles',       'LV poles'),
    ('planned_transformers',   'Transformers'),
    ('planned_connections',    'Service connections (meters)'),
    ('planned_ht_conductor_m', 'HT conductor (m)'),
    ('planned_lv_conductor_m', 'LV conductor (m)'),
]


def _derive_targets_from_boq(community):
    """Aggregate the community's BoQ lines into proposed target values.

    Returns a dict {field_name: number}. Counts are integers; conductor
    metres are Decimals. Uses the explicit ``voltage_class`` when set, falling
    back to keyword detection for HT/LV so partially-classified data still
    contributes.
    """
    from ..models import BillOfQuantity

    proposed = {f: Decimal('0') for f, _ in TARGET_FIELDS}

    rows = BillOfQuantity.objects.filter(
        region__iexact=community.region,
        district__iexact=community.district,
        community__iexact=(community.community or ''),
    )
    for boq in rows:
        qty = Decimal(str(boq.contract_quantity or 0))
        if qty <= 0:
            continue
        kind = _kind(boq.material_description, boq.item_code)
        vc = (boq.voltage_class or '').upper()

        # Resolve HT vs LV: explicit field first, then keyword fallback.
        desc = (boq.material_description or '').lower()
        if vc in ('HT', 'LV'):
            voltage = vc
        elif any(k in desc for k in ('h.t', 'ht ', '11kv', '33kv', 'high tension', 'high voltage', 'primary')):
            voltage = 'HT'
        elif any(k in desc for k in ('l.v', 'lv ', '415v', '400v', 'low tension', 'low voltage', 'secondary')):
            voltage = 'LV'
        else:
            voltage = 'LV'  # generic reticulation default

        if kind == 'transformer' or vc == 'XFMR':
            proposed['planned_transformers'] += qty
        elif kind == 'meter' or vc == 'METER':
            proposed['planned_connections'] += qty
        elif kind == 'pole':
            proposed['planned_ht_poles' if voltage == 'HT' else 'planned_lv_poles'] += qty
        elif kind == 'conductor':
            proposed['planned_ht_conductor_m' if voltage == 'HT' else 'planned_lv_conductor_m'] += qty
        # other / unclassified lines contribute to no target

    # Counts are whole numbers; conductor stays metres.
    out = {}
    for f, _ in TARGET_FIELDS:
        val = proposed[f]
        if f.endswith('_m'):
            out[f] = val.quantize(Decimal('0.01'))
        else:
            out[f] = int(val.to_integral_value())
    return out


def preview_targets_from_boq(community):
    """Return a per-field diff {field: {'label','current','proposed','delta'}}
    WITHOUT writing anything — drives the confirmation screen."""
    proposed = _derive_targets_from_boq(community)
    diff = {}
    for field, label in TARGET_FIELDS:
        current = getattr(community, field) or 0
        prop = proposed[field]
        # Normalise types for delta display.
        cur_n = Decimal(str(current))
        prop_n = Decimal(str(prop))
        diff[field] = {
            'label': label,
            'current': current,
            'proposed': prop,
            'delta': prop_n - cur_n,
        }
    return diff


def pull_targets_from_boq(community, user=None, *, apply=False):
    """Preview (apply=False) or apply (apply=True) the BoQ-derived targets.

    On apply, the snapshot is written and provenance stamped. Honours
    ``targets_locked`` — a locked community is never overwritten. Returns the
    diff dict either way so the caller can show what changed.
    """
    diff = preview_targets_from_boq(community)
    if not apply:
        return diff
    if community.targets_locked:
        return diff  # frozen baseline: caller should surface a "locked" notice

    for field, _ in TARGET_FIELDS:
        setattr(community, field, diff[field]['proposed'])
    community.targets_source = 'boq_pull'
    community.targets_pulled_at = timezone.now()
    community.targets_pulled_by = user
    community.save(update_fields=[f for f, _ in TARGET_FIELDS] + [
        'targets_source', 'targets_pulled_at', 'targets_pulled_by',
    ])
    return diff


# ─────────────────────────── completion math ────────────────────────────

def _stage(label, numerator, denominator):
    """Build one stage's result. Denominator 0/None -> no target set."""
    has_target = bool(denominator and denominator > 0)
    if has_target:
        fraction = min(1.0, float(numerator) / float(denominator))
    else:
        fraction = 0.0
    return {
        'label': label,
        'numerator': round(float(numerator), 2),
        'denominator': float(denominator or 0),
        'fraction': round(fraction, 4),
        'pct_points': round(STAGE_WEIGHT * fraction, 1),
        'has_target': has_target,
    }


def _targets_for(region, district, community):
    """Resolve the frozen targets for a site's location (1 community = 1 site)."""
    from ..models import Community
    return Community.objects.filter(
        region__iexact=region or '',
        district__iexact=district or '',
        community__iexact=community or '',
        is_active=True,
    ).first()


def resolve_canonical_community(region, district, community):
    """Return (canonical_community, duplicate_count) for a location.

    The canonical row is the SAME one completion reads via ``_targets_for``
    (``.first()`` over active matches). Duplicate community records for the
    same (region, district, community) are reported so the caller can warn —
    targets are only ever written to the canonical row, never multiplied
    across duplicates.
    """
    from ..models import Community
    qs = Community.objects.filter(
        region__iexact=region or '',
        district__iexact=district or '',
        community__iexact=community or '',
        is_active=True,
    ).order_by('id')
    rows = list(qs)
    return (rows[0] if rows else None, len(rows))


def pull_targets_for_location(region, district, community, user=None, *, apply=False):
    """Resolve the canonical community for a location and pull its BoQ targets.

    Returns a dict describing the outcome so a view can message the user:
      {'status': 'applied'|'preview'|'locked'|'no_community',
       'community': <obj or None>, 'duplicates': int, 'diff': {...} or None}

    Duplicate-safe: writes only to the canonical row (see
    ``resolve_canonical_community``); a >1 ``duplicates`` count is surfaced
    so duplicate records can be cleaned up, but never causes double-counting.
    Idempotent: targets are SET to the BoQ totals, so re-running yields the
    same numbers rather than accumulating.
    """
    canonical, dup = resolve_canonical_community(region, district, community)
    if canonical is None:
        return {'status': 'no_community', 'community': None,
                'duplicates': 0, 'diff': None}
    if canonical.targets_locked:
        return {'status': 'locked', 'community': canonical,
                'duplicates': dup, 'diff': preview_targets_from_boq(canonical)}
    diff = pull_targets_from_boq(canonical, user, apply=apply)
    return {'status': 'applied' if apply else 'preview',
            'community': canonical, 'duplicates': dup, 'diff': diff}


def bulk_pull_targets(boq_queryset, user=None):
    """Pull BoQ targets for every DISTINCT (region, district, community) in a
    BoQ queryset. De-duplicates locations first so a community spread over
    several package rows is pulled exactly once into its canonical record.

    Returns a summary: {'pulled', 'locked', 'no_community', 'duplicates_seen',
    'locations'}.
    """
    seen = set()
    summary = {'pulled': 0, 'locked': 0, 'no_community': 0,
               'duplicates_seen': 0, 'locations': 0}
    for row in boq_queryset.values('region', 'district', 'community').iterator():
        comm = (row.get('community') or '').strip()
        if not comm:
            continue
        key = ((row.get('region') or '').strip().lower(),
               (row.get('district') or '').strip().lower(),
               comm.lower())
        if key in seen:
            continue
        seen.add(key)
        summary['locations'] += 1
        res = pull_targets_for_location(
            row.get('region'), row.get('district'), comm, user, apply=True)
        if res['duplicates'] > 1:
            summary['duplicates_seen'] += 1
        if res['status'] == 'applied':
            summary['pulled'] += 1
        elif res['status'] == 'locked':
            summary['locked'] += 1
        elif res['status'] == 'no_community':
            summary['no_community'] += 1
    return summary


def compute_site_completion(site, community=None):
    """Return the 5-stage completion for a ProjectSite.

    {'percent': float, 'stages': [stage, ...], 'has_targets': bool}

    ``community`` may be passed to avoid a lookup; otherwise it's resolved
    from the site's region/district/community.
    """
    if community is None:
        community = _targets_for(site.region, site.district, site.community)

    t = community  # frozen targets live here
    ht_poles = (t.planned_ht_poles if t else 0) or 0
    lv_poles = (t.planned_lv_poles if t else 0) or 0
    transformers = (t.planned_transformers if t else 0) or 0
    connections = (t.planned_connections if t else 0) or 0

    ht_works = ((site.ht_poles_erected or 0) + (site.ht_poles_dressed or 0)
                + (site.ht_poles_strung or 0)) / 3.0
    lv_works = ((site.lv_poles_erected or 0) + (site.lv_poles_dressed or 0)
                + (site.lv_poles_strung or 0)) / 3.0
    meters = (site.meters_1ph_installed or 0) + (site.meters_3ph_installed or 0)

    stages = [
        _stage('HT works',      ht_works,                         ht_poles),
        _stage('LV works',      lv_works,                         lv_poles),
        _stage('Transformer',   site.transformers_installed or 0, transformers),
        _stage('Meters',        meters,                           connections),
        _stage('Commissioning', site.transformers_commissioned or 0, transformers),
    ]
    percent = round(sum(s['pct_points'] for s in stages), 1)
    return {
        'percent': percent,
        'stages': stages,
        'has_targets': any(s['has_target'] for s in stages),
    }


def recalc_site_progress_percent(site, community=None, save=False):
    """Set ``site.progress_percent`` from the derived completion.

    The column is retained so the Ghana map keeps reading one number; this
    keeps it in sync whenever site works change. Returns the new percent.
    """
    result = compute_site_completion(site, community=community)
    site.progress_percent = int(round(result['percent']))
    if save:
        site.save(update_fields=['progress_percent'])
    return result
