# services/admin.py
from django.contrib import admin
from .models import Service, Discount

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'min_price', 'max_price', 'duration_minutes', 'is_archived', 'created_at']
    list_filter = ['is_archived', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description')
        }),
        ('Pricing & Duration', {
            'fields': ('min_price', 'max_price', 'duration_minutes')
        }),
        ('Status', {
            'fields': ('is_archived',)
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )

@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_value', 'is_percentage', 'is_active', 'created_at']
    list_filter = ['is_percentage', 'is_active', 'created_at']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at']