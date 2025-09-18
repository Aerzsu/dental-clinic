# core/admin.py
from django.contrib import admin
from .models import AuditLog, SystemSetting, Holiday

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'model_name', 'object_repr', 'timestamp']
    list_filter = ['action', 'model_name', 'timestamp']
    search_fields = ['user__username', 'object_repr']
    readonly_fields = ['user', 'action', 'model_name', 'object_id', 'object_repr', 'changes', 'ip_address', 'timestamp']
    date_hierarchy = 'timestamp'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ['key', 'value_preview', 'is_active', 'updated_at']
    list_filter = ['is_active', 'created_at', 'updated_at']
    search_fields = ['key', 'description']
    readonly_fields = ['created_at', 'updated_at']
    CLINIC_OPEN_TIME = "10:00"
    CLINIC_CLOSE_TIME = "18:00"
    LUNCH_START_TIME = "12:00"
    LUNCH_END_TIME = "13:00"
    DEFAULT_APPOINTMENT_DURATION = "30"  # minutes
    ADVANCE_BOOKING_DAYS = "60"  # how far in advance patients can book
    CANCELLATION_HOURS = "24"  # hours before appointment
    
    def value_preview(self, obj):
        return obj.value[:50] + ('...' if len(obj.value) > 50 else '')
    value_preview.short_description = 'Value'

@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'is_recurring', 'is_active']
    list_filter = ['is_recurring', 'is_active', 'date']
    search_fields = ['name']
    date_hierarchy = 'date'