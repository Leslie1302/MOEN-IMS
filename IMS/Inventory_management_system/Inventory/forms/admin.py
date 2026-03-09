"""Admin and bulk-import forms — user uploads, community management, project site imports."""
from django import forms
from django.contrib.auth.models import Group
from django.core.validators import FileExtensionValidator
import pandas as pd

from ..models import SHEPCommunity


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
