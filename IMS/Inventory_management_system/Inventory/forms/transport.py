"""Transport, transporter, and vehicle management forms."""
from django import forms
from django.core.validators import FileExtensionValidator
import pandas as pd

from ..models import (
    MaterialOrder, MaterialTransport, ReleaseLetter,
    Transporter, TransportVehicle,
)


class TransporterForm(forms.ModelForm):
    class Meta:
        model = Transporter
        fields = ['name', 'contact_person', 'email', 'phone', 'address', 'is_active', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class TransportVehicleForm(forms.ModelForm):
    class Meta:
        model = TransportVehicle
        fields = ['registration_number', 'vehicle_type', 'capacity', 'transporter', 'is_active', 'notes']
        widgets = {
            'registration_number': forms.TextInput(attrs={'class': 'form-control'}),
            'vehicle_type': forms.Select(attrs={'class': 'form-select'}),
            'capacity': forms.TextInput(attrs={'class': 'form-control'}),
            'transporter': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class TransportAssignmentForm(forms.ModelForm):
    class Meta:
        model = MaterialTransport
        fields = ['material_order', 'transporter', 'vehicle', 'driver_name', 'driver_phone', 'status', 'notes']
        widgets = {
            'material_order': forms.Select(attrs={'class': 'form-select'}),
            'transporter': forms.Select(attrs={'class': 'form-select', 'id': 'id_transporter'}),
            'vehicle': forms.Select(attrs={'class': 'form-select', 'id': 'id_vehicle'}),
            'driver_name': forms.TextInput(attrs={'class': 'form-control'}),
            'driver_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material_order'].queryset = MaterialOrder.objects.filter(
            status__in=['Approved', 'In Progress']
        ).exclude(
            transports__status__in=['In Transit', 'Delivered', 'Completed']
        )
        
        self.fields['vehicle'].queryset = TransportVehicle.objects.none()
        
        if 'transporter' in self.data:
            try:
                transporter_id = int(self.data.get('transporter'))
                self.fields['vehicle'].queryset = TransportVehicle.objects.filter(
                    transporter_id=transporter_id,
                    is_active=True
                ).order_by('registration_number')
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.transporter:
            self.fields['vehicle'].queryset = self.instance.transporter.vehicles.filter(
                is_active=True
            ).order_by('registration_number')


class TransporterImportForm(forms.Form):
    """Form for importing transporters from Excel."""
    file = forms.FileField(
        label='Excel File',
        help_text='Upload an Excel file with transporter data. Required columns: name, contact_person, email, phone, address',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
    )
    
    def clean_file(self):
        file = self.cleaned_data['file']
        if file:
            try:
                df = pd.read_excel(file)
                required_columns = ['name', 'contact_person', 'email', 'phone', 'address']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    raise forms.ValidationError(
                        f"The following required columns are missing: {', '.join(missing_columns)}"
                    )
                    
            except Exception as e:
                raise forms.ValidationError(f"Error reading Excel file: {str(e)}")
                
        return file


class MaterialTransportForm(forms.ModelForm):
    material_order = forms.ModelChoiceField(
        queryset=MaterialOrder.objects.all(),
        label="Select Material Order",
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_material_order'}),
        required=True
    )
    letter = forms.ModelChoiceField(
        queryset=ReleaseLetter.objects.all(),
        label="Select Release Letter",
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True
    )
    status = forms.ChoiceField(
        choices=MaterialTransport.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Transport Status"
    )
    material_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_material_name', 'readonly': 'readonly'}),
        label="Material Name",
        required=False
    )
    material_code = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_material_code', 'readonly': 'readonly'}),
        label="Material Code",
        required=False
    )
    recipient = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_recipient', 'readonly': 'readonly'}),
        label="Recipient",
        required=False
    )
    consultant = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_consultant', 'readonly': 'readonly'}),
        label="Consultant",
        required=False
    )
    region = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_region', 'readonly': 'readonly'}),
        label="Region",
        required=False
    )
    district = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_district', 'readonly': 'readonly'}),
        label="District",
        required=False
    )
    community = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_community', 'readonly': 'readonly'}),
        label="Community",
        required=False
    )
    package_number = forms.CharField(
        max_length=50,
        widget=forms.TextInput(attrs={'class': 'form-control', 'id': 'id_package_number', 'readonly': 'readonly'}),
        label="Package Number",
        required=False
    )

    class Meta:
        model = MaterialTransport
        fields = [
            'material_order', 'letter', 'status', 'material_name', 'material_code',
            'recipient', 'consultant', 'region', 'district', 'community',
            'package_number'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['material_order'].initial = self.instance.material_order
            self.fields['letter'].initial = self.instance.letter
            self.fields['status'].initial = self.instance.status
            self.fields['material_name'].initial = self.instance.material_name
            self.fields['material_code'].initial = self.instance.material_code
            self.fields['recipient'].initial = self.instance.recipient
            self.fields['consultant'].initial = self.instance.consultant
            self.fields['region'].initial = self.instance.region
            self.fields['district'].initial = self.instance.district
            self.fields['community'].initial = self.instance.community
            self.fields['package_number'].initial = self.instance.package_number

    def save(self, commit=True):
        """Save the form data, auto-populating fields from material_order."""
        instance = super().save(commit=False)
        if instance.material_order:
            instance.material_name = instance.material_order.name
            instance.material_code = instance.material_order.code
            instance.recipient = instance.material_order.contractor
            instance.consultant = instance.material_order.consultant
            instance.region = instance.material_order.region
            instance.district = instance.material_order.district
            instance.community = instance.material_order.community
            instance.package_number = instance.material_order.package_number
        if commit:
            instance.save()
        return instance
