# Inventory/models.py
from django.db import models
from django.contrib.auth.models import User, Group
from django.dispatch import receiver
from django.db.models.signals import post_save

class InventoryItem(models.Model):
    name = models.CharField(max_length=200)
    quantity = models.IntegerField()
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, blank=True, null=True)
    code = models.CharField(max_length=200)
    unit = models.ForeignKey('Unit', on_delete=models.CASCADE) 
    date_created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

class Category(models.Model):
    name = models.CharField(max_length=200)

    class Meta:
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name

class Unit(models.Model):
    name = models.CharField(max_length=200)

    class Meta:
        verbose_name_plural = 'units'

    def __str__(self):
        return self.name

def get_default_group():
    return Group.objects.get(name="default").id

def get_default_unit():
    return Unit.objects.first().id

class MaterialOrder(models.Model):
    name = models.CharField(max_length=200)
    quantity = models.IntegerField()  # Total requested/received quantity
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, blank=True, null=True)
    code = models.CharField(max_length=200, blank=False, default="Enter code")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    date_requested = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, blank=True, null=True)
    
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Completed', 'Completed'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Pending'
    )
    
    REQUEST_TYPE_CHOICES = [
        ('Release', 'Release Request'),
        ('Receipt', 'Receipt Request'),
    ]
    request_type = models.CharField(
        max_length=20,
        choices=REQUEST_TYPE_CHOICES,
        default='Release'
    )
    
    processed_quantity = models.IntegerField(default=0)
    remaining_quantity = models.IntegerField(default=0)
    region = models.CharField(max_length=100, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    community = models.CharField(max_length=100, blank=True, null=True)
    consultant = models.CharField(max_length=200, blank=True, null=True)
    contractor = models.CharField(max_length=200, blank=True, null=True)
    package_number = models.CharField(max_length=50, blank=True, null=True)
    # New field
    last_updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_material_orders')

    class Meta:
        verbose_name_plural = 'orders'

    def __str__(self):
        return f"{self.name} - {self.quantity} ({self.request_type})"

    def save(self, *args, **kwargs):
        if self.pk is None:  # Only set on creation
            self.remaining_quantity = self.quantity
        super().save(*args, **kwargs)


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} Profile"

    @property
    def profile_picture_url(self):
        if self.profile_picture:
            return self.profile_picture.url
        return '/static/images/default_profile.png'


    
class BillOfQuantity(models.Model):
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    community = models.CharField(max_length=100, null=True, blank=True)
    consultant = models.CharField(max_length=200)
    contractor = models.CharField(max_length=200)
    package_number = models.CharField(max_length=50)
    material_description = models.CharField(max_length=200)
    item_code = models.CharField(max_length=200)
    contract_quantity = models.FloatField()  # Changed to FloatField
    quantity_received = models.FloatField(default=0.0)  # Changed to FloatField
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'bills of quantity'

    def __str__(self):
        return f"{self.material_description} - {self.package_number}"

    @property
    def balance(self):
        return self.contract_quantity - self.quantity_received
    

class MaterialOrderAudit(models.Model):
    order = models.ForeignKey(MaterialOrder, on_delete=models.CASCADE)
    action = models.CharField(max_length=100)
    performed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} on {self.order.id} by {self.performed_by}"