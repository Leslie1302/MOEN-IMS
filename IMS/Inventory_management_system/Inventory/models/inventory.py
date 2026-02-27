from django.db import models
import auto_prefetch
from django.contrib.auth.models import User, Group
from django.utils import timezone

class Warehouse(auto_prefetch.Model):
    """
    Model for representing warehouses where inventory items are stored.
    """
    name = models.CharField(max_length=200, help_text="Name of the warehouse")
    code = models.CharField(max_length=50, unique=True, help_text="Unique warehouse code")
    location = models.CharField(max_length=500, help_text="Physical address or location description")
    contact_person = models.CharField(max_length=200, blank=True, null=True, help_text="Primary contact person")
    contact_phone = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    contact_email = models.EmailField(blank=True, null=True, help_text="Contact email address")
    is_active = models.BooleanField(default=True, help_text="Whether this warehouse is currently active")
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the warehouse")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['name']
        verbose_name = 'Warehouse'
        verbose_name_plural = 'Warehouses'

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('warehouse_detail', kwargs={'pk': self.pk})


class Category(auto_prefetch.Model):
    name = models.CharField(max_length=200)

    class Meta(auto_prefetch.Model.Meta):
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Unit(auto_prefetch.Model):
    name = models.CharField(max_length=200)

    class Meta(auto_prefetch.Model.Meta):
        verbose_name_plural = 'units'

    def __str__(self):
        return self.name


def get_default_group():
    try:
        return Group.objects.get(name="default").id
    except Group.DoesNotExist:
        return None

def get_default_unit():
    try:
        return Unit.objects.first().id
    except (Unit.DoesNotExist, AttributeError):
        return None


class InventoryItem(auto_prefetch.Model):
    name = models.CharField(max_length=200)
    quantity = models.IntegerField()
    category = auto_prefetch.ForeignKey('Category', on_delete=models.SET_NULL, blank=True, null=True)
    code = models.CharField(max_length=200, help_text="Material code")
    unit = auto_prefetch.ForeignKey('Unit', on_delete=models.CASCADE) 
    date_created = models.DateTimeField(auto_now_add=True)
    user = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    group = auto_prefetch.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    warehouse = auto_prefetch.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, help_text="Warehouse where this item is stored")

    class Meta(auto_prefetch.Model.Meta):
        unique_together = ['code', 'warehouse']
        ordering = ['name']

    def __str__(self):
        return self.name


class ObsoleteMaterial(auto_prefetch.Model):
    """
    Model for tracking obsolete materials across all stores/warehouses.
    Used to register materials that are no longer in use or need to be disposed of.
    """
    STATUS_CHOICES = [
        ('Registered', 'Registered'),
        ('Pending Review', 'Pending Review'),
        ('Approved for Disposal', 'Approved for Disposal'),
        ('Disposed', 'Disposed'),
        ('Repurposed', 'Repurposed'),
        ('Returned to Supplier', 'Returned to Supplier'),
    ]
    
    # Material Information (linked to inventory item)
    material = auto_prefetch.ForeignKey(
        InventoryItem, 
        on_delete=models.SET_NULL, 
        null=True,
        help_text="Select the material from inventory"
    )
    
    # Auto-populated fields (from material selection)
    material_name = models.CharField(max_length=200, help_text="Material name")
    material_code = models.CharField(max_length=200, help_text="Material code")
    category = models.CharField(max_length=200, blank=True, null=True, help_text="Material category")
    unit = models.CharField(max_length=50, help_text="Unit of measurement")
    
    # Quantity and warehouse
    quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Quantity of obsolete material"
    )
    warehouse = auto_prefetch.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        help_text="Warehouse where material is stored"
    )
    
    # Serial numbers for specific categories (Energy Meters, Transformers)
    serial_numbers = models.TextField(
        blank=True, 
        null=True,
        help_text="Serial numbers (for Energy Meters and Transformers). Enter one per line or comma-separated."
    )
    
    # Obsolescence details
    reason_for_obsolescence = models.TextField(
        help_text="Explain why this material is obsolete (e.g., damaged, expired, outdated, excess stock)"
    )
    date_marked_obsolete = models.DateField(
        default=timezone.now,
        help_text="Date when material was marked as obsolete"
    )
    
    # Status and tracking
    status = models.CharField(
        max_length=50, 
        choices=STATUS_CHOICES, 
        default='Registered',
        help_text="Current status of the obsolete material"
    )
    
    # Additional information
    estimated_value = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Estimated current value of the obsolete material"
    )
    
    disposal_method = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Proposed or actual method of disposal"
    )
    
    disposal_date = models.DateField(
        blank=True,
        null=True,
        help_text="Date when material was disposed"
    )
    
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional notes or comments"
    )
    
    # Audit fields
    registered_by = auto_prefetch.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        related_name='obsolete_materials_registered',
        help_text="User who registered this obsolete material"
    )
    reviewed_by = auto_prefetch.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True,
        blank=True,
        related_name='obsolete_materials_reviewed',
        help_text="User who reviewed this registration"
    )
    review_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Date when the registration was reviewed"
    )
    review_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Notes from the review process"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-date_marked_obsolete', '-created_at']
        verbose_name = 'Obsolete Material'
        verbose_name_plural = 'Obsolete Materials'
        permissions = [
            ('can_register_obsolete_material', 'Can register obsolete materials'),
            ('can_review_obsolete_material', 'Can review obsolete materials'),
            ('can_approve_disposal', 'Can approve material disposal'),
        ]
    
    def __str__(self):
        return f"{self.material_name} ({self.material_code}) - {self.quantity} {self.unit} - {self.status}"
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('obsolete_material_detail', kwargs={'pk': self.pk})
    
    def requires_serial_numbers(self):
        """Check if this material category requires serial numbers"""
        if self.category:
            category_lower = self.category.lower()
            return 'energy meter' in category_lower or 'transformer' in category_lower
        return False
    
    def approve_for_disposal(self, user, notes=None):
        """Approve material for disposal"""
        self.status = 'Approved for Disposal'
        self.reviewed_by = user
        self.review_date = timezone.now()
        if notes:
            self.review_notes = notes
        self.save()
    
    def mark_as_disposed(self, disposal_method, disposal_date=None, notes=None):
        """Mark material as disposed"""
        self.status = 'Disposed'
        self.disposal_method = disposal_method
        self.disposal_date = disposal_date or timezone.now().date()
        if notes:
            if self.notes:
                self.notes += f"\n\nDisposal: {notes}"
            else:
                self.notes = notes
        self.save()
