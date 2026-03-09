"""Supply contract, supplier, and invoice management forms."""
from django import forms
from django.forms import formset_factory
from django.core.validators import FileExtensionValidator

from ..models import (
    Supplier, SupplierPriceCatalog, SupplyContract, SupplyContractItem,
    SupplierInvoice, SupplierInvoiceItem,
)


class SupplierForm(forms.ModelForm):
    """Form for creating and editing suppliers"""
    class Meta:
        model = Supplier
        fields = ['name', 'code', 'registration_number', 'contact_person', 
                  'contact_phone', 'contact_email', 'address', 'rating', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Supplier Name'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'SUP-001'}),
            'registration_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Business Registration Number'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact Person Name'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+233...'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Physical Address'}),
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 5, 'step': 0.1}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes'}),
        }


class SupplierPriceCatalogForm(forms.ModelForm):
    """Form for adding/editing supplier prices"""
    class Meta:
        model = SupplierPriceCatalog
        fields = ['supplier', 'material', 'unit_rate', 'currency', 'effective_date', 
                  'expiry_date', 'minimum_order_quantity', 'warehouse', 'lead_time_days', 
                  'notes', 'is_active']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'material': forms.Select(attrs={'class': 'form-select'}),
            'unit_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': 0.01, 'min': 0, 'placeholder': 'Price per unit'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'GHS'}),
            'effective_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expiry_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'minimum_order_quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'lead_time_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'placeholder': 'Delivery days'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Pricing terms, conditions, or delivery notes'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'warehouse': 'Delivery Location (Warehouse)',
            'lead_time_days': 'Lead Time (Delivery Days)',
            'minimum_order_quantity': 'Minimum Order Quantity (MOQ)',
            'unit_rate': 'Unit Price',
        }
        help_texts = {
            'warehouse': 'Which warehouse will the supplier deliver to?',
            'lead_time_days': 'Number of days for supplier to deliver materials',
            'supplier': 'Third-party company that will supply the materials',
        }


class BulkPriceCatalogUploadForm(forms.Form):
    """Form for bulk uploading supplier prices via Excel"""
    excel_file = forms.FileField(
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])],
        help_text='Upload Excel file with columns: supplier_code, material_code, unit_rate, effective_date, expiry_date (optional)',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls'})
    )


class SupplyContractForm(forms.ModelForm):
    """Form for creating and editing supply contracts"""
    class Meta:
        model = SupplyContract
        fields = ['contract_number', 'title', 'supplier', 'contract_type', 'start_date', 
                  'end_date', 'total_estimated_value', 'currency', 'status', 
                  'terms_and_conditions', 'notes']
        widgets = {
            'contract_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CON-2025-001'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contract Title'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'contract_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'total_estimated_value': forms.NumberInput(attrs={'class': 'form-control', 'step': 0.01, 'min': 0}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'GHS'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'terms_and_conditions': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SupplyContractItemForm(forms.ModelForm):
    """Form for contract line items"""
    class Meta:
        model = SupplyContractItem
        fields = ['material', 'quantity', 'unit_rate', 'warehouse', 'notes']
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': 0.01, 'min': 0}),
            'unit_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': 0.01, 'min': 0}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }


SupplyContractItemFormSet = formset_factory(
    SupplyContractItemForm,
    extra=3,
    can_delete=True
)


class SupplierInvoiceForm(forms.ModelForm):
    """Form for creating and editing supplier invoices"""
    class Meta:
        model = SupplierInvoice
        fields = ['invoice_number', 'supplier', 'contract', 'invoice_date', 'due_date', 
                  'total_amount', 'currency', 'uploaded_document', 'notes']
        widgets = {
            'invoice_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'INV-2025-001'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'contract': forms.Select(attrs={'class': 'form-select'}),
            'invoice_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': 0.01, 'min': 0}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'value': 'GHS'}),
            'uploaded_document': forms.FileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class SupplierInvoiceItemForm(forms.ModelForm):
    """Form for invoice line items"""
    class Meta:
        model = SupplierInvoiceItem
        fields = ['material', 'material_order', 'quantity_invoiced', 'unit_rate_invoiced', 
                  'quantity_received', 'warehouse', 'discrepancy_notes']
        widgets = {
            'material': forms.Select(attrs={'class': 'form-select'}),
            'material_order': forms.Select(attrs={'class': 'form-select'}),
            'quantity_invoiced': forms.NumberInput(attrs={'class': 'form-control', 'step': 0.01}),
            'unit_rate_invoiced': forms.NumberInput(attrs={'class': 'form-control', 'step': 0.01}),
            'quantity_received': forms.NumberInput(attrs={'class': 'form-control', 'step': 0.01}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
            'discrepancy_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


SupplierInvoiceItemFormSet = formset_factory(
    SupplierInvoiceItemForm,
    extra=3,
    can_delete=True
)


class InvoiceVerificationForm(forms.Form):
    """Form for verifying invoices"""
    status = forms.ChoiceField(
        choices=[
            ('verified', 'Verified - Ready for Approval'),
            ('disputed', 'Disputed - Has Issues'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        required=True
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Verification notes'}),
        required=False
    )


class InvoiceApprovalForm(forms.Form):
    """Form for approving invoices for payment"""
    approved = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    payment_reference = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Payment reference number'})
    )
    notes = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Approval notes'}),
        required=False
    )
