from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import HttpResponse
from django.utils.html import format_html
from .models import (
    InventoryItem, Category, Unit, MaterialOrder, Profile, Warehouse, Supplier, 
    BillOfQuantity, Notification, BoQOverissuanceJustification,
    SupplierPriceCatalog, SupplyContract, SupplyContractItem,
    SupplierInvoice, SupplierInvoiceItem, StoreOrderAssignment, ObsoleteMaterial
)
from .forms import ExcelUserImportForm
from .user_import import ExcelUserImporter
import tempfile
import os

# Import weekly report admin
from .admin_weekly_report import WeeklyReportAdmin

# Import weekly report admin
from .admin_weekly_report import WeeklyReportAdmin

# Import weekly report admin
from .admin_weekly_report import WeeklyReportAdmin

# Register your models here.

admin.site.register(InventoryItem)
admin.site.register(Category)
admin.site.register(Unit)

# Unregister default User and Group admins to customize them
admin.site.unregister(User)
admin.site.unregister(Group)

# Custom User Admin with Groups/Roles visible
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'get_groups', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('-date_joined',)
    
    def get_groups(self, obj):
        """Display user's groups/roles"""
        groups = obj.groups.all()
        if groups:
            return ', '.join([group.name for group in groups])
        return 'No Role'
    get_groups.short_description = 'Roles/Groups'
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Roles & Permissions', {
            'fields': ('groups', 'is_active', 'is_staff', 'is_superuser'),
            'description': 'Assign user to groups/roles. Groups define what the user can do in the system.'
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    filter_horizontal = ('groups', 'user_permissions')
    
    def get_urls(self):
        """Add custom URLs for user import functionality"""
        urls = super().get_urls()
        custom_urls = [
            path('import-users/', self.import_users_view, name='admin_import_users'),
            path('download-import-report/', self.download_report_view, name='download_import_report'),
        ]
        return custom_urls + urls
    
    def import_users_view(self, request):
        """Handle Excel user import through admin interface"""
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
        """Process the Excel file and import users"""
        excel_file = form.cleaned_data['excel_file']
        default_group = form.cleaned_data.get('default_group')
        
        # Save uploaded file temporarily
        temp_file_path = None
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
                    
                    detailed_msg = success_msg + "\\n\\nCreated users:\\n" + "\\n".join(user_details)
                    detailed_msg += "\\n\\nIMPORTANT: Save these passwords and share them securely with users."
                    
                    messages.success(request, detailed_msg)
                else:
                    messages.success(request, success_msg)
            
            if results['error_count'] > 0:
                error_msg = f"Encountered {results['error_count']} errors during import."
                if results['errors']:
                    error_details = "\\n".join([f"• {error}" for error in results['errors']])
                    error_msg += f"\\n\\nErrors:\\n{error_details}"
                messages.error(request, error_msg)
            
            # Generate and store report for download
            if results['success_count'] > 0 or results['error_count'] > 0:
                report_content = importer.generate_import_report()
                request.session['import_report'] = report_content
                request.session['import_report_filename'] = f"user_import_report.txt"
                
                # Add download link message
                messages.info(request, format_html(
                    'Import completed. <a href="{}" class="button">Download Detailed Report</a>',
                    '/admin/auth/user/download-import-report/'
                ))
            
            return redirect('admin:auth_user_changelist')
            
        except Exception as e:
            messages.error(request, f'Import failed: {str(e)}')
            return redirect('admin:admin_import_users')
            
        finally:
            # Clean up temporary file
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass
    
    def download_report_view(self, request):
        """Download the import report"""
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

# Custom Group Admin for managing roles
@admin.register(Group)
class CustomGroupAdmin(GroupAdmin):
    list_display = ('name', 'get_user_count', 'get_permissions_count')
    search_fields = ('name',)
    
    def get_user_count(self, obj):
        """Display number of users in this group"""
        return obj.user_set.count()
    get_user_count.short_description = 'Number of Users'
    
    def get_permissions_count(self, obj):
        """Display number of permissions"""
        return obj.permissions.count()
    get_permissions_count.short_description = 'Permissions'
    
    fieldsets = (
        (None, {
            'fields': ('name',),
            'description': 'Groups represent user roles (e.g., Schedule Officers, Store Officers, Transporters, Consultants)'
        }),
        ('Permissions', {
            'fields': ('permissions',),
            'classes': ('collapse',)
        }),
    )
    
    filter_horizontal = ('permissions',)

@admin.register(MaterialOrder)
class MaterialOrderAdmin(admin.ModelAdmin):
    list_display = ('request_code', 'name', 'quantity', 'status', 'request_type', 'user', 'assigned_to', 'processed_by', 'processed_at', 'date_requested')
    list_filter = ('status', 'request_type', 'priority', 'date_requested', 'processed_at', 'assigned_to')
    search_fields = ('request_code', 'name', 'user__username', 'processed_by__username', 'assigned_to__username')
    readonly_fields = ('processed_by', 'processed_at', 'assigned_to', 'assigned_at', 'assigned_by', 'last_updated_by', 'date_requested')
    date_hierarchy = 'date_requested'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'quantity', 'category', 'code', 'unit', 'request_type', 'priority')
        }),
        ('Location & Project', {
            'fields': ('region', 'district', 'community', 'consultant', 'contractor', 'package_number', 'warehouse', 'supplier')
        }),
        ('Request Details', {
            'fields': ('date_requested', 'date_required', 'status', 'request_code')
        }),
        ('Assignment Information', {
            'fields': ('assigned_to', 'assigned_by', 'assigned_at'),
            'classes': ('collapse',)
        }),
        ('Processing Information', {
            'fields': ('processed_quantity', 'remaining_quantity', 'processed_by', 'processed_at'),
            'classes': ('collapse',)
        }),
        ('User & Group', {
            'fields': ('user', 'group', 'last_updated_by'),
            'classes': ('collapse',)
        })
    )

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """
    Custom admin for Profile model with signature stamp management.
    """
    list_display = ('user', 'get_username', 'get_email', 'has_signature_stamp', 'profile_picture')
    list_filter = ('user__is_active', 'user__is_staff')
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'signature_stamp')
    readonly_fields = ('signature_stamp', 'get_stamp_details')
    
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Profile Picture', {
            'fields': ('profile_picture',)
        }),
        ('Digital Signature Stamp', {
            'fields': ('signature_stamp', 'get_stamp_details'),
            'description': 'Digital signature stamp is automatically generated. Use admin actions to regenerate if needed.'
        }),
    )
    
    def get_username(self, obj):
        """Display username"""
        return obj.user.username if obj.user else 'No User'
    get_username.short_description = 'Username'
    get_username.admin_order_field = 'user__username'
    
    def get_email(self, obj):
        """Display email"""
        return obj.user.email if obj.user else 'N/A'
    get_email.short_description = 'Email'
    get_email.admin_order_field = 'user__email'
    
    def has_signature_stamp(self, obj):
        """Display if profile has a signature stamp"""
        return bool(obj.signature_stamp)
    has_signature_stamp.boolean = True
    has_signature_stamp.short_description = 'Has Stamp'
    
    def get_stamp_details(self, obj):
        """Display parsed signature stamp details"""
        if not obj.signature_stamp:
            return 'No signature stamp'
        
        stamp_data = obj.display_signature_stamp()
        if stamp_data and isinstance(stamp_data, dict):
            details = []
            for key, value in stamp_data.items():
                details.append(f"<strong>{key}:</strong> {value}")
            return '<br>'.join(details)
        return obj.signature_stamp
    get_stamp_details.short_description = 'Stamp Details'
    get_stamp_details.allow_tags = True
    
    # Admin actions
    actions = ['regenerate_selected_stamps', 'regenerate_all_stamps', 'generate_missing_stamps']
    
    def regenerate_selected_stamps(self, request, queryset):
        """
        Regenerate signature stamps for selected profiles.
        This will overwrite existing stamps.
        """
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for profile in queryset:
            try:
                # Check if profile has a user
                if not profile.user:
                    skipped_count += 1
                    continue
                
                # Check if user has a username
                if not hasattr(profile.user, 'username') or not profile.user.username:
                    skipped_count += 1
                    continue
                
                # Regenerate the stamp
                profile.regenerate_signature_stamp(force=True)
                success_count += 1
                
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f'Error regenerating stamp for profile {profile.pk}: {str(e)}',
                    level='error'
                )
        
        # Success message
        if success_count > 0:
            self.message_user(
                request,
                f'Successfully regenerated {success_count} signature stamp(s).',
                level='success'
            )
        
        # Warning for skipped profiles
        if skipped_count > 0:
            self.message_user(
                request,
                f'Skipped {skipped_count} profile(s) without valid users.',
                level='warning'
            )
        
        # Error summary
        if error_count > 0:
            self.message_user(
                request,
                f'Failed to regenerate {error_count} stamp(s). Check error messages above.',
                level='error'
            )
    
    regenerate_selected_stamps.short_description = 'Regenerate signature stamps for selected profiles'
    
    def regenerate_all_stamps(self, request, queryset):
        """
        Regenerate signature stamps for ALL profiles in the database.
        This action ignores the selection and processes all profiles.
        """
        from django.contrib import messages
        
        # Get all profiles
        all_profiles = Profile.objects.all()
        total_count = all_profiles.count()
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for profile in all_profiles:
            try:
                # Check if profile has a user
                if not profile.user:
                    skipped_count += 1
                    continue
                
                # Check if user has a username
                if not hasattr(profile.user, 'username') or not profile.user.username:
                    skipped_count += 1
                    continue
                
                # Regenerate the stamp
                profile.regenerate_signature_stamp(force=True)
                success_count += 1
                
            except Exception as e:
                error_count += 1
        
        # Comprehensive message
        self.message_user(
            request,
            f'Processed {total_count} profile(s): '
            f'{success_count} regenerated, '
            f'{skipped_count} skipped (no user), '
            f'{error_count} errors.',
            level='success' if error_count == 0 else 'warning'
        )
    
    regenerate_all_stamps.short_description = '⚠️ Regenerate ALL signature stamps (ignores selection)'
    
    def generate_missing_stamps(self, request, queryset):
        """
        Generate signature stamps only for profiles that don't have one.
        This will not overwrite existing stamps.
        """
        success_count = 0
        error_count = 0
        skipped_no_user = 0
        skipped_has_stamp = 0
        
        for profile in queryset:
            try:
                # Skip if already has a stamp
                if profile.signature_stamp:
                    skipped_has_stamp += 1
                    continue
                
                # Check if profile has a user
                if not profile.user:
                    skipped_no_user += 1
                    continue
                
                # Check if user has a username
                if not hasattr(profile.user, 'username') or not profile.user.username:
                    skipped_no_user += 1
                    continue
                
                # Generate the stamp
                stamp = profile.get_or_create_signature_stamp()
                if stamp:
                    success_count += 1
                else:
                    error_count += 1
                
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f'Error generating stamp for profile {profile.pk}: {str(e)}',
                    level='error'
                )
        
        # Success message
        if success_count > 0:
            self.message_user(
                request,
                f'Successfully generated {success_count} signature stamp(s).',
                level='success'
            )
        
        # Info about skipped profiles
        if skipped_has_stamp > 0:
            self.message_user(
                request,
                f'{skipped_has_stamp} profile(s) already had stamps (not overwritten).',
                level='info'
            )
        
        if skipped_no_user > 0:
            self.message_user(
                request,
                f'Skipped {skipped_no_user} profile(s) without valid users.',
                level='warning'
            )
        
        # Error summary
        if error_count > 0:
            self.message_user(
                request,
                f'Failed to generate {error_count} stamp(s). Check error messages above.',
                level='error'
            )
    
    generate_missing_stamps.short_description = 'Generate stamps for profiles without one'

admin.site.register(Warehouse)

# Register LogEntry
@admin.register(BillOfQuantity)
class BillOfQuantityAdmin(admin.ModelAdmin):
    list_display = ('material_description', 'item_code', 'package_number', 'region', 'district', 'contract_quantity', 'quantity_received', 'get_balance', 'warehouse', 'date_created')
    list_filter = ('region', 'district', 'warehouse', 'date_created')
    search_fields = ('material_description', 'item_code', 'package_number', 'consultant', 'contractor', 'region', 'district')
    readonly_fields = ('date_created', 'get_balance')
    date_hierarchy = 'date_created'
    
    fieldsets = (
        ('Location Information', {
            'fields': ('region', 'district', 'community')
        }),
        ('Project Details', {
            'fields': ('consultant', 'contractor', 'package_number')
        }),
        ('Material Information', {
            'fields': ('material_description', 'item_code', 'contract_quantity', 'quantity_received', 'get_balance', 'warehouse')
        }),
        ('User & Group', {
            'fields': ('user', 'group'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('date_created',),
            'classes': ('collapse',)
        })
    )
    
    def get_balance(self, obj):
        """Display the balance (remaining quantity)"""
        return obj.balance
    get_balance.short_description = 'Balance'

@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'content_type', 'object_repr', 'action_flag', 'change_message', 'action_time')
    list_filter = ('action_flag', 'content_type')
    search_fields = ['user__username', 'object_repr', 'change_message']


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'notification_type', 'recipient_group', 'recipient_user', 'sender', 'is_read', 'created_at')
    list_filter = ('notification_type', 'recipient_group', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'recipient_user__username', 'sender__username')
    readonly_fields = ('created_at', 'read_at')
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Notification Details', {
            'fields': ('notification_type', 'title', 'message')
        }),
        ('Recipients', {
            'fields': ('recipient_group', 'recipient_user', 'sender')
        }),
        ('Related Objects', {
            'fields': ('related_order', 'related_transport', 'related_project'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_read', 'created_at', 'read_at'),
            'classes': ('collapse',)
        })
    )
    
    def has_add_permission(self, request):
        """Notifications should be created by the system, not manually"""
        return request.user.is_superuser
    
    actions = ['mark_as_read', 'mark_as_unread']
    
    def mark_as_read(self, request, queryset):
        from django.utils import timezone
        count = queryset.update(is_read=True, read_at=timezone.now())
        self.message_user(request, f'{count} notification(s) marked as read.')
    mark_as_read.short_description = 'Mark selected notifications as read'
    
    def mark_as_unread(self, request, queryset):
        count = queryset.update(is_read=False, read_at=None)
        self.message_user(request, f'{count} notification(s) marked as unread.')
    mark_as_unread.short_description = 'Mark selected notifications as unread'


@admin.register(BoQOverissuanceJustification)
class BoQOverissuanceJustificationAdmin(admin.ModelAdmin):
    list_display = ('package_number', 'boq_item', 'overissuance_quantity', 'justification_category', 'status', 'submitted_by', 'submitted_at', 'reviewed_by')
    list_filter = ('status', 'justification_category', 'submitted_at', 'reviewed_at')
    search_fields = ('package_number', 'project_name', 'boq_item__material_description', 'reason', 'submitted_by__username', 'reviewed_by__username')
    readonly_fields = ('submitted_at', 'reviewed_at', 'boq_item', 'package_number', 'project_name', 'overissuance_quantity')
    date_hierarchy = 'submitted_at'
    
    fieldsets = (
        ('Project Information', {
            'fields': ('boq_item', 'package_number', 'project_name', 'overissuance_quantity')
        }),
        ('Justification Details', {
            'fields': ('justification_category', 'reason', 'supporting_documents')
        }),
        ('Status & Review', {
            'fields': ('status', 'review_comments', 'reviewed_by', 'reviewed_at')
        }),
        ('Submission Info', {
            'fields': ('submitted_by', 'submitted_at'),
            'classes': ('collapse',)
        })
    )
    
    actions = ['approve_justifications', 'reject_justifications', 'mark_under_review']
    
    def approve_justifications(self, request, queryset):
        from django.utils import timezone
        count = queryset.update(
            status='Approved',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{count} justification(s) approved.')
    approve_justifications.short_description = 'Approve selected justifications'
    
    def reject_justifications(self, request, queryset):
        from django.utils import timezone
        count = queryset.update(
            status='Rejected',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{count} justification(s) rejected.')
    reject_justifications.short_description = 'Reject selected justifications'
    
    def mark_under_review(self, request, queryset):
        from django.utils import timezone
        count = queryset.update(
            status='Under Review',
            reviewed_by=request.user,
            reviewed_at=timezone.now()
        )
        self.message_user(request, f'{count} justification(s) marked as under review.')
    mark_under_review.short_description = 'Mark as under review'


# Supply Contract Management Admin

class SupplierPriceCatalogInline(admin.TabularInline):
    model = SupplierPriceCatalog
    extra = 0
    fields = ('material', 'unit_rate', 'currency', 'effective_date', 'expiry_date', 'is_active')
    readonly_fields = ('created_at',)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'contact_person', 'contact_phone', 'rating', 'is_active', 'created_at')
    list_filter = ('is_active', 'rating', 'created_at')
    search_fields = ('name', 'code', 'contact_person', 'contact_email', 'registration_number')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [SupplierPriceCatalogInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'registration_number', 'rating')
        }),
        ('Contact Details', {
            'fields': ('contact_person', 'contact_phone', 'contact_email', 'address')
        }),
        ('Status & Notes', {
            'fields': ('is_active', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SupplierPriceCatalog)
class SupplierPriceCatalogAdmin(admin.ModelAdmin):
    list_display = ('supplier', 'material', 'unit_rate', 'currency', 'effective_date', 'expiry_date', 'is_valid', 'is_active')
    list_filter = ('supplier', 'currency', 'is_active', 'effective_date')
    search_fields = ('supplier__name', 'material__name', 'material__code')
    readonly_fields = ('created_by', 'created_at', 'updated_at')
    date_hierarchy = 'effective_date'
    
    fieldsets = (
        ('Price Information', {
            'fields': ('supplier', 'material', 'unit_rate', 'currency')
        }),
        ('Validity', {
            'fields': ('effective_date', 'expiry_date', 'is_active')
        }),
        ('Delivery Details', {
            'fields': ('warehouse', 'minimum_order_quantity', 'lead_time_days')
        }),
        ('Additional Info', {
            'fields': ('notes', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


class SupplyContractItemInline(admin.TabularInline):
    model = SupplyContractItem
    extra = 1
    fields = ('material', 'quantity', 'unit_rate', 'total_amount', 'warehouse', 'notes')
    readonly_fields = ('total_amount',)
    
    def total_amount(self, obj):
        if obj.id:
            return f"{obj.total_amount:,.2f}"
        return "-"
    total_amount.short_description = 'Total Amount'


@admin.register(SupplyContract)
class SupplyContractAdmin(admin.ModelAdmin):
    list_display = ('contract_number', 'supplier', 'contract_type', 'status', 'start_date', 'end_date', 'total_estimated_value', 'actual_value', 'created_at')
    list_filter = ('status', 'contract_type', 'supplier', 'start_date')
    search_fields = ('contract_number', 'title', 'supplier__name')
    readonly_fields = ('created_by', 'approved_by', 'approval_date', 'created_at', 'updated_at', 'actual_value')
    date_hierarchy = 'start_date'
    inlines = [SupplyContractItemInline]
    
    fieldsets = (
        ('Contract Details', {
            'fields': ('contract_number', 'title', 'supplier', 'contract_type', 'status')
        }),
        ('Dates', {
            'fields': ('start_date', 'end_date')
        }),
        ('Financial', {
            'fields': ('total_estimated_value', 'actual_value', 'currency')
        }),
        ('Terms', {
            'fields': ('terms_and_conditions', 'notes'),
            'classes': ('collapse',)
        }),
        ('Workflow', {
            'fields': ('created_by', 'approved_by', 'approval_date', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['approve_contracts', 'mark_as_completed']
    
    def approve_contracts(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status='pending_approval').update(
            status='active',
            approved_by=request.user,
            approval_date=timezone.now()
        )
        self.message_user(request, f'{count} contract(s) approved and activated.')
    approve_contracts.short_description = 'Approve and activate selected contracts'
    
    def mark_as_completed(self, request, queryset):
        count = queryset.update(status='completed')
        self.message_user(request, f'{count} contract(s) marked as completed.')
    mark_as_completed.short_description = 'Mark selected contracts as completed'


class SupplierInvoiceItemInline(admin.TabularInline):
    model = SupplierInvoiceItem
    extra = 1
    fields = ('material', 'quantity_invoiced', 'unit_rate_invoiced', 'total_amount', 'quantity_received', 'has_discrepancy', 'warehouse')
    readonly_fields = ('total_amount', 'has_discrepancy')
    
    def total_amount(self, obj):
        if obj.id:
            return f"{obj.total_amount:,.2f}"
        return "-"
    total_amount.short_description = 'Total Amount'


@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'supplier', 'invoice_date', 'due_date', 'total_amount', 'calculated_total', 'status', 'is_overdue', 'submitted_by')
    list_filter = ('status', 'supplier', 'invoice_date', 'due_date')
    search_fields = ('invoice_number', 'supplier__name', 'payment_reference')
    readonly_fields = ('submitted_by', 'verified_by', 'approved_by', 'verified_date', 'approved_date', 'created_at', 'updated_at', 'calculated_total', 'is_overdue')
    date_hierarchy = 'invoice_date'
    inlines = [SupplierInvoiceItemInline]
    
    fieldsets = (
        ('Invoice Information', {
            'fields': ('invoice_number', 'supplier', 'contract', 'invoice_date', 'due_date')
        }),
        ('Financial', {
            'fields': ('total_amount', 'calculated_total', 'currency', 'status')
        }),
        ('Payment', {
            'fields': ('payment_reference', 'payment_date', 'is_overdue'),
            'classes': ('collapse',)
        }),
        ('Documents & Notes', {
            'fields': ('uploaded_document', 'discrepancy_notes', 'notes'),
            'classes': ('collapse',)
        }),
        ('Workflow', {
            'fields': ('submitted_by', 'verified_by', 'verified_date', 'approved_by', 'approved_date', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating new
            obj.submitted_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['verify_invoices', 'approve_invoices', 'mark_as_paid', 'mark_as_disputed']
    
    def verify_invoices(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status='pending').update(
            status='verified',
            verified_by=request.user,
            verified_date=timezone.now()
        )
        self.message_user(request, f'{count} invoice(s) verified.')
    verify_invoices.short_description = 'Verify selected invoices'
    
    def approve_invoices(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status='verified').update(
            status='approved',
            approved_by=request.user,
            approved_date=timezone.now()
        )
        self.message_user(request, f'{count} invoice(s) approved for payment.')
    approve_invoices.short_description = 'Approve selected invoices for payment'
    
    def mark_as_paid(self, request, queryset):
        from django.utils import timezone
        count = queryset.filter(status='approved').update(
            status='paid',
            payment_date=timezone.now().date()
        )
        self.message_user(request, f'{count} invoice(s) marked as paid.')
    mark_as_paid.short_description = 'Mark selected invoices as paid'
    
    def mark_as_disputed(self, request, queryset):
        count = queryset.update(status='disputed')
        self.message_user(request, f'{count} invoice(s) marked as disputed.')
    mark_as_disputed.short_description = 'Mark selected invoices as disputed'


@admin.register(StoreOrderAssignment)
class StoreOrderAssignmentAdmin(admin.ModelAdmin):
    """
    Admin interface for managing store order assignments.
    """
    list_display = ('material_order', 'get_request_code', 'assigned_to', 'assigned_by', 'status', 'assigned_at', 'completed_at')
    list_filter = ('status', 'assigned_at', 'completed_at', 'assigned_to', 'assigned_by')
    search_fields = ('material_order__request_code', 'material_order__name', 'assigned_to__username', 'assigned_by__username')
    readonly_fields = ('assigned_at', 'started_at', 'completed_at', 'updated_at')
    date_hierarchy = 'assigned_at'
    
    fieldsets = (
        ('Order Information', {
            'fields': ('material_order',)
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'assigned_by', 'assigned_at', 'status')
        }),
        ('Progress Tracking', {
            'fields': ('started_at', 'completed_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('assignment_notes', 'completion_notes'),
            'classes': ('collapse',)
        })
    )
    
    def get_request_code(self, obj):
        """Display the material order request code"""
        return obj.material_order.request_code if obj.material_order else 'N/A'
    get_request_code.short_description = 'Request Code'
    get_request_code.admin_order_field = 'material_order__request_code'
    
    actions = ['mark_in_progress', 'mark_completed']
    
    def mark_in_progress(self, request, queryset):
        """Mark selected assignments as in progress"""
        count = 0
        for assignment in queryset:
            if assignment.status in ['Pending', 'Assigned']:
                assignment.mark_in_progress(user=request.user)
                count += 1
        self.message_user(request, f'{count} assignment(s) marked as in progress.')
    mark_in_progress.short_description = 'Mark selected as in progress'
    
    def mark_completed(self, request, queryset):
        """Mark selected assignments as completed"""
        count = 0
        for assignment in queryset:
            if assignment.status in ['Assigned', 'In Progress']:
                assignment.mark_completed(user=request.user)
                count += 1
        self.message_user(request, f'{count} assignment(s) marked as completed.')
    mark_completed.short_description = 'Mark selected as completed'


@admin.register(ObsoleteMaterial)
class ObsoleteMaterialAdmin(admin.ModelAdmin):
    """
    Admin interface for managing obsolete materials register.
    """
    list_display = ('material_name', 'material_code', 'category', 'quantity', 'unit', 'warehouse', 'status', 'date_marked_obsolete', 'registered_by', 'estimated_value')
    list_filter = ('status', 'warehouse', 'category', 'date_marked_obsolete', 'registered_by')
    search_fields = ('material_name', 'material_code', 'category', 'reason_for_obsolescence', 'serial_numbers')
    readonly_fields = ('registered_by', 'reviewed_by', 'review_date', 'created_at', 'updated_at')
    date_hierarchy = 'date_marked_obsolete'
    
    fieldsets = (
        ('Material Information', {
            'fields': ('material', 'material_name', 'material_code', 'category', 'unit', 'quantity', 'warehouse')
        }),
        ('Serial Numbers (if applicable)', {
            'fields': ('serial_numbers',),
            'classes': ('collapse',)
        }),
        ('Obsolescence Details', {
            'fields': ('reason_for_obsolescence', 'date_marked_obsolete', 'status', 'estimated_value')
        }),
        ('Disposal Information', {
            'fields': ('disposal_method', 'disposal_date'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Audit Trail', {
            'fields': ('registered_by', 'reviewed_by', 'review_date', 'review_notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        """Automatically set registered_by when creating"""
        if not change:  # If creating new
            obj.registered_by = request.user
        super().save_model(request, obj, form, change)
    
    actions = ['approve_for_disposal', 'mark_as_disposed', 'mark_as_repurposed']
    
    def approve_for_disposal(self, request, queryset):
        """Approve selected materials for disposal"""
        from django.utils import timezone
        count = 0
        for material in queryset:
            if material.status in ['Registered', 'Pending Review']:
                material.status = 'Approved for Disposal'
                material.reviewed_by = request.user
                material.review_date = timezone.now()
                material.save()
                count += 1
        self.message_user(request, f'{count} material(s) approved for disposal.')
    approve_for_disposal.short_description = 'Approve selected for disposal'
    
    def mark_as_disposed(self, request, queryset):
        """Mark selected materials as disposed"""
        count = queryset.filter(status='Approved for Disposal').update(status='Disposed')
        self.message_user(request, f'{count} material(s) marked as disposed.')
    mark_as_disposed.short_description = 'Mark selected as disposed'
    
    def mark_as_repurposed(self, request, queryset):
        """Mark selected materials as repurposed"""
        count = queryset.update(status='Repurposed')
        self.message_user(request, f'{count} material(s) marked as repurposed.')
    mark_as_repurposed.short_description = 'Mark selected as repurposed'

