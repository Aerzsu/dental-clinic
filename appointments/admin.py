# appointments/admin.py
from django.contrib import admin
from .models import Schedule, Appointment, Payment, PaymentItem

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ['dentist', 'date', 'start_time', 'end_time', 'is_available']
    list_filter = ['is_available', 'date', 'dentist']
    search_fields = ['dentist__first_name', 'dentist__last_name']
    date_hierarchy = 'date'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('dentist')

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'dentist', 'service', 'schedule_date', 'schedule_time', 'status', 'patient_type']
    list_filter = ['status', 'patient_type', 'dentist', 'service', 'requested_at']
    search_fields = ['patient__first_name', 'patient__last_name', 'reason']
    readonly_fields = ['requested_at', 'approved_at']
    date_hierarchy = 'requested_at'
    
    fieldsets = (
        ('Appointment Details', {
            'fields': ('patient', 'dentist', 'service', 'schedule')
        }),
        ('Status & Type', {
            'fields': ('status', 'patient_type', 'approved_by')
        }),
        ('Notes', {
            'fields': ('reason', 'staff_notes')
        }),
        ('Timestamps', {
            'fields': ('requested_at', 'approved_at'),
            'classes': ['collapse']
        }),
    )
    
    def schedule_date(self, obj):
        return obj.schedule.date if obj.schedule else None
    schedule_date.short_description = 'Date'
    
    def schedule_time(self, obj):
        return obj.schedule.start_time if obj.schedule else None
    schedule_time.short_description = 'Time'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'patient', 'dentist', 'service', 'schedule', 'approved_by'
        )

class PaymentItemInline(admin.TabularInline):
    model = PaymentItem
    extra = 1

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'appointment', 'amount_paid', 'status', 'payment_datetime']
    list_filter = ['status', 'payment_datetime']
    search_fields = ['patient__first_name', 'patient__last_name']
    readonly_fields = ['payment_datetime']
    inlines = [PaymentItemInline]
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('patient', 'appointment')