# appointments/admin.py
from django.contrib import admin
from .models import Schedule, Appointment, Payment, PaymentItem, DentistSchedule

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
    

@admin.register(DentistSchedule)
class DentistScheduleAdmin(admin.ModelAdmin):
    list_display = ('dentist', 'get_weekday_display', 'is_working', 'working_hours_summary', 'has_lunch_break')
    list_filter = ('is_working', 'weekday', 'has_lunch_break', 'dentist')
    search_fields = ('dentist__first_name', 'dentist__last_name', 'dentist__email')
    ordering = ('dentist', 'weekday')
    
    fieldsets = (
        (None, {
            'fields': ('dentist', 'weekday', 'is_working')
        }),
        ('Working Hours', {
            'fields': ('start_time', 'end_time'),
            'classes': ('collapse',),
        }),
        ('Lunch Break', {
            'fields': ('has_lunch_break', 'lunch_start', 'lunch_end'),
            'classes': ('collapse',),
        }),
    )
    
    def working_hours_summary(self, obj):
        """Display working hours in admin list"""
        if not obj.is_working:
            return "Not Working"
        return f"{obj.start_time.strftime('%I:%M %p')} - {obj.end_time.strftime('%I:%M %p')}"
    working_hours_summary.short_description = 'Working Hours'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('dentist')
    
    actions = ['create_default_schedules']
    
    def create_default_schedules(self, request, queryset):
        """Admin action to create default schedules for selected dentists"""
        from django.contrib import messages
        from users.models import User
        
        dentist_ids = list(queryset.values_list('dentist_id', flat=True).distinct())
        dentists = User.objects.filter(id__in=dentist_ids, is_active_dentist=True)
        
        created_count = 0
        for dentist in dentists:
            for weekday in range(7):
                _, created = DentistSchedule.objects.get_or_create(
                    dentist=dentist,
                    weekday=weekday,
                    defaults={
                        'is_working': weekday < 5,  # Monday to Friday only
                    }
                )
                if created:
                    created_count += 1
        
        messages.success(
            request, 
            f'Created {created_count} default schedule entries for {dentists.count()} dentists.'
        )
    create_default_schedules.short_description = "Create default schedules for selected dentists"