from django import forms
from django.forms import ModelForm, inlineformset_factory
from django.utils import timezone
from django.core.validators import FileExtensionValidator

from .models import (
    Transporter, 
    TransportVehicle, 
    MaterialTransport,
    MaterialOrder
)


class TransporterForm(forms.ModelForm):
    """Form for adding/editing transport companies."""
    class Meta:
        model = Transporter
        fields = [
            'name', 
            'contact_person', 
            'email', 
            'phone', 
            'address', 
            'is_active', 
            'notes'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }


class TransportVehicleForm(forms.ModelForm):
    """Form for adding/editing transport vehicles."""
    class Meta:
        model = TransportVehicle
        fields = [
            'transporter',
            'registration_number',
            'vehicle_type',
            'capacity',
            'is_active',
            'notes'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 2}),
        }


class TransportAssignmentForm(forms.ModelForm):
    """Form for assigning a transporter to a material order."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set the queryset for the vehicle field based on the selected transporter
        if 'transporter' in self.data:
            try:
                transporter_id = int(self.data.get('transporter'))
                self.fields['vehicle'].queryset = TransportVehicle.objects.filter(
                    transporter_id=transporter_id,
                    is_active=True
                ).order_by('registration_number')
            except (ValueError, TypeError):
                pass
        elif self.instance and self.instance.transporter_id:
            self.fields['vehicle'].queryset = TransportVehicle.objects.filter(
                transporter_id=self.instance.transporter_id,
                is_active=True
            ).order_by('registration_number')
        else:
            self.fields['vehicle'].queryset = TransportVehicle.objects.none()
    
    class Meta:
        model = MaterialTransport
        fields = [
            'transporter',
            'vehicle',
            'driver_name',
            'driver_phone',
            'waybill_number',
            'tracking_url',
            'notes'
        ]
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 3}),
            'tracking_url': forms.URLInput(attrs={'placeholder': 'https://'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        transporter = cleaned_data.get('transporter')
        vehicle = cleaned_data.get('vehicle')
        
        # Ensure the selected vehicle belongs to the selected transporter
        if transporter and vehicle and vehicle.transporter != transporter:
            raise forms.ValidationError(
                'The selected vehicle does not belong to the selected transporter.'
            )
        
        return cleaned_data


class TransporterImportForm(forms.Form):
    """Form for importing transporters from an Excel file."""
    file = forms.FileField(
        label='Excel File',
        help_text='Upload an Excel file (.xlsx) with transporter information.',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
    )
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            try:
                # Try to read the Excel file to validate it
                import pandas as pd
                pd.read_excel(file)
                file.seek(0)  # Reset file pointer
            except Exception as e:
                raise forms.ValidationError(f'Error reading Excel file: {str(e)}')
        return file


class TransportStatusUpdateForm(forms.ModelForm):
    """Form for updating the status of a transport."""
    class Meta:
        model = MaterialTransport
        fields = ['status', 'notes']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show relevant status options based on current status
        if self.instance and self.instance.status:
            current_status = self.instance.status
            status_choices = dict(self.fields['status'].choices)
            
            # Define allowed next statuses based on current status
            allowed_next_statuses = {
                'Assigned': ['Loading', 'Cancelled'],
                'Loading': ['Loaded', 'Cancelled'],
                'Loaded': ['In Transit', 'Cancelled'],
                'In Transit': ['Delivered', 'Cancelled'],
                'Delivered': ['Completed', 'Cancelled'],
            }
            
            if current_status in allowed_next_statuses:
                allowed = allowed_next_statuses[current_status]
                self.fields['status'].choices = [
                    (status, label) 
                    for status, label in self.fields['status'].choices 
                    if status in allowed
                ]


class MaterialOrderFilterForm(forms.Form):
    """Form for filtering material orders in the transporter assignment view."""
    STATUS_CHOICES = [
        ('', 'All Statuses'),
        ('Approved', 'Approved'),
        ('In Progress', 'In Progress'),
        ('Ready for Pickup', 'Ready for Pickup'),
    ]
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search by name, code, or request code...',
            'class': 'form-control'
        })
    )
    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'From date'
        })
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'To date'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        
        if date_from and date_to and date_from > date_to:
            self.add_error('date_to', 'End date cannot be before start date')
        
        return cleaned_data
