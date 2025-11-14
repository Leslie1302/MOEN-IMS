"""
Django admin interface for Excel user import functionality.
"""

from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
import os
import tempfile
from .user_import import ExcelUserImporter
from .forms import ExcelUserImportForm


class ExcelUserImportAdmin:
    """
    Admin interface for Excel user import functionality.
    """
    
    def get_urls(self):
        """Add custom URLs for user import functionality"""
        urls = [
            path('import-users/', self.import_users_view, name='admin_import_users'),
        ]
        return urls
    
    def import_users_view(self, request):
        """
        Handle Excel user import through admin interface.
        """
        if not request.user.is_superuser:
            messages.error(request, 'Only superusers can import users.')
            return redirect('admin:index')
        
        if request.method == 'POST':
            form = ExcelUserImportForm(request.POST, request.FILES)
            if form.is_valid():
                return self.process_excel_import(request, form)
        else:
            form = ExcelUserImportForm()
        
        context = {
            'title': 'Import Users from Excel',
            'form': form,
            'opts': User._meta,
            'has_change_permission': True,
            'available_groups': Group.objects.all(),
        }
        
        return render(request, 'admin/auth/user/import_users.html', context)
    
    def process_excel_import(self, request, form):
        """
        Process the Excel file and import users.
        """
        excel_file = form.cleaned_data['excel_file']
        default_group = form.cleaned_data.get('default_group')
        send_email = form.cleaned_data.get('send_email_notifications', False)
        
        # Save uploaded file temporarily
        temp_file = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as temp_file:
                for chunk in excel_file.chunks():
                    temp_file.write(chunk)
                temp_file_path = temp_file.name
            
            # Import users
            importer = ExcelUserImporter()
            results = importer.import_users_from_excel(
                temp_file_path, 
                default_group.name if default_group else None
            )
            
            # Display results
            if results['success_count'] > 0:
                success_msg = f"Successfully imported {results['success_count']} users."
                if results['created_users']:
                    # Create detailed success message with passwords
                    user_details = []
                    for user_info in results['created_users']:
                        user_details.append(
                            f"• {user_info['username']} ({user_info['email']}) - Password: {user_info['password']}"
                        )
                    
                    detailed_msg = success_msg + "\n\nCreated users:\n" + "\n".join(user_details)
                    detailed_msg += "\n\nIMPORTANT: Save these passwords and share them securely with users."
                    
                    messages.success(request, detailed_msg)
                else:
                    messages.success(request, success_msg)
            
            if results['error_count'] > 0:
                error_msg = f"Encountered {results['error_count']} errors during import."
                if results['errors']:
                    error_details = "\n".join([f"• {error}" for error in results['errors']])
                    error_msg += f"\n\nErrors:\n{error_details}"
                messages.error(request, error_msg)
            
            # Generate and offer download of detailed report
            if results['success_count'] > 0 or results['error_count'] > 0:
                report_content = importer.generate_import_report()
                
                # Store report in session for download
                request.session['import_report'] = report_content
                request.session['import_report_filename'] = f"user_import_report_{importer.import_results.get('timestamp', 'latest')}.txt"
                
                # Add download link message
                download_url = reverse('admin:download_import_report')
                download_link = format_html(
                    '<a href="{}" class="button">Download Detailed Report</a>',
                    download_url
                )
                messages.info(
                    request, 
                    format_html('Import completed. {} {}', 
                               'Click to download detailed report:', download_link)
                )
            
            return redirect('admin:auth_user_changelist')
            
        except Exception as e:
            messages.error(request, f'Import failed: {str(e)}')
            return redirect('admin:admin_import_users')
            
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass
    
    def download_report_view(self, request):
        """
        Download the import report.
        """
        report_content = request.session.get('import_report')
        filename = request.session.get('import_report_filename', 'user_import_report.txt')
        
        if not report_content:
            messages.error(request, 'No report available for download.')
            return redirect('admin:index')
        
        response = HttpResponse(report_content, content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Clear report from session after download
        if 'import_report' in request.session:
            del request.session['import_report']
        if 'import_report_filename' in request.session:
            del request.session['import_report_filename']
        
        return response


# Create instance for URL registration
excel_user_import_admin = ExcelUserImportAdmin()


def add_import_users_action(modeladmin, request, queryset):
    """
    Admin action to redirect to user import page.
    """
    return HttpResponseRedirect(reverse('admin:admin_import_users'))

add_import_users_action.short_description = "Import users from Excel file"


# Extend the existing CustomUserAdmin to add import functionality
def extend_user_admin():
    """
    Extend the existing User admin with import functionality.
    """
    from django.contrib.auth.admin import UserAdmin
    from django.contrib.auth.models import User
    
    # Get the current User admin
    current_admin = admin.site._registry.get(User)
    
    if current_admin:
        # Add the import action to existing actions
        if hasattr(current_admin, 'actions'):
            current_admin.actions = list(current_admin.actions or [])
        else:
            current_admin.actions = []
        
        current_admin.actions.append(add_import_users_action)
        
        # Add custom URLs to existing admin
        original_get_urls = current_admin.get_urls
        
        def get_urls(self):
            urls = original_get_urls()
            custom_urls = [
                path('import-users/', excel_user_import_admin.import_users_view, name='admin_import_users'),
                path('download-import-report/', excel_user_import_admin.download_report_view, name='download_import_report'),
            ]
            return custom_urls + urls
        
        # Monkey patch the get_urls method
        current_admin.get_urls = get_urls.__get__(current_admin, current_admin.__class__)


# Call the extension function
extend_user_admin()
