from django.db import models
import auto_prefetch
from django.contrib.auth.models import User
from .inventory import InventoryItem, Warehouse

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
        'Inventory.MaterialOrder',
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
