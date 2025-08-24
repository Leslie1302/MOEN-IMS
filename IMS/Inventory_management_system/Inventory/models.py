# Inventory/models.py
from django.db import models
from django.contrib.auth.models import User, Group
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.validators import FileExtensionValidator
from django.utils import timezone
import uuid

# Import transporter models
from .transporter_models import Transporter, TransportVehicle

class Warehouse(models.Model):
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

    class Meta:
        ordering = ['name']
        verbose_name = 'Warehouse'
        verbose_name_plural = 'Warehouses'

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('warehouse_detail', kwargs={'pk': self.pk})

class ReleaseLetter(models.Model):
    """
    Model for storing release letters that authorize material releases.
    Each letter is linked to a specific material order.
    """
    request_code = models.CharField(
        max_length=50,
        db_index=True,
        help_text="The request code that identifies the material request(s) this letter authorizes"
    )
    title = models.CharField(
        max_length=200,
        help_text="A descriptive title for this release letter"
    )
    pdf_file = models.FileField(
        upload_to='release_letters/%Y/%m/%d/',
        help_text="The signed release letter in PDF format"
    )
    uploaded_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_release_letters',
        help_text="User who uploaded this letter"
    )
    upload_time = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(
        blank=True,
        help_text="Any additional notes or comments about this release letter"
    )

    class Meta:
        ordering = ['-upload_time']
        verbose_name = 'Release Letter'
        verbose_name_plural = 'Release Letters'
        unique_together = ['request_code', 'title']  # Prevent duplicate letters for same request
        permissions = [
            ('can_upload_release_letter', 'Can upload release letters'),
        ]
        
    def get_related_orders(self):
        """Get all material orders associated with this request code."""
        return MaterialOrder.objects.filter(request_code=self.request_code)

    def __str__(self):
        return f"{self.title} - {self.request_code}"

class InventoryItem(models.Model):
    name = models.CharField(max_length=200)
    quantity = models.IntegerField()
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, blank=True, null=True)
    code = models.CharField(max_length=200)
    unit = models.ForeignKey('Unit', on_delete=models.CASCADE) 
    date_created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, help_text="Warehouse where this item is stored")

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
    """
    Model representing a material order request (release or receipt).
    """
    # Basic information
    name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)  # Changed to DecimalField for precision
    category = models.ForeignKey('Category', on_delete=models.SET_NULL, blank=True, null=True)
    code = models.CharField(max_length=200, blank=False, default="Enter code")
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE)
    
    # Request metadata
    date_requested = models.DateTimeField(auto_now_add=True)
    date_required = models.DateField(null=True, blank=True)
    priority = models.CharField(
        max_length=20,
        choices=[
            ('Low', 'Low'),
            ('Medium', 'Medium'),
            ('High', 'High'),
            ('Urgent', 'Urgent')
        ],
        default='Medium'
    )
    
    # User and group associations
    user = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='material_orders_created'
    )
    group = models.ForeignKey(
        Group, 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True,
        related_name='material_orders'
    )
    warehouse = models.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text="Warehouse associated with this order"
    )
    
    # Request tracking
    request_code = models.CharField(
        max_length=50, 
        blank=True, 
        null=True, 
        unique=True, 
        db_index=True,
        help_text="Unique code for tracking this request"
    )
    
    # Status tracking
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Pending', 'Pending Approval'),
        ('Approved', 'Approved'),
        ('In Progress', 'In Progress'),
        ('Partially Fulfilled', 'Partially Fulfilled'),
        ('Ready for Pickup', 'Ready for Pickup'),
        ('In Transit', 'In Transit'),
        ('Delivered', 'Delivered'),
        ('Completed', 'Completed'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled')
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Draft'
    )
    
    # Processing tracking
    processed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='material_orders_processed',
        help_text="User who processed the quantity for release"
    )
    processed_at = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text="When the quantity was processed"
    )
    
    # Request type
    REQUEST_TYPE_CHOICES = [
        ('Release', 'Release Request'),
        ('Receipt', 'Receipt Request'),
    ]
    request_type = models.CharField(
        max_length=20,
        choices=REQUEST_TYPE_CHOICES,
        default='Release'
    )
    
    # Quantity tracking
    processed_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remaining_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Location information
    region = models.CharField(max_length=100, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    community = models.CharField(max_length=100, blank=True, null=True)
    
    # Project information
    consultant = models.CharField(max_length=200, blank=True, null=True)
    contractor = models.CharField(max_length=200, blank=True, null=True)
    package_number = models.CharField(max_length=50, blank=True, null=True)
    project_name = models.CharField(max_length=200, blank=True, null=True)
    
    # Additional metadata
    notes = models.TextField(blank=True, null=True, help_text="Additional notes or instructions")
    is_urgent = models.BooleanField(default=False)
    
    # Relationships
    release_letter = models.ForeignKey(
        'ReleaseLetter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='material_orders',
        help_text="The release letter that authorizes this material order"
    )
    
    # Audit fields
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_material_orders',
        help_text="User who created this order"
    )
    last_updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='updated_material_orders',
        help_text="User who last updated this order"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Material Order'
        verbose_name_plural = 'Material Orders'
        ordering = ['-date_requested']
        permissions = [
            ('can_approve_order', 'Can approve material orders'),
            ('can_reject_order', 'Can reject material orders'),
            ('can_export_orders', 'Can export material orders'),
        ]

    def __str__(self):
        return f"{self.name} - {self.quantity} {self.unit} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        """Custom save method to handle request code generation and status updates."""
        is_new = self.pk is None
        
        # Set created_by if this is a new record and not provided
        if is_new and not self.created_by_id and hasattr(self, '_current_user'):
            self.created_by = self._current_user
        
        # Set last_updated_by if user is available
        if hasattr(self, '_current_user'):
            self.last_updated_by = self._current_user
        
        # Generate request code for new orders
        if is_new and not self.request_code:
            # date_requested may be None before first save when using auto_now_add
            dt = self.date_requested or timezone.now()
            date_str = dt.strftime('%Y%m%d')
            unique_id = uuid.uuid4().hex[:6].upper()
            self.request_code = f"REQ-{date_str}-{unique_id}"
        
        # Always compute remaining and status based on quantity and processed_quantity
        try:
            q = float(self.quantity or 0)
            p = float(self.processed_quantity or 0)
            # Initialize remaining for new records
            self.remaining_quantity = max(0.0, q - p)
            if p <= 0:
                # Not yet processed
                if self.status in ['Partially Fulfilled', 'Fulfilled', 'Completed']:
                    self.status = 'Approved'
            elif p >= q > 0:
                self.status = 'Fulfilled'
                self.remaining_quantity = 0
            else:
                self.status = 'Partially Fulfilled'
        except Exception:
            # Fallback: do not block save if any conversion issue
            pass
        
        super().save(*args, **kwargs)
    
    @property
    def is_approved(self):
        return self.status in ['Approved', 'In Progress', 'Partially Fulfilled', 'Fulfilled', 'Completed']
    
    @property
    def is_completed(self):
        return self.status in ['Completed', 'Cancelled', 'Rejected']
    
    @property
    def progress_percentage(self):
        if float(self.quantity) == 0:
            return 0
        return min(100, (float(self.processed_quantity) / float(self.quantity)) * 100)
    
    @property
    def remaining_transport_quantity(self):
        """Calculate remaining quantity available for transport assignment"""
        if not self.processed_quantity:
            return 0
        
        total_transported = self.transports.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0
        
        return max(0, self.processed_quantity - total_transported)
    
    @property
    def total_transported_quantity(self):
        """Calculate total quantity already assigned to transporters"""
        return self.transports.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('material_order_detail', kwargs={'pk': self.pk})


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
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
    warehouse = models.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text="Warehouse associated with this BOQ item"
    )
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
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
    warehouse = models.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text="Warehouse associated with this report"
    )
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
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
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
    """
    Model to track the transportation of materials from warehouse to destination.
    """
    STATUS_CHOICES = [
        ('Pending', 'Pending Assignment'),
        ('Assigned', 'Assigned to Transporter'),
        ('Loading', 'Loading in Progress'),
        ('Loaded', 'Loaded on Truck'),
        ('In Transit', 'In Transit'),
        ('Delivered', 'Delivered to Site'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled')
    ]

    material_order = models.ForeignKey(
        MaterialOrder, 
        on_delete=models.CASCADE,
        related_name='transports'
    )
    release_letter = models.ForeignKey(
        ReleaseLetter, 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transports'
    )
    
    # Material details (cached from order)
    material_name = models.CharField(max_length=200)
    material_code = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=20, blank=True, null=True)
    
    # Warehouse and destination details
    warehouse = models.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text="Warehouse where the material is being transported from"
    )
    recipient = models.CharField(max_length=200)
    consultant = models.CharField(max_length=200)
    region = models.CharField(max_length=100, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    community = models.CharField(max_length=100, blank=True, null=True)
    package_number = models.CharField(max_length=50, blank=True, null=True)
    destination_contact = models.CharField(max_length=100, blank=True, null=True)
    destination_phone = models.CharField(max_length=20, blank=True, null=True)
    
    # Transporter and vehicle details
    transporter = models.ForeignKey(
        'Transporter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transports'
    )
    vehicle = models.ForeignKey(
        'TransportVehicle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transports'
    )
    driver_name = models.CharField(max_length=100, blank=True, null=True)
    driver_phone = models.CharField(max_length=20, blank=True, null=True)
    waybill_number = models.CharField(max_length=50, blank=True, null=True)
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Pending'
    )
    
    # Dates
    date_assigned = models.DateTimeField(null=True, blank=True)
    date_loading_started = models.DateTimeField(null=True, blank=True)
    date_loaded = models.DateTimeField(null=True, blank=True)
    date_departed = models.DateTimeField(null=True, blank=True)
    date_delivered = models.DateTimeField(null=True, blank=True)
    date_completed = models.DateTimeField(null=True, blank=True)
    
    # Tracking and documentation
    tracking_url = models.URLField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # Audit fields
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_transports'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Material Transport'
        verbose_name_plural = 'Material Transports'
    
    def save(self, *args, **kwargs):
        """Auto-populate fields from MaterialOrder when saving"""
        if self.material_order:
            self.material_name = self.material_order.name
            self.material_code = self.material_order.code
            # Only set quantity if it's not already set (to preserve processed quantity from assignment)
            if not self.quantity:
                self.quantity = self.material_order.processed_quantity or self.material_order.quantity
            self.unit = str(self.material_order.unit) if self.material_order.unit else ''
            self.recipient = self.material_order.contractor or ''
            self.consultant = self.material_order.consultant or ''
            self.region = self.material_order.region
            self.district = self.material_order.district
            self.community = self.material_order.community
            self.package_number = self.material_order.package_number
            
            # If this is a new transport and has a release letter, set status to 'Assigned'
            if not self.pk and self.release_letter:
                self.status = 'Assigned'
        
        # Update timestamps based on status changes
        if self.pk:
            old_instance = MaterialTransport.objects.get(pk=self.pk)
            if old_instance.status != self.status:
                now = timezone.now()
                if self.status == 'Assigned' and not self.date_assigned:
                    self.date_assigned = now
                elif self.status == 'Loading' and not self.date_loading_started:
                    self.date_loading_started = now
                elif self.status == 'Loaded' and not self.date_loaded:
                    self.date_loaded = now
                elif self.status == 'In Transit' and not self.date_departed:
                    self.date_departed = now
                elif self.status == 'Delivered' and not self.date_delivered:
                    self.date_delivered = now
                elif self.status == 'Completed' and not self.date_completed:
                    self.date_completed = now
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Transport: {self.material_name} ({self.quantity} {self.unit}) to {self.recipient}"
    
    @property
    def current_status_display(self):
        """Return a more user-friendly status display"""
        return dict(self.STATUS_CHOICES).get(self.status, self.status)
    
    @property
    def is_completed(self):
        return self.status in ['Completed', 'Cancelled']
    
    @property
    def is_active(self):
        return self.status not in ['Completed', 'Cancelled']
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('transport_detail', kwargs={'pk': self.pk})

class SiteReceipt(models.Model):
    """
    Model for consultants to log material receipts at project sites.
    Links to MaterialTransport to update delivery status.
    """
    material_transport = models.OneToOneField(
        MaterialTransport,
        on_delete=models.CASCADE,
        related_name='site_receipt'
    )
    
    # Receipt details
    received_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    received_date = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Documentation
    waybill_pdf = models.FileField(
        upload_to='site_receipts/waybills/%Y/%m/%d/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        help_text="Upload the endorsed waybill PDF"
    )
    site_photos = models.FileField(
        upload_to='site_receipts/photos/%Y/%m/%d/',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])],
        help_text="Upload photos of materials at site"
    )
    
    # Additional fields
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the receipt")
    condition = models.CharField(
        max_length=20,
        choices=[
            ('Good', 'Good Condition'),
            ('Damaged', 'Damaged'),
            ('Partial', 'Partial Delivery')
        ],
        default='Good'
    )
    
    class Meta:
        ordering = ['-received_date']
        verbose_name = 'Site Receipt'
        verbose_name_plural = 'Site Receipts'
    
    def save(self, *args, **kwargs):
        """Update the related MaterialTransport status when site receipt is created"""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new and self.material_transport:
            # Update transport status to 'Delivered' when site receipt is logged
            self.material_transport.status = 'Delivered'
            self.material_transport.date_delivered = self.received_date
            self.material_transport.save()
    
    def __str__(self):
        return f"Site Receipt: {self.material_transport.material_name} - {self.received_quantity} {self.material_transport.unit}"

class Project(models.Model):
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
        ('Infrastructure', 'Infrastructure'),
        ('Construction', 'Construction'),
        ('Maintenance', 'Maintenance'),
        ('Emergency', 'Emergency'),
    ]
    
    name = models.CharField(max_length=200, help_text="Project name")
    code = models.CharField(max_length=50, unique=True, help_text="Unique project code")
    description = models.TextField(help_text="Detailed project description")
    project_type = models.CharField(max_length=50, choices=PROJECT_TYPE_CHOICES, default='Infrastructure')
    status = models.CharField(max_length=50, choices=PROJECT_STATUS_CHOICES, default='Planning')
    
    # Project management details
    project_manager = models.ForeignKey(
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
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_projects')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        permissions = [
            ('can_manage_projects', 'Can manage projects'),
            ('can_view_all_projects', 'Can view all projects'),
        ]
    
    def __str__(self):
        return f"{self.code} - {self.name}"

class ProjectSite(models.Model):
    """
    Represents individual sites within a project
    """
    SITE_STATUS_CHOICES = [
        ('Planned', 'Planned'),
        ('Active', 'Active'),
        ('Completed', 'Completed'),
        ('On Hold', 'On Hold'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='sites')
    name = models.CharField(max_length=200, help_text="Site name or identifier")
    code = models.CharField(max_length=50, help_text="Site code")
    
    # Location details
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    community = models.CharField(max_length=100, null=True, blank=True)
    gps_coordinates = models.CharField(max_length=100, null=True, blank=True, help_text="GPS coordinates if available")
    
    # Site management
    site_supervisor = models.ForeignKey(
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
    
    class Meta:
        ordering = ['project', 'name']
        unique_together = ['project', 'code']
    
    def __str__(self):
        return f"{self.project.code} - {self.name}"

class ProjectPhase(models.Model):
    """
    Represents different phases within a project
    """
    PHASE_STATUS_CHOICES = [
        ('Not Started', 'Not Started'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Delayed', 'Delayed'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='phases')
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
    
    class Meta:
        ordering = ['project', 'phase_order']
        unique_together = ['project', 'phase_order']
    
    def __str__(self):
        return f"{self.project.code} - Phase {self.phase_order}: {self.name}"

class Notification(models.Model):
    """
    Model for system notifications between user groups
    """
    NOTIFICATION_TYPES = [
        ('material_request', 'Material Request'),
        ('material_processed', 'Material Processed'),
        ('transport_assigned', 'Transport Assigned'),
        ('material_delivered', 'Material Delivered'),
        ('site_receipt_logged', 'Site Receipt Logged'),
        ('boq_updated', 'BOQ Updated'),
        ('staff_prompt', 'Staff Prompt'),
    ]
    
    RECIPIENT_GROUPS = [
        ('Schedule Officers', 'Schedule Officers'),
        ('Storekeepers', 'Storekeepers'),
        ('Management', 'Management'),
        ('Consultants', 'Consultants'),
        ('All', 'All Users'),
    ]
    
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    
    # Recipients
    recipient_group = models.CharField(max_length=20, choices=RECIPIENT_GROUPS)
    recipient_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='received_notifications',
        help_text="Specific user recipient (optional)"
    )
    
    # Sender
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )
    
    # Related objects (optional)
    related_order = models.ForeignKey(
        MaterialOrder,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    related_transport = models.ForeignKey(
        MaterialTransport,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    related_project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    
    # Status
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.title} - {self.recipient_group}"
    
    def mark_as_read(self, user=None):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()