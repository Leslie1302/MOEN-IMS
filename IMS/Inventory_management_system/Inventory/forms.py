from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Category, Unit, InventoryItem, MaterialOrder, Profile, ReportSubmission, MaterialTransport, ReleaseLetter, Transporter, TransportVehicle, SiteReceipt
from django.forms import ModelForm, formset_factory, modelformset_factory
from django.core.validators import FileExtensionValidator
import pandas as pd
from io import BytesIO
from django.utils import timezone

class UserRegistration(UserCreationForm):
    email = forms.EmailField(required=True, help_text='Required. Enter a valid email address.')

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['name', 'quantity', 'category', 'unit', 'code', 'warehouse']

# Create a formset that allows an unlimited number of forms
InventoryItemFormSet = formset_factory(InventoryItemForm, extra=1, can_delete=True)


class MaterialOrderForm(forms.ModelForm):
    name = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all(),
        to_field_name="name",
        empty_label="-- Choose Material --",
        widget=forms.Select(attrs={'class': 'form-control material-select'})
    )
    
    release_letter_pdf = forms.FileField(
        required=False,
        label="Release Letter (PDF)",
        help_text="Upload the signed release letter for this material request (optional)",
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'application/pdf',
            'data-max-size': '10485760'  # 10MB limit
        })
    )
    
    release_letter_title = forms.CharField(
        required=False,
        max_length=200,
        label="Release Letter Title",
        help_text="Title for the release letter (optional, will auto-generate if not provided)",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = MaterialOrder
        fields = [
            'name', 'quantity', 'region', 'district', 'community', 
            'consultant', 'contractor', 'package_number', 'warehouse'
        ]
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'region': forms.TextInput(attrs={'class': 'form-control'}),
            'district': forms.TextInput(attrs={'class': 'form-control'}),
            'community': forms.TextInput(attrs={'class': 'form-control'}),
            'consultant': forms.TextInput(attrs={'class': 'form-control'}),
            'contractor': forms.TextInput(attrs={'class': 'form-control'}),
            'package_number': forms.TextInput(attrs={'class': 'form-control'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Show all inventory items to all users for transparency
        self.fields['name'].queryset = InventoryItem.objects.all()
    
    def save(self, commit=True):
        instance = super().save(commit=commit)
        return instance

MaterialOrderFormSet = formset_factory(MaterialOrderForm, extra=1, can_delete=True)


class UserUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['profile_picture']

class PasswordChangeForm(forms.Form):
    old_password = forms.CharField(widget=forms.PasswordInput)
    new_password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password != confirm_password:
            raise forms.ValidationError("New passwords do not match.")
        return cleaned_data

class ExcelUploadForm(forms.Form):
    file = forms.FileField()


class BulkMaterialRequestForm(forms.Form):
    file = forms.FileField(
        label='Excel File',
        help_text='Upload an Excel file with material request data. Required columns: name, quantity, region, district, community, consultant, contractor, package_number, warehouse',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
    )
    request_type = forms.ChoiceField(
        choices=MaterialOrder.REQUEST_TYPE_CHOICES,
        initial='Release',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Type of request (Release/Return)'
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            try:
                # Read the Excel file
                if file.name.endswith('.xlsx'):
                    df = pd.read_excel(file, engine='openpyxl')
                else:
                    df = pd.read_excel(file)
                
                # Check required columns
                required_columns = ['name', 'quantity', 'region', 'district', 'community', 
                                  'consultant', 'contractor', 'package_number', 'warehouse']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    raise forms.ValidationError(
                        f"Missing required columns in Excel file: {', '.join(missing_columns)}"
                    )
                
                # Validate quantity is positive
                if (df['quantity'] <= 0).any():
                    raise forms.ValidationError("Quantity must be a positive number for all items.")
                
                # Store the cleaned data for later use
                self.cleaned_data['df'] = df
                
            except Exception as e:
                raise forms.ValidationError(f"Error reading Excel file: {str(e)}")
        
        return file


class MaterialReceiptForm(forms.ModelForm):
    name = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all(),
        to_field_name="name",
        empty_label="-- Choose Material --",
        widget=forms.Select(attrs={'class': 'form-control material-select'})
    )

    class Meta:
        model = InventoryItem  # Using InventoryItem directly since we're updating it
        fields = ['name', 'quantity']  # Only need name and quantity for input
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Show all inventory items to all users for transparency
        self.fields['name'].queryset = InventoryItem.objects.all()

MaterialReceiptFormSet = formset_factory(MaterialReceiptForm, extra=1, can_delete=True)

class ReportSubmissionForm(forms.ModelForm):
    class Meta:
        model = ReportSubmission
        fields = [
            'region',
            'district',
            'community',
            'consultant',
            'contractor',
            'package_number',
            'material_description',
            'item_code',
            'contract_quantity',
            'quantity_received',
            'executive_summary',
            'monthly_report',
        ]
        widgets = {
            'executive_summary': forms.Textarea(attrs={'rows': 4}),
            'monthly_report': forms.FileInput(attrs={'accept': 'application/pdf'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print("Form initialized with fields:", self.fields)  # Debug print



class ReleaseLetterUploadForm(forms.ModelForm):
    """Form for uploading signed release letters."""
    request_code = forms.ChoiceField(
        label="Request Code",
        help_text="Select the request code that identifies the material request(s) this letter authorizes",
        widget=forms.Select(attrs={
            'class': 'form-select select2',
            'data-placeholder': 'Select a request code...'
        })
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        from .models import MaterialOrder
        import logging
        
        logger = logging.getLogger(__name__)
        
        # Get all distinct request codes from material orders that don't have a release letter yet
        request_codes = MaterialOrder.objects.filter(
            status__in=['Pending', 'Approved'],
            release_letter__isnull=True  # Only show orders without release letters
        ).values_list('request_code', flat=True).distinct()
        
        logger.info(f"Found {len(request_codes)} request codes: {list(request_codes)}")
        
        # Extract base request codes (part before the last dash)
        base_codes = set()
        for code in request_codes:
            if code:  # Only process non-None codes
                # Split by dash and join all parts except the last one (row number)
                parts = code.split('-')
                if len(parts) > 1:  
                    base_code = '-'.join(parts[:-1])
                    base_codes.add(base_code)
                    logger.debug(f"Extracted base code '{base_code}' from '{code}'")
                else:
                    # If no dash or only one part, use the whole code as base
                    base_codes.add(code)
                    logger.debug(f"Using full code '{code}' as base code")
        
        # Convert back to a sorted list
        base_codes = sorted(list(base_codes))
        logger.info(f"Final base codes: {base_codes}")
        
        # Create choices list with base request codes
        self.fields['request_code'].choices = [('', '-- Select a base request code --')] + [
            (code, code) for code in base_codes
        ]
        
        # Add a custom option to enter a new request code
        self.fields['request_code'].choices.append(('__new__', '-- Enter a new request code --'))
        
        # Add a field to store the full request code (hidden field for form submission)
        self.fields['full_request_code'] = forms.CharField(
            required=False,
            widget=forms.HiddenInput()
        )
    title = forms.CharField(
        max_length=200,
        help_text="A descriptive title for this release letter",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    pdf_file = forms.FileField(
        label="Signed Letter (PDF)",
        help_text="Upload the signed release letter in PDF format",
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
        widget=forms.FileInput(attrs={'class': 'form-control'})
    )
    notes = forms.CharField(
        required=False,
        help_text="Any additional notes or comments about this release letter",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3
        })
    )

    class Meta:
        model = ReleaseLetter
        fields = ['request_code', 'title', 'pdf_file', 'notes']

    def clean_request_code(self):
        """Validate that the request code exists and is in a valid status."""
        request_code = self.cleaned_data.get('request_code')
        if not request_code:
            raise forms.ValidationError("Request code is required.")
            
        # Check if there are any orders with this request code
        orders = MaterialOrder.objects.filter(request_code=request_code)
        if not orders.exists():
            raise forms.ValidationError(f"No material requests found with code: {request_code}")
            
        # Check if any order is already completed
        completed_orders = orders.filter(status='Completed')
        if completed_orders.exists():
            raise forms.ValidationError(
                f"Request {request_code} contains completed orders. Cannot upload a release letter for completed requests."
            )
            
        return request_code

    def save(self, commit=True):
        # Set the request code from the form data
        self.instance.request_code = self.cleaned_data['request_code']
        
        # Set the upload time if not already set
        if not self.instance.upload_time:
            self.instance.upload_time = timezone.now()
            
        # Save the release letter
        release_letter = super().save(commit=commit)
        
        # Update the status of all related orders to 'Approved' if they're not already completed
        if commit:
            orders = MaterialOrder.objects.filter(
                request_code=release_letter.request_code,
                status__in=['Pending', 'Approved']
            )
            orders.update(status='Approved')
            
        return release_letter
        return super().save(commit)


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
        # Limit choices to orders that are approved but not yet assigned for transport
        self.fields['material_order'].queryset = MaterialOrder.objects.filter(
            status__in=['Approved', 'In Progress']
        ).exclude(
            transports__status__in=['In Transit', 'Delivered', 'Completed']
        )
        
        # Set initial empty choices for vehicle field
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
                # Try to read the Excel file to validate it
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
        required=True  # Material order is required to auto-populate fields
    )
    letter = forms.ModelChoiceField(
        queryset=ReleaseLetter.objects.all(),
        label="Select Release Letter",
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True  # Assuming this is required
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
            # Pre-fill all fields if editing an existing record
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


class SiteReceiptForm(forms.ModelForm):
    """Form for consultants to log site receipts with waybill and photos"""
    
    class Meta:
        model = SiteReceipt
        fields = ['received_quantity', 'waybill_pdf', 'site_photos', 'condition', 'notes']
        widgets = {
            'received_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0'
            }),
            'waybill_pdf': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'application/pdf'
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
            # Set the expected quantity as the default
            self.fields['received_quantity'].initial = transport.quantity
            # Add transport info to help text
            self.fields['received_quantity'].help_text = f"Expected: {transport.quantity} {transport.unit}"