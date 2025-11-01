from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from .models import (
    InventoryItem, Category, Unit, MaterialOrder, Profile, Warehouse, Supplier, 
    BillOfQuantity, Notification, BoQOverissuanceJustification,
    SupplierPriceCatalog, SupplyContract, SupplyContractItem,
    SupplierInvoice, SupplierInvoiceItem
)

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
            'description': 'Groups represent user roles (e.g., Schedule Officers, Storekeepers, Transporters, Consultants)'
        }),
        ('Permissions', {
            'fields': ('permissions',),
            'classes': ('collapse',)
        }),
    )
    
    filter_horizontal = ('permissions',)

@admin.register(MaterialOrder)
class MaterialOrderAdmin(admin.ModelAdmin):
    list_display = ('request_code', 'name', 'quantity', 'status', 'request_type', 'user', 'processed_by', 'processed_at', 'date_requested')
    list_filter = ('status', 'request_type', 'priority', 'date_requested', 'processed_at')
    search_fields = ('request_code', 'name', 'user__username', 'processed_by__username')
    readonly_fields = ('processed_by', 'processed_at', 'last_updated_by', 'date_requested')
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
        ('Processing Information', {
            'fields': ('processed_quantity', 'remaining_quantity', 'processed_by', 'processed_at'),
            'classes': ('collapse',)
        }),
        ('User & Group', {
            'fields': ('user', 'group', 'last_updated_by'),
            'classes': ('collapse',)
        })
    )

admin.site.register(Profile)
admin.site.register(Warehouse)

# Supplier admin is registered below with enhanced features for supply contract management

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

