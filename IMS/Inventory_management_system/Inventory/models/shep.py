from django.db import models
import auto_prefetch
from .utils import generate_abbreviation


class Community(auto_prefetch.Model):
    """
    A community served by the Ministry of Energy. Used to populate cascading
    dropdowns in material request forms (region -> district -> community ->
    package, where package is SHEP-specific and optional for non-SHEP types).

    Project type is required so reports and forms can distinguish between
    SHEP, Cost Sharing, Streetlights, and any other project_type rows seeded
    in Inventory.0033_project_type_people_and_seed.

    Renamed from SHEPCommunity in Inventory.0034_rename_shep_to_community.
    The legacy name remains as an alias in Inventory/models/__init__.py for
    backward compatibility with existing imports across views, forms, and
    templates -- those will be updated incrementally in subsequent migrations.

    Enhanced with geospatial fields for Ghana Map tracking (Phase 2).
    """

    region = models.CharField(max_length=100, help_text="Region name", db_index=True)
    region_abbr = models.CharField(
        max_length=10, blank=True, editable=False,
        help_text="Auto-generated region abbreviation",
    )
    district = models.CharField(max_length=100, help_text="District name", db_index=True)
    district_abbr = models.CharField(
        max_length=10, blank=True, editable=False,
        help_text="Auto-generated district abbreviation",
    )
    community = models.CharField(max_length=100, help_text="Community name", db_index=True)
    community_abbr = models.CharField(
        max_length=10, blank=True, editable=False,
        help_text="Auto-generated community abbreviation",
    )

    # Optional. Required (form-level, not DB-level) when project_type is SHEP.
    package_number = models.CharField(
        max_length=50,
        blank=True,
        help_text="Package number for this community under its project type. "
                  "Used across programmes (SHEP, Cost Sharing, Streetlights) to "
                  "track releases and reconcile them to a specific BoQ package line.",
    )

    # Geospatial fields (Phase 2)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Community latitude coordinate"
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Community longitude coordinate"
    )
    gps_coordinates = models.CharField(
        max_length=100, null=True, blank=True,
        help_text="GPS coordinates as 'lat,lon' format"
    )

    project_type = auto_prefetch.ForeignKey(
        'Inventory.ProjectType',
        on_delete=models.PROTECT,
        related_name='communities',
        null=True,  # nullable for safety during rollout; tighten later
        blank=False,
        help_text="Which project this community is served under.",
    )

    # Optional: linked MP for Cost Sharing / Streetlights. The consignee
    # resolver also falls back to district/region matches when this is unset,
    # so it's purely an override / explicit-binding mechanism.
    member_of_parliament = auto_prefetch.ForeignKey(
        'Inventory.MemberOfParliament',
        on_delete=models.SET_NULL,
        related_name='communities',
        null=True,
        blank=True,
        help_text="Optional explicit MP binding. If set, used as the consignee "
                  "for Cost Sharing and Streetlights releases at this community.",
    )
    constituency = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional. Used by the consignee resolver to look up the MP "
                  "when no explicit member_of_parliament binding is set.",
    )

    # Optional: linked Project Consultant for SHEP. Same pattern as the MP
    # binding above -- if set, used as the consignee; otherwise the resolver
    # falls back to looking up a consultant by region (and optionally district).
    project_consultant = auto_prefetch.ForeignKey(
        'Inventory.ProjectConsultant',
        on_delete=models.SET_NULL,
        related_name='communities',
        null=True,
        blank=True,
        help_text="Optional explicit consultant binding. If set, used as the "
                  "consignee for SHEP releases at this community. Otherwise "
                  "the resolver looks up a consultant by region.",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this community is currently active",
    )

    # ── Progress-completion targets (frozen snapshot, seeded from BoQ) ──
    # These are the denominators for the 5-stage works completion. They are a
    # COPY of the BoQ contract quantities taken once via the explicit
    # "Pull targets from BoQ" action — never a live lookup. After the pull,
    # the BoQ and the progress tracker are functionally separate: BoQ
    # revisions / over-issuance / justifications do not move these numbers,
    # and progress works never write back to BoQ. Targets stay manually
    # editable so real scope can diverge from contract.
    planned_ht_poles = models.PositiveIntegerField(
        default=0, help_text='Planned HT poles (denominator for HT-works stage).')
    planned_lv_poles = models.PositiveIntegerField(
        default=0, help_text='Planned LV poles (denominator for LV-works stage).')
    planned_transformers = models.PositiveIntegerField(
        default=0, help_text='Planned transformers (denominator for transformer + commissioning stages).')
    planned_connections = models.PositiveIntegerField(
        default=0, help_text='Planned service connections / meters (denominator for the meters stage).')
    planned_ht_conductor_m = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Planned HT conductor in metres (reference; not a completion denominator).')
    planned_lv_conductor_m = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Planned LV conductor in metres (reference; not a completion denominator).')

    TARGETS_SOURCE_CHOICES = [
        ('manual',   'Entered manually'),
        ('boq_pull', 'Pulled from BoQ'),
    ]
    targets_source = models.CharField(
        max_length=10, choices=TARGETS_SOURCE_CHOICES, default='manual', blank=True,
        help_text='How the planned targets were last set.')
    targets_pulled_at = models.DateTimeField(
        null=True, blank=True, help_text='When targets were last pulled from BoQ.')
    targets_pulled_by = auto_prefetch.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='community_target_pulls',
        help_text='Who last pulled targets from BoQ.')
    targets_locked = models.BooleanField(
        default=False,
        help_text='When set, a BoQ pull will not overwrite these targets (manual baseline frozen).')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        verbose_name = 'Community'
        verbose_name_plural = 'Communities'
        ordering = ['region', 'district', 'community']
        # Including project_type in the unique tuple lets the same physical
        # community be served under multiple project types simultaneously
        # (e.g. Abokobi may have a SHEP row and a Cost Sharing row). For
        # SHEP, package_number distinguishes within the same (region,
        # district, community); for non-SHEP, package_number is empty and
        # project_type is what disambiguates.
        unique_together = [
            ('region', 'district', 'community', 'package_number', 'project_type'),
        ]
        indexes = [
            models.Index(fields=['region', 'district']),
            models.Index(fields=['region', 'district', 'community']),
        ]

    def save(self, *args, **kwargs):
        """Auto-generate abbreviations on save."""
        self.region_abbr = generate_abbreviation(self.region)
        self.district_abbr = generate_abbreviation(self.district)
        self.community_abbr = generate_abbreviation(self.community)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.package_number:
            return f"{self.region} > {self.district} > {self.community} ({self.package_number})"
        return f"{self.region} > {self.district} > {self.community}"

    def get_coordinates_as_tuple(self):
        """Return coordinates as (lat, lon) tuple if available"""
        if self.latitude and self.longitude:
            return (float(self.latitude), float(self.longitude))
        elif self.gps_coordinates:
            try:
                parts = [p.strip() for p in self.gps_coordinates.split(',')]
                if len(parts) == 2:
                    return (float(parts[0]), float(parts[1]))
            except (ValueError, IndexError):
                pass
        return None

    def get_coordinates_as_geojson(self):
        """Return coordinates as GeoJSON point"""
        coords = self.get_coordinates_as_tuple()
        if coords:
            return {
                'type': 'Point',
                'coordinates': [coords[1], coords[0]]  # GeoJSON uses [lon, lat]
            }
        return None


# Backward-compat alias. Kept so existing code that does
# `from Inventory.models import SHEPCommunity` keeps working through the
# transition. New code should import Community directly. This alias will be
# removed once all callers have been migrated (Phase B follow-up turns).
SHEPCommunity = Community
