from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import (
    Category, Unit, InventoryItem, MaterialOrder, Profile, ReportSubmission, 
    MaterialTransport, ReleaseLetter, Transporter, TransportVehicle, SiteReceipt, 
    Supplier, Warehouse, BoQOverissuanceJustification, BillOfQuantity,
    SupplierPriceCatalog, SupplyContract, SupplyContractItem,
    SupplierInvoice, SupplierInvoiceItem, ObsoleteMaterial, Project,
    SHEPCommunity
)
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
    
    def clean(self):
        """Validate that the combination of material code and warehouse is unique"""
        cleaned_data = super().clean()
        code = cleaned_data.get('code')
        warehouse = cleaned_data.get('warehouse')
        
        if code and warehouse:
            # Check if editing an existing item (will have an instance with pk)
            if self.instance and self.instance.pk:
                # Exclude current instance from uniqueness check
                if InventoryItem.objects.filter(code=code, warehouse=warehouse).exclude(pk=self.instance.pk).exists():
                    raise forms.ValidationError(
                        f"An item with material code '{code}' already exists in warehouse '{warehouse.name}'. "
                        "The combination of code and warehouse must be unique."
                    )
            else:
                # Creating new item
                if InventoryItem.objects.filter(code=code, warehouse=warehouse).exists():
                    raise forms.ValidationError(
                        f"An item with material code '{code}' already exists in warehouse '{warehouse.name}'. "
                        "The combination of code and warehouse must be unique."
                    )
        
        return cleaned_data

# Create a formset that allows an unlimited number of forms
InventoryItemFormSet = formset_factory(InventoryItemForm, extra=1, can_delete=True)


class MaterialOrderForm(forms.ModelForm):
    name = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all(),
        empty_label="-- Choose Material --",
        widget=forms.Select(attrs={'class': 'form-control material-select'})
    )
    
    # Project type selection
    project_type = forms.ChoiceField(
        choices=[('', '-- Select Project Type --')] + [
            ('SHEP', 'SHEP'),
            ('COST', 'Cost-sharing'),
            ('SPEC', 'Special/other'),
        ],
        required=True,
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_project_type'
        }),
        help_text="Select the type of project for this material request"
    )
    
    # Requestor field (required for uniqueness in package number generation)
    requestor = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter requestor name',
            'id': 'id_requestor'
        }),
        help_text="Person, factory, or institute making the request (used for package number generation)"
    )
    
    # Community field (for SHEP projects, cascading from district)
    community = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control shep-dropdown',
            'id': 'id_community'
        }),
        help_text="Select community (available after selecting district)"
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
    
    release_letter_quantity = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label="Authorized Quantity",
        help_text="The total quantity authorized by the letter",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    release_letter_material_type = forms.ChoiceField(
        required=False,
        choices=ReleaseLetter.MATERIAL_TYPE_CHOICES,
        label="Material Type",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    release_letter_project_phase = forms.CharField(
        required=False,
        max_length=100,
        label="Project Phase",
        help_text="e.g., SHEP-4",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = MaterialOrder
        fields = [
            'name', 'quantity', 'project_type', 'requestor',
            'region', 'district', 'community',
            'consultant', 'contractor', 'package_number', 'warehouse'
        ]
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'region': forms.Select(attrs={'class': 'form-control shep-dropdown', 'id': 'id_region'}),
            'district': forms.Select(attrs={'class': 'form-control shep-dropdown', 'id': 'id_district'}),
            'consultant': forms.Select(attrs={'class': 'form-control boq-dropdown'}),
            'contractor': forms.Select(attrs={'class': 'form-control boq-dropdown'}),
            'package_number': forms.Select(attrs={'class': 'form-control boq-dropdown', 'id': 'id_package_number'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Show all inventory items to all users for transparency
        self.fields['name'].queryset = InventoryItem.objects.all()
        
        # Import models for dropdown population
        from .models import BillOfQuantity, SHEPCommunity
        
        # Get regions from SHEP communities (for unified cascading)
        shep_regions = SHEPCommunity.objects.filter(is_active=True).values_list('region', flat=True).distinct().order_by('region')
        
        # Get distinct values from BOQ for backward compatibility
        boq_regions = BillOfQuantity.objects.values_list('region', flat=True).distinct().order_by('region')
        districts = BillOfQuantity.objects.values_list('district', flat=True).distinct().order_by('district')
        consultants = BillOfQuantity.objects.values_list('consultant', flat=True).distinct().order_by('consultant')
        contractors = BillOfQuantity.objects.values_list('contractor', flat=True).distinct().order_by('contractor')
        package_numbers = BillOfQuantity.objects.values_list('package_number', flat=True).distinct().order_by('package_number')
        
        # Combine regions (SHEP + BOQ), removing duplicates
        all_regions = list(set(list(shep_regions) + list(boq_regions)))
        all_regions = [r for r in all_regions if r]
        all_regions.sort()
        
        # Convert to choices format
        self.fields['region'].widget.choices = [('', '-- Select Region --')] + [(r, r) for r in all_regions]
        self.fields['district'].widget.choices = [('', '-- Select District --')] + [(d, d) for d in districts if d]
        self.fields['community'].widget.choices = [('', '-- Select Community --')]
        self.fields['consultant'].widget.choices = [('', '-- Select Consultant --')] + [(c, c) for c in consultants if c]
        self.fields['contractor'].widget.choices = [('', '-- Select Contractor --')] + [(c, c) for c in contractors if c]
        self.fields['package_number'].widget.choices = [('', '-- Select Package Number --')] + [(p, p) for p in package_numbers if p]
    
    def clean(self):
        cleaned_data = super().clean()
        project_type = cleaned_data.get('project_type')
        requestor = cleaned_data.get('requestor')
        
        # Requestor is required for Cost-sharing and Special projects
        if project_type in ['COST', 'SPEC'] and not requestor:
            self.add_error('requestor', 'Requestor is required for Cost-sharing and Special projects.')
        
        return cleaned_data
    
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
        help_text='Upload an Excel file with material request data. For Release: name, quantity, region, district, community, consultant, contractor, package_number, warehouse. For Receipt: name, quantity, warehouse. Note: Priority is set via the form field below and applies to all items. The community field is required for proper tracking.',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
    )
    request_type = forms.ChoiceField(
        choices=MaterialOrder.REQUEST_TYPE_CHOICES,
        initial='Release',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Type of request (Release/Return)'
    )
    priority = forms.ChoiceField(
        choices=[
            ('Low', 'Low'),
            ('Medium', 'Medium'),
            ('High', 'High'),
            ('Urgent', 'Urgent')
        ],
        initial='Medium',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Priority level for all items in this bulk upload'
    )
    release_letter_pdf = forms.FileField(
        required=False,
        label="Release Letter (PDF)",
        help_text="Upload the signed release letter for these material requests (optional)",
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
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
    
    release_letter_quantity = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label="Authorized Quantity",
        help_text="The total quantity authorized by the letter",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    
    release_letter_material_type = forms.ChoiceField(
        required=False,
        choices=ReleaseLetter.MATERIAL_TYPE_CHOICES,
        label="Material Type",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    release_letter_project_phase = forms.CharField(
        required=False,
        max_length=100,
        label="Project Phase",
        help_text="e.g., SHEP-4",
        widget=forms.TextInput(attrs={'class': 'form-control'})
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
                
                # Check required columns based on request type
                # We'll validate this later when request_type is available
                # For now, just check that 'name' and 'quantity' exist
                basic_required = ['name', 'quantity']
                missing_columns = [col for col in basic_required if col not in df.columns]
                if missing_columns:
                    raise forms.ValidationError(
                        f"Missing required columns in Excel file: {', '.join(missing_columns)}"
                    )
                
                # Filter out rows with zero or negative quantities
                initial_count = len(df)
                df = df[df['quantity'] > 0]
                
                # Check if any valid rows remain after filtering
                if len(df) == 0:
                    raise forms.ValidationError("No items with positive quantities found in the Excel file.")
                
                # Store the cleaned data for later use
                self.cleaned_data['df'] = df
                
                # Store info about filtered rows for user feedback
                filtered_count = initial_count - len(df)
                if filtered_count > 0:
                    self.cleaned_data['filtered_rows'] = filtered_count
                
            except Exception as e:
                raise forms.ValidationError(f"Error reading Excel file: {str(e)}")
        
        return file
    
    def clean(self):
        cleaned_data = super().clean()
        df = cleaned_data.get('df')
        request_type = cleaned_data.get('request_type')
        
        if df is not None and request_type:
            # Validate columns based on request type
            if request_type == 'Release':
                # community field removed - package-based tracking only
                required_columns = ['name', 'quantity', 'region', 'district', 
                                  'consultant', 'contractor', 'package_number', 'warehouse']
            else:  # Receipt
                required_columns = ['name', 'quantity', 'warehouse']
            
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise forms.ValidationError(
                    f"Missing required columns for {request_type} request: {', '.join(missing_columns)}"
                )
        
        return cleaned_data


class MaterialReceiptForm(forms.ModelForm):
    name = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all(),
        empty_label="-- Choose Material --",
        widget=forms.Select(attrs={'class': 'form-control material-select'})
    )

    class Meta:
        model = MaterialOrder
        fields = ['name', 'quantity', 'supplier', 'warehouse']  # Materials, Quantity, Supplier, and Warehouse
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'supplier': forms.Select(attrs={'class': 'form-control'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        # Show all inventory items to all users for transparency
        self.fields['name'].queryset = InventoryItem.objects.all()
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True)
        self.fields['supplier'].required = False
        self.fields['warehouse'].required = False

MaterialReceiptFormSet = formset_factory(MaterialReceiptForm, extra=1, can_delete=True)


class ReportSubmissionForm(forms.ModelForm):
    class Meta:
        model = ReportSubmission
        fields = [
            'region',
            'district',
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
    total_quantity = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        label="Total Authorized Quantity",
        help_text="The total quantity of material authorized by this letter",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'})
    )
    material_type = forms.ChoiceField(
        choices=ReleaseLetter.MATERIAL_TYPE_CHOICES,
        label="Material Type",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    project_phase = forms.CharField(
        required=False,
        max_length=100,
        label="Project Phase",
        help_text="e.g., SHEP-4, Turnkey Phase 2",
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
        fields = ['request_code', 'title', 'total_quantity', 'material_type', 'project_phase', 'pdf_file', 'notes']

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
        # Prioritize SHEP as the default project type if it's a new project
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
            # Set the expected quantity as the default
            self.fields['received_quantity'].initial = transport.quantity
            # Add transport info to help text
            self.fields['received_quantity'].help_text = f"Expected: {transport.quantity} {transport.unit}"


class BoQOverissuanceJustificationForm(forms.ModelForm):
    """
    Form for submitting justification for Bill of Quantity overissuances
    """
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
        
        # Make fields required
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


# ============================================================================
# Supply Contract Management Forms
# ============================================================================

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


# Create formset for contract items
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


# Create formset for invoice items
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


class BulkUserUploadForm(forms.Form):
    """Form for uploading Excel file to create users in bulk"""
    excel_file = forms.FileField(
        label='Upload Excel File',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])],
        help_text='Upload an Excel file with columns: username, name, email',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.xlsx,.xls'})
    )
    user_group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        label='Assign to Group (Optional)',
        help_text='Select a group to assign all users to',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    send_welcome_email = forms.BooleanField(
        required=False,
        initial=True,
        label='Send welcome email with credentials',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    def clean_excel_file(self):
        """Validate and parse the Excel file"""
        excel_file = self.cleaned_data.get('excel_file')
        if not excel_file:
            return excel_file
        
        try:
            # Read Excel file
            df = pd.read_excel(excel_file)
            
            # Check required columns
            required_columns = ['username', 'name', 'email']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise forms.ValidationError(
                    f"Missing required columns: {', '.join(missing_columns)}. "
                    f"Required columns are: {', '.join(required_columns)}"
                )
            
            # Check for empty DataFrame
            if df.empty:
                raise forms.ValidationError("The Excel file is empty. Please add user data.")
            
            # Remove rows with missing username or email
            df_clean = df.dropna(subset=['username', 'email'])
            
            if len(df_clean) == 0:
                raise forms.ValidationError("No valid user records found. Username and email are required.")
            
            # Store cleaned DataFrame in form for later use
            self.cleaned_data['df'] = df_clean
            
            # Store count of filtered rows
            filtered_count = len(df) - len(df_clean)
            if filtered_count > 0:
                self.cleaned_data['filtered_rows'] = filtered_count
            
        except pd.errors.EmptyDataError:
            raise forms.ValidationError("The Excel file is empty or corrupted.")
        except Exception as e:
            raise forms.ValidationError(f"Error reading Excel file: {str(e)}")
        
        return excel_file


class ExcelUserImportForm(forms.Form):
    """
    Form for importing users from Excel files.
    """
    excel_file = forms.FileField(
        label='Excel File',
        help_text='Upload an Excel file (.xlsx) with columns: username, name, email',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
    )
    
    default_group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        empty_label="No default group",
        help_text='Optional: Assign all imported users to this group'
    )
    
    send_email_notifications = forms.BooleanField(
        required=False,
        initial=False,
        help_text='Send email notifications to users with their login credentials (requires email configuration)'
    )
    
    def clean_excel_file(self):
        """
        Validate the uploaded Excel file format and basic structure.
        """
        excel_file = self.cleaned_data['excel_file']
        
        # Check file size (limit to 10MB)
        if excel_file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File size must be less than 10MB.")
        
        try:
            # Read Excel file to validate structure
            df = pd.read_excel(excel_file)
            
            # Reset file pointer for later use
            excel_file.seek(0)
            
            # Check if file is empty
            if df.empty:
                raise forms.ValidationError("The Excel file is empty.")
            
            # Check for required columns
            required_columns = ['username', 'name', 'email']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise forms.ValidationError(
                    f"Missing required columns: {', '.join(missing_columns)}. "
                    f"Required columns are: {', '.join(required_columns)}"
                )
            
            # Check if there's any data after removing empty rows
            df_clean = df.dropna(how='all')
            if df_clean.empty:
                raise forms.ValidationError("No valid data found in the Excel file.")
            
            # Basic validation of data types
            row_count = len(df_clean)
            if row_count > 1000:
                raise forms.ValidationError(
                    f"Too many rows ({row_count}). Maximum allowed is 1000 users per import."
                )
            
            # Store preview data for display
            self.cleaned_data['preview_data'] = df_clean.head(5).to_dict('records')
            self.cleaned_data['total_rows'] = row_count
            
        except pd.errors.EmptyDataError:
            raise forms.ValidationError("The Excel file is empty or corrupted.")
        except Exception as e:
            if "Missing required columns" in str(e) or "No valid data found" in str(e):
                raise
            raise forms.ValidationError(f"Error reading Excel file: {str(e)}")
        
        return excel_file


class BillOfQuantityForm(forms.ModelForm):
    """
    Form for editing Bill of Quantity items.
    Used for bulk editing BOQ entries by superusers.
    """
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


# Create a formset for bulk editing BOQ items
BillOfQuantityFormSet = modelformset_factory(
    BillOfQuantity,
    form=BillOfQuantityForm,
    extra=0,  # No extra blank forms
    can_delete=False  # Don't allow deletion through the formset
)


class ObsoleteMaterialForm(forms.ModelForm):
    """
    Form for registering obsolete materials.
    Auto-populates material code, unit, and category when material is selected.
    Shows serial number field for Energy Meters and Transformers.
    """
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
        # Make serial_numbers not required by default (it will be conditionally required via JavaScript)
        self.fields['serial_numbers'].required = False
        
        # Make some fields optional
        self.fields['estimated_value'].required = False
        self.fields['disposal_method'].required = False
        self.fields['disposal_date'].required = False
        self.fields['notes'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        material = cleaned_data.get('material')
        
        # Auto-populate material fields from the selected InventoryItem
        if material:
            cleaned_data['material_name'] = material.name
            cleaned_data['material_code'] = material.code
            cleaned_data['unit'] = material.unit.name if material.unit else ''
            cleaned_data['category'] = material.category.name if material.category else ''
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Populate the auto-fill fields from the cleaned data
        if self.cleaned_data.get('material'):
            material = self.cleaned_data['material']
            instance.material_name = material.name
            instance.material_code = material.code
            instance.unit = material.unit.name if material.unit else ''
            instance.category = material.category.name if material.category else ''
        
        if commit:
            instance.save()
        return instance


class SHEPCommunityForm(forms.ModelForm):
    """Form for creating and editing SHEP communities."""
    class Meta:
        model = SHEPCommunity
        fields = ['region', 'district', 'community', 'package_number', 'is_active']
        widgets = {
            'region': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter region name'}),
            'district': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter district name'}),
            'community': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter community name'}),
            'package_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter package number'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'region': 'Full region name (abbreviation will be auto-generated)',
            'district': 'Full district name (abbreviation will be auto-generated)',
            'community': 'Full community name (abbreviation will be auto-generated)',
            'package_number': 'SHEP package number for this community',
        }