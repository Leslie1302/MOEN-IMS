"""Admin and bulk-import forms — user uploads, community management, project site imports."""
from django import forms
from django.contrib.auth.models import Group
from django.core.validators import FileExtensionValidator
import pandas as pd

from ..models import Community, SHEPCommunity, ProjectType, MemberOfParliament, ProjectConsultant
from ..constants import PROJECT_TYPE_SHEP, active_project_types


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
            df = pd.read_excel(excel_file)
            
            required_columns = ['username', 'name', 'email']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise forms.ValidationError(
                    f"Missing required columns: {', '.join(missing_columns)}. "
                    f"Required columns are: {', '.join(required_columns)}"
                )
            
            if df.empty:
                raise forms.ValidationError("The Excel file is empty. Please add user data.")
            
            df_clean = df.dropna(subset=['username', 'email'])
            
            if len(df_clean) == 0:
                raise forms.ValidationError("No valid user records found. Username and email are required.")
            
            self.cleaned_data['df'] = df_clean
            
            filtered_count = len(df) - len(df_clean)
            if filtered_count > 0:
                self.cleaned_data['filtered_rows'] = filtered_count
            
        except pd.errors.EmptyDataError:
            raise forms.ValidationError("The Excel file is empty or corrupted.")
        except Exception as e:
            raise forms.ValidationError(f"Error reading Excel file: {str(e)}")
        
        return excel_file


class ExcelUserImportForm(forms.Form):
    """Form for importing users from Excel files."""
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
        """Validate the uploaded Excel file format and basic structure."""
        excel_file = self.cleaned_data['excel_file']
        
        if excel_file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File size must be less than 10MB.")
        
        try:
            df = pd.read_excel(excel_file)
            excel_file.seek(0)
            
            if df.empty:
                raise forms.ValidationError("The Excel file is empty.")
            
            required_columns = ['username', 'name', 'email']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise forms.ValidationError(
                    f"Missing required columns: {', '.join(missing_columns)}. "
                    f"Required columns are: {', '.join(required_columns)}"
                )
            
            df_clean = df.dropna(how='all')
            if df_clean.empty:
                raise forms.ValidationError("No valid data found in the Excel file.")
            
            row_count = len(df_clean)
            if row_count > 1000:
                raise forms.ValidationError(
                    f"Too many rows ({row_count}). Maximum allowed is 1000 users per import."
                )
            
            self.cleaned_data['preview_data'] = df_clean.head(5).to_dict('records')
            self.cleaned_data['total_rows'] = row_count
            
        except pd.errors.EmptyDataError:
            raise forms.ValidationError("The Excel file is empty or corrupted.")
        except Exception as e:
            if "Missing required columns" in str(e) or "No valid data found" in str(e):
                raise
            raise forms.ValidationError(f"Error reading Excel file: {str(e)}")
        
        return excel_file


class CommunityForm(forms.ModelForm):
    """
    Form for creating and editing communities. Project-agnostic; project_type
    is required, package_number is required only when project_type is SHEP
    (validated in clean()), and MP / constituency are used to drive the
    consignee resolver for Cost Sharing and Streetlights releases.

    Renamed from SHEPCommunityForm in Phase B.2. The legacy name remains as
    an alias below for backward compatibility with existing imports.
    """

    class Meta:
        model = Community
        fields = [
            'project_type', 'region', 'district', 'community',
            'package_number', 'constituency',
            'member_of_parliament', 'project_consultant',
            'is_active',
        ]
        widgets = {
            'project_type': forms.Select(attrs={
                'class': 'form-control',
                'data-role': 'community-project-type',
            }),
            'region': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter region name'}),
            'district': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter district name'}),
            'community': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter community name'}),
            'package_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. SHEP-PKG-024',
                'data-role': 'community-package-number',
            }),
            'constituency': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Ga East (used to look up MP if not set explicitly)',
            }),
            'member_of_parliament': forms.Select(attrs={'class': 'form-control'}),
            'project_consultant': forms.Select(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        help_texts = {
            'project_type': 'Which project this community is served under. Drives consignee routing.',
            'region': 'Full region name (abbreviation will be auto-generated).',
            'district': 'Full district name (abbreviation will be auto-generated).',
            'community': 'Full community name (abbreviation will be auto-generated).',
            'package_number': 'SHEP package number. Required for SHEP, ignored for other project types.',
            'constituency': 'Optional. Used by the system to find the MP for Cost Sharing / Streetlights releases when no explicit MP is set below.',
            'member_of_parliament': 'Optional explicit MP binding. Overrides the constituency-based lookup.',
            'project_consultant': 'Optional explicit consultant binding for SHEP. Overrides the region-based lookup.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Restrict the project_type dropdown to active types only.
        # Inactive (archived) types stay queryable on existing rows but
        # cannot be selected for new ones.
        self.fields['project_type'].queryset = active_project_types()
        self.fields['project_type'].empty_label = '— select project —'
        self.fields['project_type'].required = True

        # MP queryset: active only. Empty option allowed.
        self.fields['member_of_parliament'].queryset = (
            MemberOfParliament.objects.filter(active=True).order_by('region', 'constituency', 'name')
        )
        self.fields['member_of_parliament'].required = False
        self.fields['member_of_parliament'].empty_label = '— none / use constituency lookup —'

        # Consultant queryset: active only. Empty option allowed.
        self.fields['project_consultant'].queryset = (
            ProjectConsultant.objects.filter(active=True).order_by('region', 'name')
        )
        self.fields['project_consultant'].required = False
        self.fields['project_consultant'].empty_label = '— none / use region lookup —'

    def clean(self):
        cleaned = super().clean()
        project_type = cleaned.get('project_type')
        package_number = (cleaned.get('package_number') or '').strip()

        # SHEP requires package_number; other project types must NOT have one
        # so reports can keep package_number meaningful as a SHEP signal.
        if project_type and project_type.code == PROJECT_TYPE_SHEP:
            if not package_number:
                self.add_error(
                    'package_number',
                    'Package number is required for SHEP communities.',
                )
        else:
            if package_number:
                # Soft warning rather than hard error -- silently clear
                # rather than reject the whole form.
                cleaned['package_number'] = ''

        return cleaned


# Backward-compat alias. Existing views/templates import SHEPCommunityForm.
# Will be removed once all callers are updated.
SHEPCommunityForm = CommunityForm

class ExcelProjectSiteImportForm(forms.Form):
    """Form for importing Project Sites from Excel files."""
    excel_file = forms.FileField(
        label='Excel File',
        help_text='Upload the Project Sites Excel template file (.xlsx)',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls'])]
    )
    
    def clean_excel_file(self):
        excel_file = self.cleaned_data['excel_file']
        
        if excel_file.size > 10 * 1024 * 1024:
            raise forms.ValidationError("File size must be less than 10MB.")
            
        try:
            df = pd.read_excel(excel_file)
            excel_file.seek(0)
            
            if df.empty:
                raise forms.ValidationError("The Excel file is empty.")
                
            required_columns = ['Project Code', 'Site Code', 'Site Name', 'Region', 'District']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise forms.ValidationError(
                    f"Missing required columns: {', '.join(missing_columns)}."
                )
                
            df_clean = df.dropna(how='all')
            if df_clean.empty:
                raise forms.ValidationError("No valid data found in the Excel file.")
                
        except Exception as e:
            if "Missing required columns" in str(e) or "No valid data" in str(e) or "empty" in str(e):
                raise
            raise forms.ValidationError(f"Error reading Excel file: {str(e)}")
            
        return excel_file
