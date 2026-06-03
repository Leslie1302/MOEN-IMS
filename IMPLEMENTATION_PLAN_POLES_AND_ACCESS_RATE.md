# Implementation Plan — Poles Release Form + Access Rate Map

**Owner:** Leslie Nii Adjei
**Drafted:** 2026-06-01
**Scope:** Two parallel tracks that can ship independently. Track A is a
small refactor; Track B is a new feature.

---

## Track A — Poles release request form: drop redundant spec inputs

### Problem

The poles request form (`StreetlightsRequestForm` in
`Inventory/forms/request_flow.py`) asks for `pole_height_m`, `lumen_rating`,
and `pole_type` as free-text fields. These are written only to
`MaterialOrder.notes`, so they:

- Don't filter the Material dropdown (user can pick an 8 m pole and type
  "12" in height — no validation).
- Don't reconcile against `InventoryItem.code`, which already uniquely
  identifies the SKU.
- Aren't reportable without re-parsing notes.

The `InventoryItem` model already enforces one SKU per `(code, warehouse)`,
so each pole variant is — or should be — its own stock row.

### Naming cleanup (do first, no behaviour change)

The class, project-type code, and constants are named "Streetlights" but
the programme is **Poles**. Rename:

| File | From | To |
|---|---|---|
| `Inventory/constants.py` | `PROJECT_TYPE_STREETLIGHTS = 'streetlights'` | `PROJECT_TYPE_POLES = 'poles'` |
| `Inventory/constants.py` | `PROJECT_TYPE_TO_CHARFIELD[...'streetlights'] = 'STREET'` | `[...'poles'] = 'POLES'` |
| `Inventory/forms/request_flow.py` | `class StreetlightsRequestForm` | `class PolesRequestForm` |
| `Inventory/forms/request_flow.py` | `FORM_BY_PROJECT_CODE[PROJECT_TYPE_STREETLIGHTS]` | `FORM_BY_PROJECT_CODE[PROJECT_TYPE_POLES]` |
| `Inventory/templates/Inventory/request_material_v2.html` | `project_type.code == 'streetlights'` | `'poles'` |

Data migration: update the `ProjectType` row in place (`code='streetlights'`
→ `'poles'`, `name='Streetlights'` → `'Poles'`). Also remap any
`MaterialOrder.project_type='STREET'` → `'POLES'`. Migration name:
`0055_rename_streetlights_to_poles.py`.

### Form refactor

Remove the three spec fields from `PolesRequestForm`:

```python
# DELETE:
pole_height_m = forms.DecimalField(...)
lumen_rating  = forms.IntegerField(...)
pole_type     = forms.CharField(...)

# DELETE the [Streetlights] notes prefix block in collect_project_specific_notes()
```

Drop the corresponding card from `request_material_v2.html` (lines ~99–119).

### Make the Material dropdown spec-aware (so it can replace what we removed)

Currently the dropdown deduplicates by `code` and shows `name` only. For
poles requesters, that means "8m galvanised steel pole" and "12m concrete
pole" appear as two list items distinguished only by the name string.
That's fine — but reporting is weak.

Add structured columns to `InventoryItem` so the SKU is the source of
truth for spec data:

```python
# Inventory/models/inventory.py — InventoryItem
height_m       = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
material_type  = models.CharField(max_length=50, blank=True)   # 'steel', 'concrete', 'wood'
spec_notes     = models.CharField(max_length=200, blank=True)  # free-form fallback
```

Migration: `0056_inventoryitem_spec_columns.py`. Backfill from
existing `name` strings with a one-off script (regex pull "8m", "12m",
"steel", "concrete"). Items where backfill fails get flagged for manual
admin cleanup — log to a CSV.

### Acceptance criteria — Track A

- Renaming PR merges cleanly; no `MaterialOrder` rows orphaned; all URL
  reverses still resolve.
- Pole spec fields no longer render on the request form.
- Existing pole orders still display correctly (`notes` retains legacy
  text).
- New orders get spec data from the chosen `InventoryItem`, queryable as
  `order.inventory_item.height_m`.
- Audit query: `MaterialOrder.objects.filter(project_type='POLES')
  .values('inventory_item__height_m').annotate(c=Count('id'))` returns a
  clean breakdown by pole height.

### Effort estimate — Track A

~1.5 days. Rename + migration (4h), form/template edits (2h), spec
columns + backfill script (4h), test pass (2h).

---

## Track B — Access Rate map (formula-driven, national)

### Formula (this is the contract)

```
access_rate = (
    (7 × meters_3ph_installed)
    + (7 × meters_1ph_installed)
    + 27,980,911
) / 31,493,526
```

- 7 = persons per connection (national fallback; assumption, to be
  refined later when actual household-size data is collected).
- 27,980,911 = baseline population already electrified before the
  programme.
- 31,493,526 = total Ghana population.

### Phase B1 — Data model

#### B1.1 `MeterInstallation` (new model)

The single source of truth for the numerator's V and W counts.

```python
# Inventory/models/access_rate.py  (new file)

class MeterInstallation(auto_prefetch.Model):
    PHASE_CHOICES = [('1ph', '1-phase'), ('3ph', '3-phase')]

    community         = auto_prefetch.ForeignKey('Inventory.Community',
                                                  on_delete=models.PROTECT,
                                                  related_name='meter_installs')
    project_site      = auto_prefetch.ForeignKey('Inventory.ProjectSite',
                                                  on_delete=models.SET_NULL,
                                                  null=True, blank=True,
                                                  related_name='meter_installs')
    phase_type        = models.CharField(max_length=3, choices=PHASE_CHOICES, db_index=True)
    quantity          = models.PositiveIntegerField(help_text='Number of meters installed on this report')
    installation_date = models.DateField(db_index=True)
    reported_by       = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL,
                                                  null=True, related_name='meter_reports')
    verified_by       = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL,
                                                  null=True, blank=True,
                                                  related_name='meter_verifications')
    verified_at       = models.DateTimeField(null=True, blank=True)
    evidence_photo    = models.ImageField(upload_to='meter_evidence/', null=True, blank=True)
    notes             = models.TextField(blank=True)

    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-installation_date']
        indexes = [
            models.Index(fields=['phase_type', 'installation_date']),
            models.Index(fields=['community', 'phase_type']),
        ]
```

Only verified rows count toward the access rate — unverified rows show
as "pending" in the map's drill-down.

#### B1.2 `AccessRateConfig` (admin-editable singleton)

```python
class AccessRateConfig(auto_prefetch.Model):
    persons_per_connection      = models.PositiveIntegerField(default=7)
    baseline_population_access  = models.PositiveIntegerField(default=27_980_911)
    total_population            = models.PositiveIntegerField(default=31_493_526)

    effective_from              = models.DateField()
    notes                       = models.TextField(blank=True,
                                       help_text='Source / rationale for these values')

    created_at                  = models.DateTimeField(auto_now_add=True)
    created_by                  = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-effective_from']

    @classmethod
    def current(cls):
        """Return the row with the latest effective_from <= today."""
        from django.utils import timezone
        return (cls.objects.filter(effective_from__lte=timezone.now().date())
                            .order_by('-effective_from').first())
```

Seed one row in the migration with the values above and
`effective_from=2026-01-01`. Future updates land as new rows, not
edits — preserves reproducibility of historical reports.

#### B1.3 Migration

`0057_access_rate_models.py` — creates both tables, seeds config row.

### Phase B2 — Calculator service

```python
# Inventory/services/access_rate.py  (new)

from dataclasses import dataclass
from django.db.models import Sum, Q

@dataclass
class AccessRateResult:
    rate: float                  # 0.0–1.0
    rate_pct: float              # rate * 100, rounded 2dp
    meters_1ph: int
    meters_3ph: int
    pop_newly_served: int        # 7 * (V + W)
    baseline_population: int
    total_population: int
    config_id: int               # for audit
    as_of: datetime

def compute_access_rate(*, region=None, district=None, as_of=None):
    """
    Returns AccessRateResult. region/district filter the meter counts;
    when both are None, returns the national rate (the headline figure).
    Note: the formula's denominator is national; when filtering by region,
    we compute a *contribution* rate, not a regional access rate.
    """
    cfg = AccessRateConfig.current()
    qs = MeterInstallation.objects.filter(verified_at__isnull=False)
    if as_of:
        qs = qs.filter(installation_date__lte=as_of)
    if region:
        qs = qs.filter(community__region__iexact=region)
    if district:
        qs = qs.filter(community__district__iexact=district)

    totals = qs.aggregate(
        m1=Sum('quantity', filter=Q(phase_type='1ph')),
        m3=Sum('quantity', filter=Q(phase_type='3ph')),
    )
    m1 = totals['m1'] or 0
    m3 = totals['m3'] or 0
    newly_served = cfg.persons_per_connection * (m1 + m3)
    numerator    = newly_served + cfg.baseline_population_access
    rate         = numerator / cfg.total_population
    return AccessRateResult(
        rate=rate, rate_pct=round(rate * 100, 2),
        meters_1ph=m1, meters_3ph=m3,
        pop_newly_served=newly_served,
        baseline_population=cfg.baseline_population_access,
        total_population=cfg.total_population,
        config_id=cfg.pk, as_of=as_of or timezone.now(),
    )
```

Unit tests cover: baseline-only (zero meters → 88.84%), one 1ph meter
adds 7 to numerator, region filter narrows the count, unverified meters
excluded, config swap changes the result.

### Phase B3 — Map view changes

Edit `Inventory/views/map_views.py::ghana_map_data_api`:

- Keep the existing per-region `total_sites` / `completed_sites` payload
  but rename `access_rate` → `material_delivery_rate` (the BoQ-driven
  number is *material flow*, not access).
- Add a new `access_rate` block populated from
  `compute_access_rate()` — national headline plus per-region
  contribution numbers.
- Add per-region meter counts (1ph, 3ph) to the regional payloads.

New payload shape (additions only):

```json
{
  "national": {
    "material_delivery_rate": 62.4,
    "access_rate": {
      "rate_pct": 89.12,
      "meters_1ph": 4210, "meters_3ph": 187,
      "pop_newly_served": 30779,
      "baseline_population": 27980911,
      "total_population": 31493526,
      "config_id": 1
    }
  },
  "data": [
    {
      "name": "Greater Accra",
      "material_delivery_rate": 71.0,
      "meters_1ph": 812, "meters_3ph": 41,
      "pop_newly_served_in_region": 5971,
      ...
    },
    ...
  ]
}
```

### Phase B4 — Map UI

Update `Inventory/templates/Inventory/ghana_map.html` (and the variant
templates: `ghana_map_completed_sites.html`,
`ghana_map_active_sites.html`, `ghana_map_progress.html`):

- Headline card: "National electricity access rate: **X.XX%**"
  - Sub-line: "Baseline 27.98M + 7 × (V 1ph + W 3ph) installed = Y people / 31.49M total"
  - Tooltip on the 7: "Persons-per-connection estimate; refresh when survey data lands."
- Secondary card: "Material delivery rate: Z%" (renamed from the
  current "Access rate", with a small (i) icon explaining the
  difference).
- Region drill-down: show meters installed (1ph / 3ph) and the
  region's contribution to `pop_newly_served`.

### Phase B5 — Meter installation entry UI

Two entry points:

1. **Single-row form** at `/access-rate/meters/new/` — for a supervisor
   logging the day's installs from the field. Fields: community,
   phase_type, quantity, installation_date, evidence photo, notes.
2. **Bulk upload** via XLSX (mirror the existing
   `bulk_request_template.xlsx` pattern): columns are `region`,
   `district`, `community`, `phase_type`, `quantity`,
   `installation_date`. Resolver matches communities by
   `(region, district, community)`; unmatched rows go to a review
   queue.

Verification: a manager role hits a "Verify" button on each row, which
stamps `verified_by` and `verified_at`. Only verified rows feed the
access rate. Admin can bulk-verify by package / phase.

### Phase B6 — Decouple ProjectSite status from BoQ-only signal

Today `signals.sync_project_site_from_boq` sets `ProjectSite.status =
'Completed'` when BoQ delivery hits 100%. Add a parallel signal:

- New field `ProjectSite.works_status` — choices: Planned, In Progress,
  Energised, Commissioned.
- New signal on `MeterInstallation.save()` (when verified): if the
  community now has at least one verified meter, set
  `works_status='Energised'`; if site supervisor marks commissioning
  done, set `works_status='Commissioned'`.
- Rename the existing `ProjectSite.status` → `material_status` in a
  migration so the two fields are unambiguous. Keep `status` as a
  Python `@property` returning `works_status` for any legacy template
  that still reads it.

This is the bigger lift — gated behind Track A landing first so we're
not rewriting two things at once.

### Acceptance criteria — Track B

- `compute_access_rate()` with zero meters returns 88.85% (baseline
  only).
- Adding 1,000 verified 1ph meters bumps the national rate by
  exactly 7,000 / 31,493,526 = +0.0222 percentage points.
- Map headline shows the formula-driven number, not the
  BoQ-completion number.
- Region drill-down shows meter counts and population-served
  contribution.
- Unverified `MeterInstallation` rows do not move the rate.
- Updating `AccessRateConfig` (new row, later `effective_from`) takes
  effect on next page load without a deploy.
- Historical view: `compute_access_rate(as_of='2026-01-01')` returns
  the rate using config valid on that date.

### Effort estimate — Track B

~6–8 working days. Models + migration (1d), service + tests (1d), map
view + UI (2d), entry form + bulk upload (2d), works_status decoupling
(2d), QA (1d).

---

## Sequencing

1. **Week 1** — Track A in full (rename + form refactor + spec
   columns). Ships independently; unblocks cleaner reporting and gives
   the team an early win.
2. **Week 2** — Track B Phase B1–B3 (models, service, map view payload).
   At this point the map shows the new numbers via API but uses the
   existing template.
3. **Week 3** — Track B Phase B4–B5 (UI + entry forms). Ministry users
   can start logging meters.
4. **Week 4** — Track B Phase B6 (works_status decoupling). Last
   because it touches the most legacy code paths.

## Open questions for the team

- Persons-per-connection of 7 — who signs off on this for the headline
  number? GSS 2021 puts national average household size around 3.6;
  the 7 implies extended-family or shared-meter accounting. Document
  the rationale in the `AccessRateConfig.notes` field at seed time.
- Verification authority — which role can flip
  `MeterInstallation.verified_by`? Manager? Regional engineer?
- Evidence requirement — is the photo mandatory before a row can be
  verified, or just recommended?
- Baseline `27,980,911` — confirm the source (NEAP? GSS? Energy
  Commission?) so the audit trail is defensible.
