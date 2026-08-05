"""Operational areas — groups of regions that share a consultant + officer team.

Used to segregate the region/area data views: a scoped user (consultant or
schedule officer) sees only the communities/BoQ/progress in their area's
regions. Management and superusers are never scoped.
"""

from django.db import models


class Area(models.Model):
    """A named operational area covering one or more whole regions."""

    name = models.CharField(max_length=100, unique=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'area'
        verbose_name_plural = 'areas'

    def __str__(self):
        return self.name

    @property
    def region_names(self):
        return list(self.regions.values_list('region', flat=True))


class AreaRegion(models.Model):
    """One region name belonging to an area.

    Stored as the region string exactly as it appears on BoQ / ProjectSite /
    Community rows, so scope filters can match with ``region__iexact``.
    """

    area = models.ForeignKey(Area, on_delete=models.CASCADE, related_name='regions')
    region = models.CharField(max_length=100, db_index=True)

    class Meta:
        unique_together = ('area', 'region')
        ordering = ['region']

    def __str__(self):
        return f"{self.area.name} · {self.region}"
