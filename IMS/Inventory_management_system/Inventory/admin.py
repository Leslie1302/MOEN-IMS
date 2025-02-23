from django.contrib import admin
from django.contrib.admin.models import LogEntry
from .models import InventoryItem, Category, Unit, MaterialOrder, Profile

# Register your models here.

admin.site.register(InventoryItem)
admin.site.register(Category)
admin.site.register(Unit)
admin.site.register(MaterialOrder)
admin.site.register(Profile)

# Register LogEntry
@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'content_type', 'object_repr', 'action_flag', 'change_message', 'action_time')
    list_filter = ('action_flag', 'content_type')
    search_fields = ['user__username', 'object_repr', 'change_message']