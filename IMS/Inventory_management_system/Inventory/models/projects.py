from django.db import models
import auto_prefetch
from django.contrib.auth.models import User, Group
from .inventory import Warehouse

class BillOfQuantity(auto_prefetch.Model):
    """Bill of Quantity model - tracks material quantities by community"""
    region = models.CharField(max_length=100, db_index=True)
    district = models.CharField(max_length=100, db_index=True)
    community = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    consultant = models.CharField(max_length=200)
    contractor = models.CharField(max_length=200)
    package_number = models.CharField(max_length=50, db_index=True)
    phase = models.CharField(max_length=50, blank=True, null=True, help_text="SHEP Phase (e.g., SHEP-4)")
    # Project segregation — the BoQ is the spine the whole system rolls up
    # against, so it needs to carry the project type it belongs to. Mirrors
    # the ProjectType registry the request form uses.
    project_type = models.CharField(
        max_length=50,
        db_index=True,
        default='SHEP',
        help_text=(
            'Project type this BoQ line belongs to. Mirrors the ProjectType '
            'registry the request form uses so the BoQ rolls up correctly '
            'under the right programme.'
        ),
    )
    material_description = models.CharField(max_length=200)
    item_code = models.CharField(max_length=200, db_index=True)

    # Explicit electrical classification of this BoQ line. Replaces the
    # keyword-only guess (_categorise_boq_material) used by the community
    # breakdown: that heuristic now only fills the blank as a *suggestion*,
    # and this field is authoritative when set. Backfilled from the heuristic
    # in migration. Read by the one-time "pull targets from BoQ" action that
    # seeds community planned-quantity targets; otherwise the BoQ and the
    # progress tracker stay decoupled.
    VOLTAGE_CLASS_CHOICES = [
        ('HT',    'HT (high tension)'),
        ('LV',    'LV (low tension)'),
        ('XFMR',  'Transformer'),
        ('METER', 'Meter / service connection'),
        ('OTHER', 'Other / non-line'),
    ]
    voltage_class = models.CharField(
        max_length=10,
        choices=VOLTAGE_CLASS_CHOICES,
        blank=True,
        default='',
        db_index=True,
        help_text=(
            'Explicit HT/LV/Transformer/Meter classification. Authoritative '
            'when set; the keyword heuristic only pre-fills a suggestion. '
            'Used to seed community progress targets at setup.'
        ),
    )

    contract_quantity = models.FloatField()
    quantity_received = models.FloatField(default=0.0)
    warehouse = auto_prefetch.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text="Warehouse associated with this BOQ item"
    )
    user = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    group = auto_prefetch.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta(auto_prefetch.Model.Meta):
        verbose_name_plural = 'bills of quantity'

    def __str__(self):
        return f"{self.material_description} - {self.package_number}"

    @property
    def balance(self):
        return self.contract_quantity - self.quantity_received
    
    @property
    def has_overissuance(self):
        """Check if this BoQ item has overissuance (negative balance)"""
        return self.balance < 0
    
    @property
    def overissuance_amount(self):
        """Return the absolute value of overissuance if negative balance exists"""
        return abs(self.balance) if self.has_overissuance else 0


class Project(auto_prefetch.Model):
    """
    Main project model that represents a construction/infrastructure project
    """
    PROJECT_STATUS_CHOICES = [
        ('Planning', 'Planning'),
        ('Active', 'Active'),
        ('On Hold', 'On Hold'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]
    
    PROJECT_TYPE_CHOICES = [
        ('SHEP', 'SHEP'),
        ('Turnkey', 'Turnkey'),
        ('China Water', 'China Water'),
        ('Other Electrification', 'Other Electrification'),
    ]
    
    name = models.CharField(max_length=200, help_text="Project name")
    code = models.CharField(max_length=50, unique=True, help_text="Unique project code")
    description = models.TextField(help_text="Detailed project description")
    project_type = models.CharField(max_length=50, choices=PROJECT_TYPE_CHOICES, default='SHEP')
    phase = models.CharField(max_length=50, blank=True, null=True, help_text="SHEP Phase (e.g., SHEP-4, Phase 2, etc.)")
    status = models.CharField(max_length=50, choices=PROJECT_STATUS_CHOICES, default='Planning')
    
    # Project management details
    project_manager = auto_prefetch.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='managed_projects',
        help_text="User responsible for managing this project"
    )
    consultant = models.CharField(max_length=200, help_text="Primary consultant for the project")
    contractor = models.CharField(max_length=200, help_text="Primary contractor for the project")
    
    # Timeline
    start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    
    # Budget
    total_budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    spent_budget = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Administrative
    created_by = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-created_at']
        permissions = [
            ('can_manage_projects', 'Can manage projects'),
            ('can_view_all_projects', 'Can view all projects'),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class ProjectSite(auto_prefetch.Model):
    """
    Represents individual sites within a project.
    Enhanced with geospatial fields for Ghana Map tracking (Phase 2).
    """
    SITE_STATUS_CHOICES = [
        ('Planned', 'Planned'),
        ('Active', 'Active'),
        ('Completed', 'Completed'),
        ('On Hold', 'On Hold'),
    ]

    project = auto_prefetch.ForeignKey(Project, on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=200, help_text="Site name or identifier")
    code = models.CharField(max_length=50, help_text="Site code")

    # Location details
    region = models.CharField(max_length=100, db_index=True)
    district = models.CharField(max_length=100, db_index=True)
    community = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    gps_coordinates = models.CharField(max_length=100, null=True, blank=True, help_text="GPS coordinates if available")

    # Geospatial fields (Phase 2)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Site latitude coordinate"
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="Site longitude coordinate"
    )

    # Site management
    site_supervisor = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supervised_sites',
        help_text="User supervising this site"
    )
    # ``status`` is now a *material*-completion proxy -- driven by the BoQ
    # signal in Inventory.signals.sync_project_site_from_boq. Before Phase
    # B6 it was the only completion field, conflating "all materials
    # delivered" with "site energised". The new ``works_status`` field
    # (below) captures the works-on-the-ground view; templates and reports
    # that need the access-rate-relevant signal should prefer it.
    status = models.CharField(max_length=50, choices=SITE_STATUS_CHOICES, default='Planned', db_index=True)

    WORKS_STATUS_CHOICES = [
        ('Planned',      'Planned'),
        ('In Progress',  'In Progress'),
        ('Energised',    'Energised'),     # meters installed + verified
        ('Commissioned', 'Commissioned'),  # signed off as fully handed over
    ]
    works_status = models.CharField(
        max_length=20, choices=WORKS_STATUS_CHOICES,
        default='Planned', db_index=True,
        help_text=(
            'Physical-works progress. Two write paths feed this: '
            '(1) consultants update it from the Site Progress page; '
            '(2) verified MeterInstallation rows flip it to "Energised" '
            'when the access-rate-from-meters flow is enabled. '
            'Use this for access-rate roll-ups; use ``status`` only for '
            'material-flow views.'
        ),
    )

    # ── Consultant progress reporting (interim until Energy Commission engagement) ──
    # Free-text % complete that the field consultant updates as works
    # progress at the site. The Ghana map's headline access rate reads
    # this (averaged across sites) rather than the meter-driven formula
    # until the EC engagement decides on the canonical methodology.
    progress_percent = models.PositiveSmallIntegerField(
        default=0,
        help_text=(
            'Consultant-reported % complete (0-100). Updated from the Site '
            'Progress page. Drives the Ghana map headline in the interim.'
        ),
    )
    progress_notes = models.TextField(
        blank=True,
        help_text='Brief context from the consultant. Shown on the map drill-down.',
    )
    progress_updated_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Stamped automatically when progress_percent or works_status changes.',
    )
    progress_updated_by = auto_prefetch.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='site_progress_updates',
        help_text='Last user who updated the progress record.',
    )

    # ── Materials used to progress the works (cumulative, as-of latest update) ──
    # Quantified alongside works_status so a site's progress is backed by
    # physical counts, not just a percentage. Updated from the Site Progress
    # page. Meters additionally drive the national access rate: when the
    # meter totals below increase, the Site Progress save creates a verified
    # MeterInstallation row for the delta, which the access-rate formula reads.
    meters_1ph_installed = models.PositiveIntegerField(
        default=0,
        help_text='Single-phase meters installed at this site to date. '
                  'Increasing this logs the difference as a MeterInstallation '
                  'so the national access rate rises.',
    )
    meters_3ph_installed = models.PositiveIntegerField(
        default=0,
        help_text='Three-phase meters installed at this site to date. '
                  'Increasing this logs the difference as a MeterInstallation '
                  'so the national access rate rises.',
    )
    poles_erected = models.PositiveIntegerField(
        default=0,
        help_text='Poles erected at this site to date.',
    )
    conductor_laid_m = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Conductor / cable strung at this site to date, in metres.',
    )
    transformers_installed = models.PositiveIntegerField(
        default=0,
        help_text='Distribution transformers installed at this site to date.',
    )
    transformers_commissioned = models.PositiveIntegerField(
        default=0,
        help_text='Distribution transformers commissioned (energised and '
                  'handed over) at this site to date.',
    )

    # ── Granular pole lifecycle, split by voltage class (cumulative) ──
    # The works are credited in stages: a pole is erected/planted, then
    # dressed (cross-arms/insulators fitted), then strung (conductor run).
    # Captured per HT/LV class so the 5-stage community completion can be
    # computed against the frozen BoQ-seeded targets. The legacy
    # ``poles_erected`` / ``conductor_laid_m`` totals above are retained and
    # kept in sync as the sum of the HT+LV figures here.
    ht_poles_erected = models.PositiveIntegerField(
        default=0, help_text='HT poles erected/planted at this site to date.')
    lv_poles_erected = models.PositiveIntegerField(
        default=0, help_text='LV poles erected/planted at this site to date.')
    ht_poles_dressed = models.PositiveIntegerField(
        default=0, help_text='HT poles dressed (hardware fitted) to date.')
    lv_poles_dressed = models.PositiveIntegerField(
        default=0, help_text='LV poles dressed (hardware fitted) to date.')
    ht_poles_strung = models.PositiveIntegerField(
        default=0, help_text='HT poles strung (conductor run) to date.')
    lv_poles_strung = models.PositiveIntegerField(
        default=0, help_text='LV poles strung (conductor run) to date.')
    ht_conductor_strung_m = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='HT conductor used for stringing to date, in metres.')
    lv_conductor_strung_m = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='LV conductor used for stringing to date, in metres.')

    # Timeline
    start_date = models.DateField(null=True, blank=True)
    planned_completion_date = models.DateField(null=True, blank=True)
    actual_completion_date = models.DateField(null=True, blank=True)

    # Administrative
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['project', 'name']
        unique_together = ['project', 'code']
        indexes = [
            models.Index(fields=['region', 'district']),
            models.Index(fields=['region', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['region', 'works_status']),
        ]

    def __str__(self):
        return f"{self.project.code} - {self.name}"

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

    @property
    def is_completed(self):
        """Check if site is completed"""
        return self.status == 'Completed'

    @property
    def completion_percentage(self):
        """Calculate estimated completion percentage based on status"""
        status_percentages = {
            'Planned': 0,
            'Active': 50,
            'Completed': 100,
            'On Hold': 25,
        }
        return status_percentages.get(self.status, 0)


class ProjectPhase(auto_prefetch.Model):
    """
    Represents different phases within a project
    """
    PHASE_STATUS_CHOICES = [
        ('Not Started', 'Not Started'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Delayed', 'Delayed'),
    ]
    
    project = auto_prefetch.ForeignKey(Project, on_delete=models.CASCADE, related_name='phases')
    name = models.CharField(max_length=200, help_text="Phase name")
    description = models.TextField(help_text="Phase description")
    phase_order = models.PositiveIntegerField(help_text="Order of this phase in the project")
    
    status = models.CharField(max_length=50, choices=PHASE_STATUS_CHOICES, default='Not Started')
    
    # Timeline
    planned_start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    actual_start_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    
    # Progress tracking
    completion_percentage = models.PositiveIntegerField(default=0, help_text="Completion percentage (0-100)")
    
    # Administrative
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['project', 'phase_order']
        unique_together = ['project', 'phase_order']
    
    def __str__(self):
        return f"{self.project.code} - Phase {self.phase_order}: {self.name}"
