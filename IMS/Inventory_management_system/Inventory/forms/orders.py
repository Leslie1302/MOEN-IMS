"""Material order, receipt, bulk request, report, and release letter forms."""
from django import forms
from django.forms import formset_factory
from django.core.validators import FileExtensionValidator
from django.utils import timezone
import pandas as pd

from ..models import (
    InventoryItem, MaterialOrder, ReportSubmission, ReleaseLetter,
    Supplier, Warehouse, BillOfQuantity, SHEPCommunity,
)
from ..models.suppliers import SupplyContract


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
            if self.instance and self.instance.pk:
                if InventoryItem.objects.filter(code=code, warehouse=warehouse).exclude(pk=self.instance.pk).exists():
                    raise forms.ValidationError(
                        f"An item with material code '{code}' already exists in warehouse '{warehouse.name}'. "
                        "The combination of code and warehouse must be unique."
                    )
            else:
                if InventoryItem.objects.filter(code=code, warehouse=warehouse).exists():
                    raise forms.ValidationError(
                        f"An item with material code '{code}' already exists in warehouse '{warehouse.name}'. "
                        "The combination of code and warehouse must be unique."
                    )
        
        return cleaned_data

InventoryItemFormSet = formset_factory(InventoryItemForm, extra=1, can_delete=True)


class MaterialOrderForm(forms.ModelForm):
    name = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all(),
        empty_label="-- Choose Material --",
        widget=forms.Select(attrs={'class': 'form-control material-select'})
    )
    
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
            'data-max-size': '10485760'
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
        self.fields['name'].queryset = InventoryItem.objects.all()
        
        shep_regions = SHEPCommunity.objects.filter(is_active=True).values_list('region', flat=True).distinct().order_by('region')
        boq_regions = BillOfQuantity.objects.values_list('region', flat=True).distinct().order_by('region')
        districts = BillOfQuantity.objects.values_list('district', flat=True).distinct().order_by('district')
        consultants = BillOfQuantity.objects.values_list('consultant', flat=True).distinct().order_by('consultant')
        contractors = BillOfQuantity.objects.values_list('contractor', flat=True).distinct().order_by('contractor')
        package_numbers = BillOfQuantity.objects.values_list('package_number', flat=True).distinct().order_by('package_number')
        
        all_regions = list(set(list(shep_regions) + list(boq_regions)))
        all_regions = [r for r in all_regions if r]
        all_regions.sort()
        
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
        
        if project_type in ['COST', 'SPEC'] and not requestor:
            self.add_error('requestor', 'Requestor is required for Cost-sharing and Special projects.')
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=commit)
        return instance


MaterialOrderFormSet = formset_factory(MaterialOrderForm, extra=1, can_delete=True)


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
            'data-max-size': '10485760'
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
                if file.name.endswith('.xlsx'):
                    df = pd.read_excel(file, engine='openpyxl')
                else:
                    df = pd.read_excel(file)
                
                basic_required = ['name', 'quantity']
                missing_columns = [col for col in basic_required if col not in df.columns]
                if missing_columns:
                    raise forms.ValidationError(
                        f"Missing required columns in Excel file: {', '.join(missing_columns)}"
                    )
                
                initial_count = len(df)
                df = df[df['quantity'] > 0]
                
                if len(df) == 0:
                    raise forms.ValidationError("No items with positive quantities found in the Excel file.")
                
                self.cleaned_data['df'] = df
                
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
            if request_type == 'Release':
                required_columns = ['name', 'quantity', 'region', 'district', 
                                  'consultant', 'contractor', 'package_number', 'warehouse']
            else:
                required_columns = ['name', 'quantity', 'warehouse']
            
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise forms.ValidationError(
                    f"Missing required columns for {request_type} request: {', '.join(missing_columns)}"
                )
        
        return cleaned_data


class MaterialReceiptForm(forms.ModelForm):
    """Material Receipt form.

    Mirrors the release-side contract linkage: a receipt now picks a
    Supplier, a SupplyContract drawn from that supplier, and a category
    that distinguishes a brand-new supply from an Overissuance Return.
    When the category is "Overissuance Return", the form also asks for
    the BoQ line being offset so the overissuance ledger can update on
    receipt completion.
    """

    name = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all(),
        empty_label="-- Choose Material --",
        widget=forms.Select(attrs={'class': 'form-control material-select'})
    )

    receipt_category = forms.ChoiceField(
        choices=MaterialOrder.RECEIPT_CATEGORY_CHOICES,
        initial='new_supply',
        required=True,
        widget=forms.Select(attrs={'class': 'form-control receipt-category-select'}),
        help_text=(
            'Pick "Overissuance Return" for materials being returned to '
            'offset an over-issued BoQ line.'
        ),
    )

    supply_contract = forms.ModelChoiceField(
        queryset=SupplyContract.objects.filter(status='active'),
        required=False,
        empty_label="— no contract / not applicable —",
        widget=forms.Select(attrs={'class': 'form-control supply-contract-select'}),
        help_text='Contract this receipt is drawn against.',
    )

    linked_boq_item = forms.ModelChoiceField(
        queryset=BillOfQuantity.objects.none(),
        required=False,
        empty_label="— pick over-issued BoQ line —",
        widget=forms.Select(attrs={'class': 'form-control boq-overissuance-select'}),
        help_text=(
            'Required for Overissuance Returns. quantity_received on this '
            'BoQ line will be reduced by the return quantity on completion.'
        ),
    )

    class Meta:
        model = MaterialOrder
        fields = [
            'name', 'quantity', 'supplier', 'supply_contract',
            'receipt_category', 'linked_boq_item', 'warehouse',
        ]
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'supplier': forms.Select(attrs={'class': 'form-control supplier-select'}),
            'warehouse': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['name'].queryset = InventoryItem.objects.all()
        self.fields['supplier'].queryset = Supplier.objects.filter(is_active=True)
        self.fields['warehouse'].queryset = Warehouse.objects.filter(is_active=True)
        self.fields['supplier'].required = False
        self.fields['warehouse'].required = False
        # Pre-load over-issued BoQ lines so the dropdown shows real options
        # the moment the user picks "Overissuance Return".
        over_issued_ids = [
            b.id for b in BillOfQuantity.objects.all()
            if (b.contract_quantity or 0) - (b.quantity_received or 0) < 0
        ]
        self.fields['linked_boq_item'].queryset = (
            BillOfQuantity.objects.filter(id__in=over_issued_ids)
            .order_by('package_number', 'material_description')
        )

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get('receipt_category')
        linked_boq = cleaned.get('linked_boq_item')
        contract = cleaned.get('supply_contract')
        supplier = cleaned.get('supplier')

        # Overissuance returns must point at a BoQ line so the ledger can be
        # updated on receipt; otherwise the return is silent.
        if category == 'overissuance_return' and not linked_boq:
            self.add_error(
                'linked_boq_item',
                'Pick the BoQ line being offset — overissuance returns must '
                'be linked into the BoQ ledger.',
            )

        # If a contract is picked, its supplier must match the supplier
        # field. This stops misposted receipts crossing supplier boundaries.
        if contract and supplier and contract.supplier_id != supplier.id:
            self.add_error(
                'supply_contract',
                f'Contract {contract.contract_number} belongs to '
                f'{contract.supplier.name}, not {supplier.name}.',
            )
        return cleaned


MaterialReceiptFormSet = formset_factory(MaterialReceiptForm, extra=1, can_delete=True)


class ReportSubmissionForm(forms.ModelForm):
    class Meta:
        model = ReportSubmission
        fields = [
            'region', 'district', 'community', 'consultant', 'contractor',
            'package_number', 'material_description', 'item_code',
            'contract_quantity', 'quantity_received',
            'executive_summary', 'monthly_report',
        ]
        widgets = {
            'executive_summary': forms.Textarea(attrs={'rows': 4}),
            'monthly_report': forms.FileInput(attrs={'accept': 'application/pdf'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Community is OPTIONAL: contracts are tracked per package, not per
        # community. Captured when known (it enriches the map / distribution
        # view), but reconciliation happens at the package level, so a blank
        # community must not block a submission.
        self.fields['community'].required = False


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
        
        import logging
        logger = logging.getLogger(__name__)
        
        # Broaden the filter so any order that hasn't yet been released or
        # cancelled shows up in the dropdown. The old filter (Pending|Approved
        # only) hid most real-world orders since the system rarely sits in
        # those two statuses for long.
        request_codes = MaterialOrder.objects.filter(
            release_letter__isnull=True,
        ).exclude(
            status__in=['Cancelled', 'Rejected'],
        ).values_list('request_code', flat=True).distinct()
        
        logger.info(f"Found {len(request_codes)} request codes: {list(request_codes)}")

        # Group request codes by batch base so a BULK upload is offered as a
        # single option (one release letter for the whole batch) while SINGLE
        # requests are offered individually.
        #
        # Codes are REQ-YYYYMMDD-NNNNNN for single requests (3 segments) and
        # REQ-YYYYMMDD-NNNNNN-1, -2, … for bulk rows (4 segments). We collapse
        # to the base ONLY when there are more than 3 segments and the last is
        # numeric — this captures the bulk row suffix without re-introducing the
        # old "REQ-YYYYMMDD" date-bucket over-grouping (the date/random parts of
        # a single request are left intact).
        def _base(code):
            parts = code.split('-')
            if len(parts) > 3 and parts[-1].isdigit():
                return '-'.join(parts[:-1])
            return code

        counts = {}
        for code in request_codes:
            if not code:
                continue
            b = _base(code)
            counts[b] = counts.get(b, 0) + 1

        choices = []
        for b in sorted(counts):
            n = counts[b]
            label = b if n <= 1 else f"{b}  (bulk batch — {n} items)"
            choices.append((b, label))
        logger.info(f"Final request-code options (grouped): {[c[0] for c in choices]}")

        self.fields['request_code'].choices = [('', '-- Select a request code --')] + choices
        self.fields['request_code'].choices.append(('__new__', '-- Enter a new request code --'))
        
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
        help_text="Upload the signed scan of the auto-generated release letter (QR-verified)",
        required=False,
        validators=[FileExtensionValidator(allowed_extensions=['pdf', 'png', 'jpg', 'jpeg'])],
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
            
        orders = MaterialOrder.objects.filter(request_code=request_code)
        if not orders.exists():
            raise forms.ValidationError(f"No material requests found with code: {request_code}")
            
        completed_orders = orders.filter(status='Completed')
        if completed_orders.exists():
            raise forms.ValidationError(
                f"Request {request_code} contains completed orders. Cannot upload a release letter for completed requests."
            )
            
        return request_code

    def save(self, commit=True):
        self.instance.request_code = self.cleaned_data['request_code']
        
        if not self.instance.upload_time:
            self.instance.upload_time = timezone.now()
            
        release_letter = super().save(commit=commit)
        
        if commit:
            orders = MaterialOrder.objects.filter(
                request_code=release_letter.request_code,
                status__in=['Pending', 'Approved']
            )
            orders.update(status='Approved')
            
        return release_letter
