from django.db import models
import auto_prefetch
from .utils import generate_abbreviation

class SHEPCommunity(auto_prefetch.Model):
    """
    Model for managing SHEP communities and their associated package numbers.
    Used to populate cascading dropdowns in material request forms.
    Abbreviations are auto-generated on save.
    """
    region = models.CharField(max_length=100, help_text="Region name")
    region_abbr = models.CharField(max_length=10, blank=True, editable=False, help_text="Auto-generated region abbreviation")
    district = models.CharField(max_length=100, help_text="District name")
    district_abbr = models.CharField(max_length=10, blank=True, editable=False, help_text="Auto-generated district abbreviation")
    community = models.CharField(max_length=100, help_text="Community name")
    community_abbr = models.CharField(max_length=10, blank=True, editable=False, help_text="Auto-generated community abbreviation")
    package_number = models.CharField(max_length=50, help_text="SHEP package number for this community")
    is_active = models.BooleanField(default=True, help_text="Whether this community is currently active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta(auto_prefetch.Model.Meta):
        verbose_name = 'SHEP Community'
        verbose_name_plural = 'SHEP Communities'
        ordering = ['region', 'district', 'community']
        unique_together = ['region', 'district', 'community', 'package_number']
    
    def save(self, *args, **kwargs):
        """Auto-generate abbreviations on save."""
        self.region_abbr = generate_abbreviation(self.region)
        self.district_abbr = generate_abbreviation(self.district)
        self.community_abbr = generate_abbreviation(self.community)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.region} > {self.district} > {self.community} ({self.package_number})"
