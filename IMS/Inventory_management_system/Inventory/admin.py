from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from .models import InventoryItem, Category, Unit, MaterialOrder, Profile, Warehouse, Supplier, BillOfQuantity, Notification, BoQOverissuanceJustification

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

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'contact_person', 'contact_phone', 'contact_email', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'code', 'contact_person', 'contact_email')
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'code', 'is_active')
        }),
        ('Contact Information', {
            'fields': ('contact_person', 'contact_phone', 'contact_email', 'address')
        }),
        ('Additional Information', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

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

