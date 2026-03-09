"""Project, BOQ, site receipt, and overissuance forms."""
from django import forms
from django.forms import modelformset_factory

from ..models import (
    BillOfQuantity, BoQOverissuanceJustification, InventoryItem,
    ObsoleteMaterial, Project, SiteReceipt,
)


class ProjectForm(forms.ModelForm):
    """Form for creating and editing projects, tailored for SHEP and turnkey projects."""
    class Meta:
        model = Project
        fields = [
            'name', 'code', 'description', 'project_type', 'phase', 
            'status', 'project_manager', 'consultant', 'contractor', 
            'start_date', 'planned_end_date', 'total_budget'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter project name'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., SHEP5-AS-01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'project_type': forms.Select(attrs={'class': 'form-select'}),
            'phase': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., SHEP-4'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'project_manager': forms.Select(attrs={'class': 'form-select'}),
            'consultant': forms.TextInput(attrs={'class': 'form-control'}),
            'contractor': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'planned_end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'total_budget': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['project_type'].initial = 'SHEP'


class SiteReceiptForm(forms.ModelForm):
    """Form for consultants to log site receipts with waybill and photos"""
    
    class Meta:
        model = SiteReceipt
        fields = ['received_quantity', 'acknowledgement_sheet', 'site_photos', 'condition', 'notes']
        widgets = {
            'received_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'acknowledgement_sheet': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'application/pdf,image/*'
            }),
            'site_photos': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'condition': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes about the delivery condition, location, etc.'
            })
        }
    
    def __init__(self, *args, **kwargs):
        transport = kwargs.pop('transport', None)
        super().__init__(*args, **kwargs)
        
        if transport:
            self.fields['received_quantity'].initial = transport.quantity
            self.fields['received_quantity'].help_text = f"Expected: {transport.quantity} {transport.unit}"


class BoQOverissuanceJustificationForm(forms.ModelForm):
    """Form for submitting justification for Bill of Quantity overissuances"""
    class Meta:
        model = BoQOverissuanceJustification
        fields = ['justification_category', 'reason', 'supporting_documents']
        widgets = {
            'justification_category': forms.Select(attrs={
                'class': 'form-control',
                'required': True
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Provide a detailed explanation for the overissuance...',
                'required': True
            }),
            'supporting_documents': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'List any supporting documents, file references, or related documentation...'
            })
        }
        labels = {
            'justification_category': 'Category of Justification',
            'reason': 'Detailed Reason for Overissuance',
            'supporting_documents': 'Supporting Documents/References'
        }
        help_texts = {
            'justification_category': 'Select the category that best describes the reason for overissuance',
            'reason': 'Provide a comprehensive explanation including when and why the overissuance occurred',
            'supporting_documents': 'Optional: Reference any documents that support this justification'
        }
    
    def __init__(self, *args, **kwargs):
        self.boq_item = kwargs.pop('boq_item', None)
        super().__init__(*args, **kwargs)
        
        self.fields['justification_category'].required = True
        self.fields['reason'].required = True
        self.fields['supporting_documents'].required = False
    
    def clean_reason(self):
        """Validate that the reason is sufficiently detailed"""
        reason = self.cleaned_data.get('reason')
        if reason and len(reason.strip()) < 20:
            raise forms.ValidationError(
                "Please provide a more detailed explanation (at least 20 characters)."
            )
        return reason


class BillOfQuantityForm(forms.ModelForm):
    """Form for editing Bill of Quantity items.
    Used for bulk editing BOQ entries by superusers."""
    class Meta:
        model = BillOfQuantity
        fields = [
            'region', 'district', 'community', 'consultant', 'contractor',
            'package_number', 'material_description', 'item_code',
            'contract_quantity', 'quantity_received', 'warehouse'
        ]
        widgets = {
            'region': forms.TextInput(attrs={'class': 'form-control'}),
            'district': forms.TextInput(attrs={'class': 'form-control'}),
            'community': forms.TextInput(attrs={'class': 'form-control'}),
            'consultant': forms.TextInput(attrs={'class': 'form-control'}),
            'contractor': forms.TextInput(attrs={'class': 'form-control'}),
            'package_number': forms.TextInput(attrs={'class': 'form-control'}),
            'material_description': forms.TextInput(attrs={'class': 'form-control'}),
            'item_code': forms.TextInput(attrs={'class': 'form-control'}),
            'contract_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'quantity_received': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
        }
        help_texts = {
            'quantity_received': 'Note: This value is automatically updated by site logs',
        }


BillOfQuantityFormSet = modelformset_factory(
    BillOfQuantity,
    form=BillOfQuantityForm,
    extra=0,
    can_delete=False
)


class ObsoleteMaterialForm(forms.ModelForm):
    """Form for registering obsolete materials.
    Auto-populates material code, unit, and category when material is selected.
    Shows serial number field for Energy Meters and Transformers."""
    material = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all(),
        empty_label="-- Select Material --",
        widget=forms.Select(attrs={'class': 'form-control material-select'}),
        help_text="Select the material to register as obsolete"
    )
    
    class Meta:
        model = ObsoleteMaterial
        fields = [
            'material', 'quantity', 'warehouse', 'serial_numbers',
            'reason_for_obsolescence', 'date_marked_obsolete', 
            'status', 'estimated_value', 'disposal_method', 
            'disposal_date', 'notes'
        ]
        widgets = {
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01',
                'min': '0'
            }),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
            'serial_numbers': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter serial numbers (one per line or comma-separated)'
            }),
            'reason_for_obsolescence': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Explain why this material is obsolete (e.g., damaged, expired, outdated, excess stock)'
            }),
            'date_marked_obsolete': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'estimated_value': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'disposal_method': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Auction, Scrap, Donation, etc.'
            }),
            'disposal_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Additional notes or comments'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['serial_numbers'].required = False
        self.fields['estimated_value'].required = False
        self.fields['disposal_method'].required = False
        self.fields['disposal_date'].required = False
        self.fields['notes'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        material = cleaned_data.get('material')
        
        if material:
            cleaned_data['material_name'] = material.name
            cleaned_data['material_code'] = material.code
            cleaned_data['unit'] = material.unit.name if material.unit else ''
            cleaned_data['category'] = material.category.name if material.category else ''
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if self.cleaned_data.get('material'):
            material = self.cleaned_data['material']
            instance.material_name = material.name
            instance.material_code = material.code
            instance.unit = material.unit.name if material.unit else ''
            instance.category = material.category.name if material.category else ''
        
        if commit:
            instance.save()
        return instance
