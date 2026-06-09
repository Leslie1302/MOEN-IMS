"""
Geospatial models for Ghana administrative divisions and project locations.
Designed for SQLite now; ready to migrate to PostgreSQL + PostGIS later.
"""

from django.db import models
import auto_prefetch
from django.contrib.auth.models import User
from .shep import Community  # Import existing Community model


class Region(auto_prefetch.Model):
    """Ghana's 16 administrative regions"""
    name = models.CharField(max_length=100, unique=True, db_index=True)
    code = models.CharField(max_length=10, unique=True)

    # PostGIS polygon boundary (optional, for advanced geospatial queries)
    # When using PostGIS, replace geom_json with PolygonField
    geom_json = models.JSONField(null=True, blank=True, help_text="GeoJSON boundary (used with SQLite)")

    # Administrative fields
    population = models.IntegerField(null=True, blank=True)
    capital = models.CharField(max_length=100, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['name']
        verbose_name = 'Region'
        verbose_name_plural = 'Regions'

    def __str__(self):
        return f"{self.name} ({self.code})"


class District(auto_prefetch.Model):
    """Districts within Ghana's regions"""
    region = auto_prefetch.ForeignKey(Region, on_delete=models.CASCADE, related_name='districts')
    name = models.CharField(max_length=100, db_index=True)
    code = models.CharField(max_length=10)  # Unique per region, not globally

    # PostGIS polygon boundary
    geom_json = models.JSONField(null=True, blank=True, help_text="GeoJSON boundary")

    # Administrative fields
    capital = models.CharField(max_length=100, null=True, blank=True)
    population = models.IntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['region', 'name']
        # A district name and a district code are each unique within a region.
        unique_together = [['region', 'name'], ['region', 'code']]
        verbose_name = 'District'
        verbose_name_plural = 'Districts'

    def __str__(self):
        return f"{self.name} ({self.code})"


class Package(auto_prefetch.Model):
    """Project packages linked to regions and districts"""
    name = models.CharField(max_length=200, unique=True, db_index=True)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)

    # Geographic scope
    region = auto_prefetch.ForeignKey(Region, on_delete=models.PROTECT)
    districts = models.ManyToManyField(
        District,
        related_name='packages',
        help_text="Districts covered by this package"
    )

    # Related communities (the actual implementation sites)
    communities = models.ManyToManyField(
        Community,
        related_name='packages',
        help_text="Communities where this package will be implemented"
    )

    # Package details
    phase = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        help_text="SHEP Phase or other phase identifier (e.g., SHEP-4, Phase 2)"
    )

    project_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        choices=[
            ('SHEP', 'SHEP'),
            ('Turnkey', 'Turnkey'),
            ('China Water', 'China Water'),
            ('Other Electrification', 'Other Electrification'),
            ('Other', 'Other'),
        ]
    )

    budget = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=50,
        default='Planning',
        choices=[
            ('Planning', 'Planning'),
            ('Active', 'Active'),
            ('Completed', 'Completed'),
            ('On Hold', 'On Hold'),
        ]
    )

    # Timeline
    start_date = models.DateField(null=True, blank=True)
    planned_end_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_packages')

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-created_at']
        verbose_name = 'Package'
        verbose_name_plural = 'Packages'
        indexes = [
            models.Index(fields=['phase', 'status']),
            models.Index(fields=['region', 'status']),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def community_count(self):
        """Total communities in this package"""
        return self.communities.count()
