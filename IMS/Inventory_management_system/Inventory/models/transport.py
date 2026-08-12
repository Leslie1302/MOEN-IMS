from django.db import models
import auto_prefetch
from django.contrib.auth.models import User
from django.utils import timezone
from .inventory import Warehouse
from .orders import MaterialOrder

class MaterialTransport(auto_prefetch.Model):
    """
    Model for tracking transportation of materials from request to delivery.
    Links the material order to the transporter and driver.
    """
    material_order = auto_prefetch.ForeignKey(
        MaterialOrder,
        on_delete=models.CASCADE,
        related_name='transports'
    )
    transporter = auto_prefetch.ForeignKey(
        'Transporter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    vehicle = auto_prefetch.ForeignKey(
        'TransportVehicle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    driver_name = models.CharField(max_length=200, default='Unknown')
    driver_phone = models.CharField(max_length=20, default='Unknown')
    waybill_number = models.CharField(max_length=100, default='Unknown')
    waybill_download_count = models.IntegerField(
        default=0,
        help_text="Number of times this waybill has been downloaded"
    )
    
    # Quantity tracking
    quantity = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Quantity being transported in this shipment"
    )
    
    # Status tracking
    # Phase F.5: 'Awaiting Transporter' added so we can auto-create a placeholder
    # row when a MaterialOrder reaches Completed, surfacing it on the Transport
    # Officer dashboard for assignment.
    STATUS_CHOICES = [
        ('Awaiting Transporter', 'Awaiting Transporter Assignment'),
        ('Loaded', 'Loaded / Ready'),
        ('In Transit', 'In Transit'),
        ('Delivered', 'Delivered'),
        ('Issue', 'Issue Reported')
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Loaded')
    
    # Dates
    date_dispatched = models.DateTimeField(default=timezone.now)
    date_delivered = models.DateTimeField(null=True, blank=True)
    
    # Additional info
    notes = models.TextField(blank=True, null=True)
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-date_dispatched']
        verbose_name = 'Material Transport'
        verbose_name_plural = 'Material Transports'

    def __str__(self):
        return f"Transport: {self.material_order.name} - {self.waybill_number}"

    @property
    def material_name(self):
        return self.material_order.name

    @property
    def material_code(self):
        return self.material_order.code if self.material_order else None

    @property
    def unit(self):
        return self.material_order.unit

    @property
    def project(self):
        return self.material_order.project_name

    @property
    def warehouse(self):
        return self.material_order.warehouse if self.material_order else None

    @property
    def consultant(self):
        return self.material_order.consultant if self.material_order else None

    @property
    def region(self):
        return self.material_order.region if self.material_order else None

    @property
    def district(self):
        return self.material_order.district if self.material_order else None

    @property
    def community(self):
        return self.material_order.community if self.material_order else None

    @property
    def package_number(self):
        return self.material_order.package_number if self.material_order else None

    @property
    def created_by(self):
        return self.material_order.created_by if self.material_order else None

    @property
    def assigned_by(self):
        return self.material_order.assigned_by if self.material_order else None

    @property
    def assigned_at(self):
        return self.material_order.assigned_at if self.material_order else None

    @property
    def processed_by(self):
        return self.material_order.processed_by if self.material_order else None

    @property
    def processed_at(self):
        return self.material_order.processed_at if self.material_order else None

    @property
    def recipient(self):
        receipt = getattr(self, "site_receipt", None)
        if receipt and receipt.received_by:
            return receipt.received_by.get_full_name() or receipt.received_by.get_username()
        return None

    @property
    def destination_contact(self):
        warehouse = self.warehouse
        return getattr(warehouse, "contact_person", None) if warehouse else None

    @property
    def destination_phone(self):
        warehouse = self.warehouse
        return getattr(warehouse, "contact_phone", None) if warehouse else None

    @property
    def vehicle_registration_number(self):
        return self.vehicle.registration_number if self.vehicle else None

    @property
    def waybill_scan(self):
        receipt = getattr(self, "site_receipt", None)
        return receipt.waybill_pdf if receipt else None
        
    @property
    def delivery_location(self):
        """Return the destination (community/district/region)"""
        components = []
        if self.material_order.community:
            components.append(self.material_order.community)
        if self.material_order.district:
            components.append(self.material_order.district)
        if self.material_order.region:
            components.append(self.material_order.region)
        return ", ".join(components) if components else "Unknown Location"

    def save(self, *args, **kwargs):
        """Update MaterialOrder status when transport is saved"""
        is_new = self.pk is None
        
        # Ensure quantity doesn't exceed remaining order quantity for new records
        if is_new and self.material_order:
            remaining = self.material_order.remaining_transport_quantity
            if self.quantity is not None and remaining is not None and self.quantity > remaining:
                # We'll allow it but log a warning/error or just cap it? 
                # For now, just let it pass but maybe validate in form
                pass
        
        super().save(*args, **kwargs)
        
        # Update MaterialOrder status based on transport status
        if self.material_order:
            order = self.material_order
            
            # If any transport is in transit, order is in transit
            if self.status == 'In Transit':
                if order.status != 'In Transit':
                    order.status = 'In Transit'
                    order.save()
            
            # If all quantity delivered, order is delivered
            # (Note: simpler logic, might need aggregation for partials)
