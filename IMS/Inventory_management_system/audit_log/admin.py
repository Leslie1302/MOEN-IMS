from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'model_name', 'object_id', 'action', 'timestamp')
    search_fields = ('user__username', 'model_name', 'action')
    list_filter = ('model_name', 'action', 'timestamp')