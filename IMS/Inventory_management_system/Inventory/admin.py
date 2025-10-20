from django.contrib import admin
from django.contrib.admin.models import LogEntry
from .models import InventoryItem, Category, Unit, MaterialOrder, Profile, Warehouse, Supplier

# Register your models here.

admin.site.register(InventoryItem)
admin.site.register(Category)
admin.site.register(Unit)

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
        }),
        ('Documents', {
            'fields': ('release_letter_pdf', 'release_letter_title'),
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
@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'content_type', 'object_repr', 'action_flag', 'change_message', 'action_time')
    list_filter = ('action_flag', 'content_type')
    search_fields = ['user__username', 'object_repr', 'change_message']