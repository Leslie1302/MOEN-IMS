# Inventory/models.py
from django.db import models
import auto_prefetch
from django.contrib.auth.models import User, Group
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.conf import settings
import uuid
import os

# Try to import PIL for image generation
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Import transporter models
from .transporter_models import Transporter, TransportVehicle

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

class Supplier(auto_prefetch.Model):
    """
    Model for representing suppliers who provide materials to the inventory.
    Enhanced with registration and rating for supply contract management.
    """
    name = models.CharField(max_length=200, help_text="Name of the supplier")
    code = models.CharField(max_length=50, unique=True, help_text="Unique supplier code")
    registration_number = models.CharField(max_length=100, blank=True, null=True, help_text="Business registration number")
    contact_person = models.CharField(max_length=200, blank=True, null=True, help_text="Primary contact person")
    contact_phone = models.CharField(max_length=20, blank=True, null=True, help_text="Contact phone number")
    contact_email = models.EmailField(blank=True, null=True, help_text="Contact email address")
    address = models.TextField(blank=True, null=True, help_text="Physical address of the supplier")
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, help_text="Supplier rating (0-5)")
    is_active = models.BooleanField(default=True, help_text="Whether this supplier is currently active")
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the supplier")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['name']
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('supplier_detail', kwargs={'pk': self.pk})

class ReleaseLetter(auto_prefetch.Model):
    """
    Model for storing release letters that authorize material releases.
    Each letter is linked to a specific material order.
    
    Enhanced for tracking:
    - Drawdown: Tracks requested (administrative commitment) vs. authorized
    - Fulfillment: Tracks delivered (physical movement) vs. authorized
    """
    # Original fields
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
        blank=True,
        null=True,
        help_text="The signed release letter in PDF format"
    )
    uploaded_by = auto_prefetch.ForeignKey(
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
    
    # ========== NEW TRACKING FIELDS ==========
    
    # Unique reference for tracking
    reference_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        blank=True,
        null=True,
        help_text="Unique reference number for this release letter (auto-generated if blank)"
    )
    
    # Authorized quantity tracking
    total_quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Total quantity authorized by this release letter"
    )
    
    # Material classification
    MATERIAL_TYPE_CHOICES = [
        ('Transformers', 'Transformers'),
        ('Poles', 'Poles'),
        ('Cables', 'Cables'),
        ('Conductors', 'Conductors'),
        ('Meters', 'Meters'),
        ('Insulators', 'Insulators'),
        ('Switches', 'Switches'),
        ('Other', 'Other'),
    ]
    material_type = models.CharField(
        max_length=50,
        choices=MATERIAL_TYPE_CHOICES,
        default='Other',
        help_text="Type of material covered by this release letter"
    )
    
    # Project phase association
    project_phase = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Project phase this release letter covers"
    )
    
    # Status tracking
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('Closed', 'Closed'),
    ]
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='Open',
        help_text="Status of this release letter"
    )
    
    # Alert threshold
    alert_threshold_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=80.00,
        help_text="Percentage threshold to trigger drawdown alerts (default 80%)"
    )
    
    # BOQ linkage for guardrail validation
    boq_item = auto_prefetch.ForeignKey(
        'BillOfQuantity',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='release_letters',
        help_text="Bill of Quantity item for allocation validation"
    )

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-upload_time']
        verbose_name = 'Release Letter'
        verbose_name_plural = 'Release Letters'
        unique_together = ['request_code', 'title']  # Prevent duplicate letters for same request
        permissions = [
            ('can_upload_release_letter', 'Can upload release letters'),
            ('can_view_release_letter_tracking', 'Can view release letter tracking dashboard'),
        ]
    
    def save(self, *args, **kwargs):
        """Auto-generate reference number if not provided."""
        if not self.reference_number:
            from datetime import datetime
            import uuid
            date_str = datetime.now().strftime('%Y%m%d')
            unique_id = uuid.uuid4().hex[:6].upper()
            self.reference_number = f"RL-{date_str}-{unique_id}"
        super().save(*args, **kwargs)
        
    def get_related_orders(self):
        """Get all material orders associated with this release letter."""
        return self.material_orders.all()
    
    def get_related_orders_by_request_code(self):
        """Get all material orders associated with this request code (legacy method)."""
        return MaterialOrder.objects.filter(request_code=self.request_code)

    def __str__(self):
        ref = self.reference_number or self.request_code
        return f"{self.title} - {ref}"
    
    # ========== CALCULATED PROPERTIES FOR TRACKING ==========
    
    @property
    def total_requested(self):
        """
        Sum of all linked MaterialOrder quantities (administrative commitment).
        This represents what has been "committed" on paper.
        """
        from decimal import Decimal
        result = self.material_orders.aggregate(
            total=models.Sum('quantity')
        )['total']
        return Decimal(str(result)) if result else Decimal('0')
    
    @property
    def balance_to_request(self):
        """
        Remaining quantity available to request.
        Represents how much more can be requested against this letter.
        """
        from decimal import Decimal
        total_qty = Decimal(str(self.total_quantity)) if self.total_quantity else Decimal('0')
        return max(Decimal('0'), total_qty - self.total_requested)
    
    @property
    def drawdown_percentage(self):
        """
        Percentage of authorized quantity that has been requested.
        Shows administrative commitment level.
        """
        from decimal import Decimal
        if not self.total_quantity or self.total_quantity == 0:
            return Decimal('0')
        return (self.total_requested / Decimal(str(self.total_quantity))) * 100
    
    @property
    def total_released(self):
        """
        Sum of quantities from Delivered transports (physical movement).
        This represents what has actually left the warehouse.
        """
        from decimal import Decimal
        # Get from transports linked directly to this release letter
        result = self.transports.filter(
            status='Delivered'
        ).aggregate(total=models.Sum('quantity'))['total']
        return Decimal(str(result)) if result else Decimal('0')
    
    @property
    def fulfillment_percentage(self):
        """
        Percentage of authorized quantity actually released/delivered.
        Shows physical movement level.
        """
        from decimal import Decimal
        if not self.total_quantity or self.total_quantity == 0:
            return Decimal('0')
        return (self.total_released / Decimal(str(self.total_quantity))) * 100
    
    @property
    def is_threshold_exceeded(self):
        """Check if drawdown has exceeded alert threshold."""
        from decimal import Decimal
        threshold = Decimal(str(self.alert_threshold_percentage)) if self.alert_threshold_percentage else Decimal('80')
        return self.drawdown_percentage >= threshold
    
    @property
    def tracking_status_color(self):
        """
        Return color coding for dashboard display.
        Green: <70%, Yellow: 70-89%, Red: >=90%
        """
        pct = float(self.drawdown_percentage)
        if pct >= 90:
            return 'danger'  # Red
        elif pct >= 70:
            return 'warning'  # Yellow
        return 'success'  # Green
    
    @property
    def fulfillment_gap(self):
        """
        Difference between requested and released.
        Positive = materials requested but not yet delivered.
        """
        return self.total_requested - self.total_released

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
    return Group.objects.get(name="default").id

def get_default_unit():
    return Unit.objects.first().id

class MaterialOrder(auto_prefetch.Model):
    """
    Model representing a material order request (release or receipt).
    """
    # Basic information
    name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)  # Changed to DecimalField for precision
    category = auto_prefetch.ForeignKey('Category', on_delete=models.SET_NULL, blank=True, null=True)
    code = models.CharField(max_length=200, blank=False, default="Enter code")
    unit = auto_prefetch.ForeignKey(Unit, on_delete=models.CASCADE)
    
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
    user = auto_prefetch.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='material_orders_created'
    )
    group = auto_prefetch.ForeignKey(
        Group, 
        on_delete=models.SET_NULL, 
        blank=True, 
        null=True,
        related_name='material_orders'
    )
    warehouse = auto_prefetch.ForeignKey(
        Warehouse, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        help_text="Warehouse associated with this order"
    )
    supplier = auto_prefetch.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Supplier for material receipts"
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
    processed_by = auto_prefetch.ForeignKey(
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
    
    # Assignment tracking (for stores workflow)
    assigned_to = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_material_orders',
        help_text="Storekeeper assigned to process this order"
    )
    assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the order was assigned to a storekeeper"
    )
    assigned_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='material_orders_assigned',
        help_text="Manager who assigned this order"
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
    phase = models.CharField(max_length=50, blank=True, null=True, help_text="SHEP Phase (e.g., SHEP-4)")
    
    # Additional metadata
    notes = models.TextField(blank=True, null=True, help_text="Additional notes or instructions")
    is_urgent = models.BooleanField(default=False)
    
    # Relationships
    release_letter = auto_prefetch.ForeignKey(
        'ReleaseLetter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='material_orders',
        help_text="The release letter that authorizes this material order"
    )
    
    # Audit fields
    created_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_material_orders',
        help_text="User who created this order"
    )
    last_updated_by = auto_prefetch.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='updated_material_orders',
        help_text="User who last updated this order"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
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
                if self.status in ['Partially Fulfilled', 'Completed']:
                    self.status = 'Approved'
            elif p >= q > 0:
                self.status = 'Completed'
                self.remaining_quantity = 0
            else:
                self.status = 'Partially Fulfilled'
        except Exception:
            # Fallback: do not block save if any conversion issue
            pass
        
        super().save(*args, **kwargs)
    
    @property
    def is_approved(self):
        return self.status in ['Approved', 'In Progress', 'Partially Fulfilled', 'Completed']
    
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


class Profile(auto_prefetch.Model):
    """
    User profile model extending Django's built-in User model.
    Stores additional user information including profile picture and digital signature stamp.
    """
    user = auto_prefetch.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    signature_stamp = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        help_text="Unique digital signature stamp for this user"
    )

    def __str__(self):
        """String representation of the profile."""
        if self.user:
            return f"{self.user.username} Profile"
        return "Profile (No User)"

    @property
    def profile_picture_url(self):
        """
        Returns the URL of the profile picture or a default image.
        
        Returns:
            str: URL path to the profile picture
        """
        if self.profile_picture:
            return self.profile_picture.url
        return '/static/images/default_profile.png'
    
    def generate_signature_stamp(self):
        """
        Generate a unique digital signature stamp for the user.
        The stamp includes: full name (first + last), timestamp, and a unique identifier.
        
        Format: "SIGNED_BY:{first_name} {last_name}|TIMESTAMP:{iso_timestamp}|ID:{unique_id}"
        
        Returns:
            str: The generated signature stamp
            
        Raises:
            ValueError: If user is None or has no name
        """
        if not self.user:
            raise ValueError("Cannot generate signature stamp: Profile has no associated user")
        
        # Get first and last name, fallback to username if names are not set
        first_name = self.user.first_name.strip() if self.user.first_name else ""
        last_name = self.user.last_name.strip() if self.user.last_name else ""
        
        # Construct full name
        if first_name and last_name:
            full_name = f"{first_name} {last_name}"
        elif first_name:
            full_name = first_name
        elif last_name:
            full_name = last_name
        elif hasattr(self.user, 'username') and self.user.username:
            # Fallback to username if no names are set
            full_name = self.user.username
        else:
            raise ValueError("Cannot generate signature stamp: User has no name or username")
        
        try:
            # Generate timestamp in ISO format
            timestamp = timezone.now().isoformat()
            
            # Generate unique identifier using UUID
            unique_id = uuid.uuid4().hex[:12].upper()
            
            # Create the signature stamp
            stamp = f"SIGNED_BY:{full_name}|TIMESTAMP:{timestamp}|ID:{unique_id}"
            
            return stamp
        except Exception as e:
            # Log the error and re-raise with context
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error generating signature stamp for user {full_name if 'full_name' in locals() else 'Unknown'}: {str(e)}")
            raise
    
    def get_or_create_signature_stamp(self):
        """
        Get existing signature stamp or create a new one if it doesn't exist.
        This method is safe to call multiple times and won't overwrite existing stamps.
        
        Returns:
            str: The signature stamp (existing or newly created)
        """
        if self.signature_stamp:
            return self.signature_stamp
        
        try:
            self.signature_stamp = self.generate_signature_stamp()
            self.save(update_fields=['signature_stamp'])
            return self.signature_stamp
        except ValueError as e:
            # Return a placeholder if we can't generate a stamp
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not generate signature stamp: {str(e)}")
            return None
    
    def display_signature_stamp(self):
        """
        Return a human-readable version of the signature stamp.
        
        Returns:
            dict: Parsed components of the signature stamp or None if no stamp exists
        """
        if not self.signature_stamp:
            return None
        
        try:
            # Parse the stamp components
            parts = self.signature_stamp.split('|')
            stamp_data = {}
            
            for part in parts:
                if ':' in part:
                    key, value = part.split(':', 1)
                    stamp_data[key] = value
            
            return stamp_data
        except Exception:
            return {'raw': self.signature_stamp}
    
    def regenerate_signature_stamp(self, force=False):
        """
        Regenerate the signature stamp. Use with caution as this will overwrite the existing stamp.
        
        Args:
            force (bool): If True, regenerate even if a stamp already exists
            
        Returns:
            str: The newly generated signature stamp
            
        Raises:
            ValueError: If force=False and a stamp already exists
        """
        if self.signature_stamp and not force:
            raise ValueError("Signature stamp already exists. Use force=True to regenerate.")
        
        self.signature_stamp = self.generate_signature_stamp()
        self.save(update_fields=['signature_stamp'])
        return self.signature_stamp
    
    def generate_digital_stamp_png(self):
        """
        Generate a PNG digital signature stamp image for the user.
        Creates a professional-looking stamp with user name, role, and unique ID.
        Saves to media/digital_signatures/ folder.
        
        Returns:
            str: Path to the generated PNG file, or None if generation failed
        """
        if not self.user:
            return None
        
        if not PIL_AVAILABLE:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("PIL/Pillow not available. Cannot generate PNG stamps.")
            return None
        
        try:
            # Get user information
            full_name = self.user.get_full_name() or self.user.username
            username = self.user.username
            
            # Get user's role/group
            user_groups = self.user.groups.all()
            role = user_groups[0].name if user_groups.exists() else "User"
            
            # Get registration year
            registration_year = self.user.date_joined.year if self.user.date_joined else timezone.now().year
            
            # Generate unique ID (use existing signature_stamp ID if available, otherwise create new)
            unique_id = None
            if self.signature_stamp and 'ID:' in self.signature_stamp:
                try:
                    parts = self.signature_stamp.split('|')
                    for part in parts:
                        if 'ID:' in part:
                            unique_id = part.split('ID:')[1].strip()
                            break
                except Exception:
                    pass
            
            if not unique_id:
                unique_id = uuid.uuid4().hex[:12].upper()
            
            # Create digital_signatures directory if it doesn't exist
            digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital_signatures')
            if not os.path.exists(digital_signatures_dir):
                # Try with space in folder name
                digital_signatures_dir = os.path.join(settings.MEDIA_ROOT, 'digital signatures')
                if not os.path.exists(digital_signatures_dir):
                    os.makedirs(digital_signatures_dir, exist_ok=True)
            
            # Create stamp image (300x150 pixels)
            width, height = 300, 150
            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)
            
            # Draw border
            border_color = '#1a5490'  # Navy blue
            draw.rectangle([(0, 0), (width-1, height-1)], outline=border_color, width=3)
            
            # Draw inner border
            draw.rectangle([(5, 5), (width-6, height-6)], outline='#dc3545', width=2)
            
            # Try to use a nice font, fallback to default
            try:
                # Try to use system fonts
                if os.name == 'nt':  # Windows
                    title_font = ImageFont.truetype("arial.ttf", 14)
                    name_font = ImageFont.truetype("arial.ttf", 16)
                    text_font = ImageFont.truetype("arial.ttf", 10)
                else:  # Linux/Mac
                    title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
                    name_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
                    text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
            except:
                # Fallback to default font
                title_font = ImageFont.load_default()
                name_font = ImageFont.load_default()
                text_font = ImageFont.load_default()
            
            # Helper function to get text width (works with both default and truetype fonts)
            def get_text_width(text, font):
                try:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    return bbox[2] - bbox[0]
                except:
                    # Fallback for older PIL versions
                    try:
                        return draw.textlength(text, font=font)
                    except:
                        # Last resort: estimate width
                        return len(text) * 6
            
            # Draw "AUTHORIZED SIGNATURE" at top
            title_text = "AUTHORIZED SIGNATURE"
            title_width = get_text_width(title_text, title_font)
            draw.text(((width - title_width) / 2, 12), title_text, fill=border_color, font=title_font)
            
            # Draw user's full name (centered)
            name_width = get_text_width(full_name, name_font)
            draw.text(((width - name_width) / 2, 45), full_name, fill='black', font=name_font)
            
            # Draw role
            role_width = get_text_width(role, text_font)
            draw.text(((width - role_width) / 2, 70), role, fill='#666666', font=text_font)
            
            # Draw "Since YEAR" and "ID: XXXXXX" at bottom
            since_text = f"Since {registration_year}"
            id_text = f"ID: {unique_id}"
            
            since_width = get_text_width(since_text, text_font)
            id_width = get_text_width(id_text, text_font)
            
            draw.text((15, height - 30), since_text, fill='#666666', font=text_font)
            draw.text((width - id_width - 15, height - 30), id_text, fill='#666666', font=text_font)
            
            # Save the image
            filename = f"{username}.png"
            filepath = os.path.join(digital_signatures_dir, filename)
            img.save(filepath, 'PNG')
            
            return filepath
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error generating PNG digital stamp for user {self.user.username if self.user else 'Unknown'}: {str(e)}")
            return None


    
class BillOfQuantity(auto_prefetch.Model):
    """Bill of Quantity model - tracks material quantities by community"""
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    community = models.CharField(max_length=100, null=True, blank=True)
    consultant = models.CharField(max_length=200)
    contractor = models.CharField(max_length=200)
    package_number = models.CharField(max_length=50)
    phase = models.CharField(max_length=50, blank=True, null=True, help_text="SHEP Phase (e.g., SHEP-4)")
    material_description = models.CharField(max_length=200)
    item_code = models.CharField(max_length=200)
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


class BoQOverissuanceJustification(auto_prefetch.Model):
    """
    Tracks justifications for Bill of Quantity overissuances
    (when quantity_received exceeds contract_quantity)
    """
    JUSTIFICATION_STATUS_CHOICES = [
        ('Pending', 'Pending Review'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
        ('Under Review', 'Under Review'),
    ]
    
    boq_item = auto_prefetch.ForeignKey(
        BillOfQuantity, 
        on_delete=models.CASCADE,
        related_name='overissuance_justifications',
        help_text="Bill of Quantity item with overissuance"
    )
    package_number = models.CharField(max_length=50, help_text="Project package number")
    project_name = models.CharField(max_length=200, help_text="Project name/description")
    overissuance_quantity = models.FloatField(help_text="Amount of overissuance")
    
    # Justification details
    reason = models.TextField(help_text="Detailed reason for overissuance")
    justification_category = models.CharField(
        max_length=100,
        choices=[
            ('Design Change', 'Design Change'),
            ('Site Condition', 'Site Condition'),
            ('Measurement Error', 'Measurement Error'),
            ('Emergency Need', 'Emergency Need'),
            ('Variation Order', 'Variation Order'),
            ('Other', 'Other'),
        ],
        help_text="Category of justification"
    )
    supporting_documents = models.TextField(
        blank=True,
        help_text="Reference to supporting documents or file paths"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=JUSTIFICATION_STATUS_CHOICES,
        default='Pending',
        help_text="Status of the justification"
    )
    
    # User tracking
    submitted_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='submitted_overissuance_justifications',
        help_text="User who submitted the justification"
    )
    reviewed_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_overissuance_justifications',
        help_text="User who reviewed the justification"
    )
    
    # Timestamps
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Review comments
    review_comments = models.TextField(
        blank=True,
        help_text="Comments from reviewer"
    )
    
    class Meta(auto_prefetch.Model.Meta):
        verbose_name = 'BoQ Overissuance Justification'
        verbose_name_plural = 'BoQ Overissuance Justifications'
        ordering = ['-submitted_at']
        permissions = [
            ('can_review_overissuance', 'Can review overissuance justifications'),
            ('can_view_overissuance_summary', 'Can view overissuance summary'),
        ]
    
    def __str__(self):
        return f"{self.package_number} - {self.boq_item.material_description} (Overissuance: {self.overissuance_quantity})"


class MaterialOrderAudit(auto_prefetch.Model):
    order = auto_prefetch.ForeignKey(MaterialOrder, on_delete=models.CASCADE)
    action = models.CharField(max_length=100)
    performed_by = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} on {self.order.id} by {self.performed_by}"
    

class ReportSubmission(auto_prefetch.Model):
    # Fields matching BillOfQuantity
    region = models.CharField(max_length=100)
    district = models.CharField(max_length=100)
    community = models.CharField(max_length=100, null=True, blank=True)
    consultant = models.CharField(max_length=200)
    contractor = models.CharField(max_length=200)
    package_number = models.CharField(max_length=50)
    phase = models.CharField(max_length=50, blank=True, null=True, help_text="SHEP Phase (e.g., SHEP-4)")
    material_description = models.CharField(max_length=200)
    item_code = models.CharField(max_length=200)
    contract_quantity = models.FloatField()
    quantity_received = models.FloatField(default=0.0)
    warehouse = auto_prefetch.ForeignKey(
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
    user = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    group = auto_prefetch.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    related_boq = auto_prefetch.ForeignKey(
        BillOfQuantity, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='report_submissions'
    )

    class Meta(auto_prefetch.Model.Meta):
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
                item_code=self.item_code,
                defaults={
                    'region': self.region,
                    'district': self.district,
                    'consultant': self.consultant,
                    'contractor': self.contractor,
                    'material_description': self.material_description,
                    'contract_quantity': self.contract_quantity,
                    'quantity_received': self.quantity_received,
                    'phase': self.phase,
                    'user': self.user,
                    'group': self.group
                }
            )
            self.related_boq = boq
            self.save()

    @property
    def balance(self):
        """Calculate the remaining balance (contract_quantity - quantity_received)"""
        return self.contract_quantity - self.quantity_received

class MaterialTransport(auto_prefetch.Model):
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

    material_order = auto_prefetch.ForeignKey(
        MaterialOrder, 
        on_delete=models.CASCADE,
        related_name='transports'
    )
    release_letter = auto_prefetch.ForeignKey(
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
    warehouse = auto_prefetch.ForeignKey(
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
    transporter = auto_prefetch.ForeignKey(
        'Transporter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transports'
    )
    vehicle = auto_prefetch.ForeignKey(
        'TransportVehicle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transports'
    )
    driver_name = models.CharField(max_length=100, blank=True, null=True)
    driver_phone = models.CharField(max_length=20, blank=True, null=True)
    waybill_number = models.CharField(max_length=50, blank=True, null=True)
    consignment_number = models.CharField(
        max_length=50, 
        blank=True, 
        null=True,
        help_text="Groups multiple materials assigned together as one shipment"
    )
    
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
    waybill_download_count = models.IntegerField(default=0, help_text="Number of times this waybill has been downloaded")
    
    # Audit fields
    created_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_transports'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta(auto_prefetch.Model.Meta):
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
            # community field removed - package-based tracking only
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

class SiteReceipt(auto_prefetch.Model):
    """
    Model for consultants to log material receipts at project sites.
    Links to MaterialTransport to update delivery status.
    """
    material_transport = auto_prefetch.OneToOneField(
        MaterialTransport,
        on_delete=models.CASCADE,
        related_name='site_receipt'
    )
    
    # Receipt details
    received_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    received_date = models.DateTimeField(auto_now_add=True)
    received_by = auto_prefetch.ForeignKey(User, on_delete=models.CASCADE)
    
    # Documentation
    waybill_pdf = models.FileField(
        upload_to='site_receipts/waybills/%Y/%m/%d/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        help_text="Upload the endorsed waybill PDF"
    )
    acknowledgement_sheet = models.FileField(
        upload_to='site_receipts/acknowledgements/%Y/%m/%d/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png'])],
        help_text="Upload the signed acknowledgement sheet",
        null=True,
        blank=True
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
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-received_date']
        verbose_name = 'Site Receipt'
        verbose_name_plural = 'Site Receipts'
    
    def save(self, *args, **kwargs):
        """Update the related MaterialTransport status and BOQ when site receipt is created"""
        import logging
        logger = logging.getLogger(__name__)
        
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new and self.material_transport:
            # Update transport status to 'Delivered' when site receipt is logged
            self.material_transport.status = 'Delivered'
            self.material_transport.date_delivered = self.received_date
            self.material_transport.save()
            
            # Update BOQ quantity_received based on site receipt
            try:
                material_order = self.material_transport.material_order
                if material_order and material_order.package_number:
                    # Try to find matching BOQ entry
                    boq_entry = None
                    
                    # Strategy 1: Match by item_code and package_number
                    if material_order.code and material_order.package_number:
                        boq_entry = BillOfQuantity.objects.filter(
                            item_code=material_order.code,
                            package_number=material_order.package_number
                        ).first()
                        logger.info(f"BOQ lookup by code={material_order.code}, package={material_order.package_number}: {'Found' if boq_entry else 'Not found'}")
                    
                    # Strategy 2: Match by material_description and package_number
                    if not boq_entry and material_order.name and material_order.package_number:
                        boq_entry = BillOfQuantity.objects.filter(
                            material_description__iexact=material_order.name,
                            package_number=material_order.package_number
                        ).first()
                        logger.info(f"BOQ lookup by name={material_order.name}, package={material_order.package_number}: {'Found' if boq_entry else 'Not found'}")
                    
                    if boq_entry:
                        # Update BOQ with received quantity from site receipt
                        old_qty = boq_entry.quantity_received
                        boq_entry.quantity_received += float(self.received_quantity)
                        
                        # Log if exceeding contract quantity
                        if boq_entry.quantity_received > boq_entry.contract_quantity:
                            logger.warning(
                                f"BOQ quantity_received ({boq_entry.quantity_received}) exceeds contract_quantity "
                                f"({boq_entry.contract_quantity}) for {boq_entry.material_description}"
                            )
                        
                        boq_entry.save()
                        logger.info(
                            f"Site Receipt: Updated BOQ for '{boq_entry.material_description}' (Package: {boq_entry.package_number}): "
                            f"quantity_received {old_qty} → {boq_entry.quantity_received}, balance: {boq_entry.balance}"
                        )
                    else:
                        logger.warning(
                            f"Site Receipt: No BOQ entry found. "
                            f"Order details - code: {material_order.code}, name: {material_order.name}, package: {material_order.package_number}"
                        )
            except Exception as e:
                logger.error(f"Error updating BOQ from site receipt: {str(e)}", exc_info=True)
    
    def __str__(self):
        return f"Site Receipt: {self.material_transport.material_name} - {self.received_quantity} {self.material_transport.unit}"

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

class Notification(auto_prefetch.Model):
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
    recipient_user = auto_prefetch.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='received_notifications',
        help_text="Specific user recipient (optional)"
    )
    
    # Sender
    sender = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications'
    )
    
    # Related objects (optional)
    related_order = auto_prefetch.ForeignKey(
        MaterialOrder,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    related_transport = auto_prefetch.ForeignKey(
        MaterialTransport,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    related_project = auto_prefetch.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    
    # Status
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.title} - {self.recipient_group}"
    
    def mark_as_read(self, user=None):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()


class SupplierPriceCatalog(auto_prefetch.Model):
    """
    Model for tracking supplier prices for materials.
    Maintains historical pricing data and supports price comparisons.
    """
    supplier = auto_prefetch.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='price_catalog',
        help_text="Supplier offering this price"
    )
    material = auto_prefetch.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name='supplier_prices',
        help_text="Material being priced"
    )
    unit_rate = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Price per unit"
    )
    currency = models.CharField(
        max_length=3,
        default='GHS',
        help_text="Currency code (e.g., GHS, USD)"
    )
    effective_date = models.DateField(
        help_text="Date from which this price is valid"
    )
    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date when this price expires (null = no expiry)"
    )
    minimum_order_quantity = models.IntegerField(
        default=1,
        help_text="Minimum quantity that must be ordered"
    )
    warehouse = auto_prefetch.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='supplier_prices',
        help_text="Warehouse this supplier delivers to"
    )
    lead_time_days = models.IntegerField(
        default=0,
        help_text="Number of days for delivery"
    )
    notes = models.TextField(
        blank=True,
        null=True,
        help_text="Additional pricing notes or conditions"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this price is currently active"
    )
    created_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_prices'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-effective_date', 'supplier__name']
        verbose_name = 'Supplier Price'
        verbose_name_plural = 'Supplier Prices'
        unique_together = ['supplier', 'material', 'effective_date']

    def __str__(self):
        return f"{self.supplier.name} - {self.material.name}: {self.currency} {self.unit_rate}"

    @property
    def is_expired(self):
        """Check if price has expired"""
        if self.expiry_date:
            from django.utils import timezone
            return timezone.now().date() > self.expiry_date
        return False

    @property
    def is_valid(self):
        """Check if price is currently valid"""
        return self.is_active and not self.is_expired


class SupplyContract(auto_prefetch.Model):
    """
    Model for supply contracts with suppliers.
    Tracks contract details, terms, and estimated/actual costs.
    """
    CONTRACT_TYPES = [
        ('one_time', 'One-Time Purchase'),
        ('framework', 'Framework Agreement'),
        ('long_term', 'Long-Term Contract'),
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('pending_approval', 'Pending Approval'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    contract_number = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique contract reference number"
    )
    title = models.CharField(
        max_length=200,
        help_text="Contract title/description"
    )
    supplier = auto_prefetch.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='contracts',
        help_text="Supplier for this contract"
    )
    contract_type = models.CharField(
        max_length=20,
        choices=CONTRACT_TYPES,
        default='one_time'
    )
    start_date = models.DateField(help_text="Contract start date")
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Contract end date (null for open-ended)"
    )
    total_estimated_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0.00,
        help_text="Total estimated contract value"
    )
    currency = models.CharField(
        max_length=3,
        default='GHS'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='draft'
    )
    terms_and_conditions = models.TextField(
        blank=True,
        null=True,
        help_text="Contract terms and conditions"
    )
    notes = models.TextField(blank=True, null=True)
    
    # Workflow fields
    created_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_contracts'
    )
    approved_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_contracts'
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-created_at']
        verbose_name = 'Supply Contract'
        verbose_name_plural = 'Supply Contracts'

    def __str__(self):
        return f"{self.contract_number} - {self.supplier.name}"

    @property
    def actual_value(self):
        """Calculate actual contract value from items"""
        return sum(item.total_amount for item in self.items.all())

    @property
    def is_active(self):
        """Check if contract is currently active"""
        return self.status == 'active'


class SupplyContractItem(auto_prefetch.Model):
    """
    Individual items/materials in a supply contract.
    """
    contract = auto_prefetch.ForeignKey(
        SupplyContract,
        on_delete=models.CASCADE,
        related_name='items'
    )
    material = auto_prefetch.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name='contract_items'
    )
    quantity = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Contracted quantity"
    )
    unit_rate = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Price per unit"
    )
    warehouse = auto_prefetch.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Delivery warehouse"
    )
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['material__name']
        verbose_name = 'Contract Item'
        verbose_name_plural = 'Contract Items'

    def __str__(self):
        return f"{self.contract.contract_number} - {self.material.name}"

    @property
    def total_amount(self):
        """Calculate total cost for this item"""
        return self.quantity * self.unit_rate


class SupplierInvoice(auto_prefetch.Model):
    """
    Model for supplier invoices for processing and payment tracking.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('approved', 'Approved for Payment'),
        ('paid', 'Paid'),
        ('disputed', 'Disputed'),
        ('rejected', 'Rejected'),
    ]
    
    invoice_number = models.CharField(
        max_length=100,
        unique=True,
        help_text="Supplier's invoice number"
    )
    supplier = auto_prefetch.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name='invoices'
    )
    contract = auto_prefetch.ForeignKey(
        SupplyContract,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices',
        help_text="Related contract (if any)"
    )
    invoice_date = models.DateField(help_text="Date on the invoice")
    due_date = models.DateField(help_text="Payment due date")
    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Total invoice amount"
    )
    currency = models.CharField(max_length=3, default='GHS')
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    uploaded_document = models.FileField(
        upload_to='invoices/%Y/%m/',
        null=True,
        blank=True,
        help_text="Scanned invoice document"
    )
    payment_reference = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Payment reference number"
    )
    payment_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date payment was made"
    )
    discrepancy_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Notes about any discrepancies found"
    )
    notes = models.TextField(blank=True, null=True)
    
    # Workflow
    submitted_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='submitted_invoices'
    )
    verified_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='verified_invoices'
    )
    approved_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_invoices'
    )
    verified_date = models.DateTimeField(null=True, blank=True)
    approved_date = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-invoice_date']
        verbose_name = 'Supplier Invoice'
        verbose_name_plural = 'Supplier Invoices'

    def __str__(self):
        return f"{self.invoice_number} - {self.supplier.name}"

    @property
    def calculated_total(self):
        """Calculate total from invoice items"""
        return sum(item.total_amount for item in self.items.all())

    @property
    def is_overdue(self):
        """Check if invoice is overdue"""
        if self.status in ['paid', 'rejected']:
            return False
        from django.utils import timezone
        return timezone.now().date() > self.due_date


class SupplierInvoiceItem(auto_prefetch.Model):
    """
    Individual line items in a supplier invoice.
    """
    invoice = auto_prefetch.ForeignKey(
        SupplierInvoice,
        on_delete=models.CASCADE,
        related_name='items'
    )
    material = auto_prefetch.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name='invoice_items'
    )
    material_order = auto_prefetch.ForeignKey(
        'MaterialOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice_items',
        help_text="Link to actual material order if applicable"
    )
    quantity_invoiced = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Quantity on the invoice"
    )
    unit_rate_invoiced = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Unit rate on the invoice"
    )
    quantity_received = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Quantity actually received (from MaterialOrder)"
    )
    warehouse = auto_prefetch.ForeignKey(
        Warehouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    discrepancy_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Notes about quantity/price discrepancies"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['material__name']
        verbose_name = 'Invoice Item'
        verbose_name_plural = 'Invoice Items'

    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.material.name}"

    @property
    def total_amount(self):
        """Calculate total for this invoice item"""
        return self.quantity_invoiced * self.unit_rate_invoiced

    @property
    def has_discrepancy(self):
        """Check if there's a quantity discrepancy"""
        if self.quantity_received is not None:
            return abs(self.quantity_invoiced - self.quantity_received) > 0.01
        return False


class WeeklyReport(auto_prefetch.Model):
    """
    Model to store generated weekly development reports.
    Keeps a history of all reports sent for auditing and reference.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]
    
    # Report metadata
    report_id = models.CharField(max_length=50, unique=True, editable=False, help_text="Unique report identifier")
    generated_by = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='generated_reports')
    generated_at = models.DateTimeField(auto_now_add=True)
    
    # Date range
    start_date = models.DateField(help_text="Start date of the reporting period")
    end_date = models.DateField(help_text="End date of the reporting period")
    
    # Report content
    subject = models.CharField(max_length=500, help_text="Email subject line")
    executive_summary = models.TextField(help_text="Brief overview of the week's activities")
    new_features = models.TextField(blank=True, help_text="New features implemented")
    bug_fixes = models.TextField(blank=True, help_text="Bug fixes and issues resolved")
    database_changes = models.TextField(blank=True, help_text="Database migrations and schema changes")
    code_improvements = models.TextField(blank=True, help_text="Code refactoring and improvements")
    pending_tasks = models.TextField(blank=True, help_text="Pending tasks and known issues")
    next_priorities = models.TextField(blank=True, help_text="Next week's priorities")
    custom_notes = models.TextField(blank=True, help_text="Custom notes added by the generator")
    
    # Email details
    recipients = models.TextField(help_text="Comma-separated list of recipient emails")
    cc_recipients = models.TextField(blank=True, help_text="Comma-separated list of CC emails")
    
    # Status and tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    sent_at = models.DateTimeField(null=True, blank=True, help_text="When the report was sent")
    error_message = models.TextField(blank=True, help_text="Error message if sending failed")
    
    # Statistics
    commits_analyzed = models.IntegerField(default=0, help_text="Number of git commits analyzed")
    files_scanned = models.IntegerField(default=0, help_text="Number of documentation files scanned")
    migrations_found = models.IntegerField(default=0, help_text="Number of migrations found")
    
    # Full report content (for archival)
    html_content = models.TextField(blank=True, help_text="Full HTML email content")
    plain_text_content = models.TextField(blank=True, help_text="Plain text email content")
    pdf_file = models.FileField(upload_to='weekly_reports/', blank=True, null=True, help_text="Generated PDF report")
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-generated_at']
        verbose_name = 'Weekly Report'
        verbose_name_plural = 'Weekly Reports'
    
    def __str__(self):
        return f"Weekly Report {self.report_id} - {self.start_date} to {self.end_date}"
    
    def save(self, *args, **kwargs):
        """Generate unique report ID if not set"""
        if not self.report_id:
            # Format: WR-YYYYMMDD-XXXX
            from datetime import datetime
            date_str = datetime.now().strftime('%Y%m%d')
            random_suffix = str(uuid.uuid4())[:4].upper()
            self.report_id = f"WR-{date_str}-{random_suffix}"
        super().save(*args, **kwargs)
    
    def mark_as_sent(self):
        """Mark report as successfully sent"""
        self.status = 'sent'
        self.sent_at = timezone.now()
        self.error_message = ''
        self.save()
    
    def mark_as_failed(self, error_message):
        """Mark report as failed with error message"""
        self.status = 'failed'
        self.error_message = error_message
        self.save()
    
    def get_recipients_list(self):
        """Return list of recipient emails"""
        return [email.strip() for email in self.recipients.split(',') if email.strip()]
    
    def get_cc_recipients_list(self):
        """Return list of CC recipient emails"""
        if self.cc_recipients:
            return [email.strip() for email in self.cc_recipients.split(',') if email.strip()]
        return []


class StoreOrderAssignment(auto_prefetch.Model):
    """
    Model for tracking assignment of material orders to stores staff by stores management.
    Implements the stores management workflow where:
    1. All material release requests first come to stores management
    2. Store managers assign requests to specific stores staff
    3. Assigned staff can then process the orders for transportation
    """
    # The material order being assigned
    material_order = auto_prefetch.ForeignKey(
        MaterialOrder,
        on_delete=models.CASCADE,
        related_name='store_assignments',
        help_text="Material order being assigned to stores staff"
    )
    
    # Assignment details
    assigned_to = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='assigned_store_orders',
        help_text="Stores staff member this order is assigned to"
    )
    assigned_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='store_assignments_made',
        help_text="Store manager who made the assignment"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    # Status tracking
    STATUS_CHOICES = [
        ('Pending', 'Pending Assignment'),
        ('Assigned', 'Assigned to Staff'),
        ('In Progress', 'In Progress'),
        ('Completed', 'Completed'),
        ('Reassigned', 'Reassigned'),
    ]
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='Pending',
        help_text="Current status of this assignment"
    )
    
    # Notes
    assignment_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Notes from store manager about this assignment"
    )
    completion_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Notes from stores staff upon completion"
    )
    
    # Timestamps
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the stores staff started working on this"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the assignment was completed"
    )
    
    # Tracking
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-assigned_at']
        verbose_name = 'Store Order Assignment'
        verbose_name_plural = 'Store Order Assignments'
        permissions = [
            ('can_assign_orders', 'Can assign orders to stores staff'),
            ('can_view_all_assignments', 'Can view all order assignments'),
        ]
    
    def __str__(self):
        if self.assigned_to:
            return f"Order {self.material_order.request_code} → {self.assigned_to.username}"
        return f"Order {self.material_order.request_code} (Unassigned)"
    
    def mark_in_progress(self, user=None):
        """Mark assignment as in progress"""
        self.status = 'In Progress'
        self.started_at = timezone.now()
        if user:
            self.material_order.last_updated_by = user
            self.material_order.save()
        self.save()
    
    def mark_completed(self, notes=None, user=None):
        """Mark assignment as completed"""
        self.status = 'Completed'
        self.completed_at = timezone.now()
        if notes:
            self.completion_notes = notes
        if user:
            self.material_order.last_updated_by = user
            self.material_order.save()
        self.save()
    
    def reassign(self, new_staff, reassigned_by, notes=None):
        """Reassign to a different stores staff member"""
        old_staff = self.assigned_to
        self.assigned_to = new_staff
        self.assigned_by = reassigned_by
        self.status = 'Reassigned'
        
        # Add reassignment note
        reassignment_note = f"Reassigned from {old_staff.username if old_staff else 'unassigned'} to {new_staff.username} by {reassigned_by.username}"
        if notes:
            reassignment_note += f"\nReason: {notes}"
        
        if self.assignment_notes:
            self.assignment_notes += f"\n\n{reassignment_note}"
        else:
            self.assignment_notes = reassignment_note
        
        self.save()


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

