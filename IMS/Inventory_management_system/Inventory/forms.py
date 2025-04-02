from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import Category, Unit, InventoryItem, MaterialOrder, Profile, ReportSubmission, MaterialTransport, ReleaseLetter
from django.forms import ModelForm, formset_factory, modelformset_factory
from django.core.validators import FileExtensionValidator

class UserRegistration(UserCreationForm):
    email = forms.EmailField(required=True, help_text='Required. Enter a valid email address.')

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['name', 'quantity', 'category', 'unit', 'code']

# Create a formset that allows an unlimited number of forms
InventoryItemFormSet = formset_factory(InventoryItemForm, extra=1, can_delete=True)


class MaterialOrderForm(forms.ModelForm):
    name = forms.ModelChoiceField(
        queryset=InventoryItem.objects.all(),
        to_field_name="name",
        empty_label="-- Choose Material --",
        widget=forms.Select(attrs={'class': 'form-control material-select'})
    )

    class Meta:
        model = MaterialOrder
        fields = [
            'name', 'quantity', 'region', 'district', 'community', 
            'consultant', 'contractor', 'package_number'
        ]
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'region': forms.TextInput(attrs={'class': 'form-control'}),
            'district': forms.TextInput(attrs={'class': 'form-control'}),
            'community': forms.TextInput(attrs={'class': 'form-control'}),
            'consultant': forms.TextInput(attrs={'class': 'form-control'}),
            'contractor': forms.TextInput(attrs={'class': 'form-control'}),
            'package_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            if not user.is_superuser:
                self.fields['name'].queryset = InventoryItem.objects.filter(group__in=user.groups.all())
            else:
                self.fields['name'].queryset = InventoryItem.objects.all()

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
        if user:
            if not user.is_superuser:
                self.fields['name'].queryset = InventoryItem.objects.filter(group__in=user.groups.all())
            else:
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