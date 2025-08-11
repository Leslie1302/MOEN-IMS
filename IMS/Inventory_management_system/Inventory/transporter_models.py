from django.db import models
from django.contrib.auth.models import User

class Transporter(models.Model):
    """
    Model to store transporter company information.
    """
    name = models.CharField(max_length=200, help_text="Name of the transport company")
    contact_person = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    date_added = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True, help_text="Any additional notes about the transporter")
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Transporter'
        verbose_name_plural = 'Transporters'
    
    def __str__(self):
        return self.name

class TransportVehicle(models.Model):
    """
    Model to store vehicle information for transporters.
    """
    VEHICLE_TYPES = [
        ('Truck', 'Truck'),
        ('Van', 'Van'),
        ('Trailer', 'Trailer'),
        ('Pickup', 'Pickup Truck'),
        ('Other', 'Other'),
    ]
    
    transporter = models.ForeignKey(Transporter, on_delete=models.CASCADE, related_name='vehicles')
    registration_number = models.CharField(max_length=50, unique=True)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPES, default='Truck')
    capacity = models.CharField(max_length=100, help_text="E.g., 10 tons, 20ft container, etc.")
    is_active = models.BooleanField(default=True)
    date_added = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['transporter__name', 'registration_number']
        verbose_name = 'Transport Vehicle'
        verbose_name_plural = 'Transport Vehicles'
    
    def __str__(self):
        return f"{self.registration_number} ({self.transporter.name})"
