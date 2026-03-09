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
    material_description = models.CharField(max_length=200)
    item_code = models.CharField(max_length=200, db_index=True)
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
    Represents individual sites within a project
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
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    community = models.CharField(max_length=100, null=True, blank=True)
    gps_coordinates = models.CharField(max_length=100, null=True, blank=True, help_text="GPS coordinates if available")
    
    # Site management
    site_supervisor = auto_prefetch.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='supervised_sites',
        help_text="User supervising this site"
    )
    status = models.CharField(max_length=50, choices=SITE_STATUS_CHOICES, default='Planned')
    
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
    
    def __str__(self):
        return f"{self.project.code} - {self.name}"


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
