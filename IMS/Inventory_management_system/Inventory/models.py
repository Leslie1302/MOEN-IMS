# Inventory/models.py
from django.db import models
from django.contrib.auth.models import User, Group
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.validators import FileExtensionValidator

class ReleaseLetter(models.Model):
    title = models.CharField(max_length=200)
    pdf_file = models.FileField(upload_to='media/')
    upload_time = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

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
    

class ReportSubmission(models.Model):
    # Fields matching BillOfQuantity
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    community = models.CharField(max_length=100, null=True, blank=True)
    consultant = models.CharField(max_length=200)
    contractor = models.CharField(max_length=200)
    package_number = models.CharField(max_length=50)
    material_description = models.CharField(max_length=200)
    item_code = models.CharField(max_length=200)
    contract_quantity = models.FloatField()
    quantity_received = models.FloatField(default=0.0)
    executive_summary = models.TextField(help_text="Provide a summary of the report")
    submission_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('Draft', 'Draft'),
            ('Submitted', 'Submitted'),
            ('Approved', 'Approved'),
            ('Rejected', 'Rejected')
        ],
        default='Draft'
    )
    
    # Add the new PDF field
    monthly_report = models.FileField(
        upload_to='monthly_reports/',
        help_text="Upload monthly report in PDF format",
        validators=[
            FileExtensionValidator(
                allowed_extensions=['pdf'],
                message="Only PDF files are allowed"
            )
        ],
        null=True,
        blank=True
    )
    
    # Foreign keys
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True, blank=True)
    related_boq = models.ForeignKey(
        BillOfQuantity, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='report_submissions'
    )

    class Meta:
        verbose_name_plural = 'report submissions'

    def __str__(self):
        return f"Report for {self.package_number} - {self.submission_date.date()}"

    def create_or_update_boq(self):
        """
        Creates or updates a corresponding BillOfQuantity entry
        """
        if self.status == 'Approved':
            boq, created = BillOfQuantity.objects.get_or_create(
                package_number=self.package_number,
                defaults={
                    'region': self.region,
                    'district': self.district,
                    'community': self.community,
                    'consultant': self.consultant,
                    'contractor': self.contractor,
                    'material_description': self.material_description,
                    'item_code': self.item_code,
                    'contract_quantity': self.contract_quantity,
                    'quantity_received': self.quantity_received,
                    'user': self.user,
                    'group': self.group
                }
            )
            self.related_boq = boq
            self.save()

class MaterialTransport(models.Model):
    # Add STATUS_CHOICES as a class attribute
    STATUS_CHOICES = [
        ('Loaded', 'Loaded'),
        ('En Route', 'En Route'),
        ('On Site', 'On Site')
    ]

    material_order = models.ForeignKey(MaterialOrder, on_delete=models.CASCADE)  
    letter = models.ForeignKey(ReleaseLetter, on_delete=models.CASCADE)  
    material_name = models.CharField(max_length=200)  
    material_code = models.CharField(max_length=200)  
    recipient = models.CharField(max_length=200)  
    consultant = models.CharField(max_length=200) 
    region = models.CharField(max_length=100, blank=True, null=True)  
    district = models.CharField(max_length=100, blank=True, null=True)  
    community = models.CharField(max_length=100, blank=True, null=True)  
    package_number = models.CharField(max_length=50, blank=True, null=True)  
    
    date_transported = models.DateTimeField(auto_now_add=True)
    date_received = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES  
    )

    def save(self, *args, **kwargs):
        """ Auto-populate fields from MaterialOrder when saving """
        if self.material_order:
            self.material_name = self.material_order.name
            self.material_code = self.material_order.code
            self.recipient = self.material_order.contractor
            self.consultant = self.material_order.consultant
            self.region = self.material_order.region
            self.district = self.material_order.district
            self.community = self.material_order.community
            self.package_number = self.material_order.package_number
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Transport: {self.material_name} ({self.material_code})"

    