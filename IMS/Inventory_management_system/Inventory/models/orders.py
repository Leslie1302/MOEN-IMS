from django.db import models
import auto_prefetch
from django.contrib.auth.models import User, Group
from django.utils import timezone
from django.core.validators import FileExtensionValidator
import uuid
from .utils import generate_abbreviation
from .inventory import Category, Unit, Warehouse
from .suppliers import Supplier
from .projects import BillOfQuantity

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
        BillOfQuantity,
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


class MaterialOrder(auto_prefetch.Model):
    """
    Model representing a material order request (release or receipt).
    """
    # Basic information
    name = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)  # Changed to DecimalField for precision
    category = auto_prefetch.ForeignKey('Inventory.Category', on_delete=models.SET_NULL, blank=True, null=True)
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
        default='Draft',
        db_index=True
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
        help_text="Store Officer assigned to process this order"
    )
    assigned_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the order was assigned to a store officer"
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
    
    # Project type for material requests
    PROJECT_TYPE_CHOICES = [
        ('SHEP', 'SHEP'),
        ('COST', 'Cost-sharing'),
        ('SPEC', 'Special/other'),
    ]
    project_type = models.CharField(
        max_length=10,
        choices=PROJECT_TYPE_CHOICES,
        default='SHEP',
        help_text="Type of project this request is for"
    )
    
    # Requestor tracking for unique package generation
    requestor = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Person/factory/institute making the request"
    )
    requestor_abbr = models.CharField(
        max_length=10,
        blank=True,
        editable=False,
        help_text="Auto-generated requestor abbreviation"
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
        ReleaseLetter,
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
        
        # Auto-generate requestor abbreviation
        if self.requestor and not self.requestor_abbr:
            self.requestor_abbr = generate_abbreviation(self.requestor)
        
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


class MaterialOrderAudit(auto_prefetch.Model):
    order = auto_prefetch.ForeignKey(MaterialOrder, on_delete=models.CASCADE)
    action = models.CharField(max_length=100)
    performed_by = auto_prefetch.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.action} on {self.order.id} by {self.performed_by}"


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


class SiteReceipt(auto_prefetch.Model):
    """
    Model for consultants to log material receipts at project sites.
    Links to MaterialTransport to update delivery status.
    """
    material_transport = auto_prefetch.OneToOneField(
        'Inventory.MaterialTransport',
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
        help_text="Upload the endorsed waybill PDF",
        null=True,
        blank=True
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
