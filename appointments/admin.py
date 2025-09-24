# appointments/admin.py - Fixed for AM/PM slot system
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import DailySlots, Appointment, Payment, PaymentItem


@admin.register(DailySlots)
class DailySlotsAdmin(admin.ModelAdmin):
    list_display = ['date', 'am_slots', 'pm_slots', 'total_slots', 'availability_status', 'created_by']
    list_filter = ['created_by', 'am_slots', 'pm_slots']
    search_fields = ['date', 'notes']
    date_hierarchy = 'date'
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Date & Slots', {
            'fields': ('date', 'am_slots', 'pm_slots')
        }),
        ('Details', {
            'fields': ('notes', 'created_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )
    
    def total_slots(self, obj):
        return obj.total_slots
    total_slots.short_description = 'Total Slots'
    
    def availability_status(self, obj):
        am_available = obj.get_available_am_slots()
        pm_available = obj.get_available_pm_slots()
        
        if am_available == 0 and pm_available == 0:
            return format_html('<span style="color: red;">Fully Booked</span>')
        elif am_available == 0:
            return format_html('<span style="color: orange;">AM Full, PM: {}</span>', pm_available)
        elif pm_available == 0:
            return format_html('<span style="color: orange;">AM: {}, PM Full</span>', am_available)
        else:
            return format_html('<span style="color: green;">AM: {}, PM: {}</span>', am_available, pm_available)
    
    availability_status.short_description = 'Availability'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by')


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient', 'appointment_date', 'period', 'service', 'status', 'assigned_dentist', 'patient_type']
    list_filter = ['status', 'period', 'patient_type', 'assigned_dentist', 'service', 'requested_at']
    search_fields = ['patient__first_name', 'patient__last_name', 'reason']
    readonly_fields = ['requested_at', 'confirmed_at']  # Changed from 'approved_at' to 'confirmed_at'
    date_hierarchy = 'appointment_date'
    
    fieldsets = (
        ('Appointment Details', {
            'fields': ('patient', 'service', 'appointment_date', 'period')
        }),
        ('Assignment & Status', {
            'fields': ('status', 'assigned_dentist', 'patient_type', 'confirmed_by')  # Changed from 'approved_by' to 'confirmed_by'
        }),
        ('Notes', {
            'fields': ('reason', 'staff_notes')
        }),
        ('Timestamps', {
            'fields': ('requested_at', 'confirmed_at'),  # Changed from 'approved_at' to 'confirmed_at'
            'classes': ['collapse']
        }),
    )
    
    actions = ['approve_selected_appointments', 'cancel_selected_appointments']
    
    def approve_selected_appointments(self, request, queryset):
        """Bulk approve selected pending appointments"""
        pending_appointments = queryset.filter(status='pending')
        
        if not pending_appointments.exists():
            self.message_user(request, "No pending appointments selected.")
            return
        
        approved_count = 0
        errors = []
        
        for appointment in pending_appointments:
            try:
                # Check slot availability
                can_book, message = Appointment.can_book_appointment(
                    appointment.appointment_date, 
                    appointment.period,
                    exclude_appointment_id=appointment.id
                )
                
                if can_book:
                    # Auto-assign first available dentist
                    from users.models import User
                    dentist = User.objects.filter(is_active_dentist=True).first()
                    appointment.approve(request.user, dentist)
                    approved_count += 1
                else:
                    errors.append(f"{appointment.patient.full_name}: {message}")
                    
            except Exception as e:
                errors.append(f"{appointment.patient.full_name}: {str(e)}")
        
        if approved_count:
            self.message_user(request, f"Successfully approved {approved_count} appointment(s).")
        
        if errors:
            self.message_user(request, f"Errors: {'; '.join(errors)}", level='ERROR')
    
    approve_selected_appointments.short_description = "Approve selected appointments"
    
    def cancel_selected_appointments(self, request, queryset):
        """Bulk cancel selected appointments"""
        cancellable_appointments = queryset.filter(
            status__in=['pending', 'confirmed']  # Changed from 'approved' to 'confirmed'
        )
        
        cancelled_count = 0
        for appointment in cancellable_appointments:
            if appointment.can_be_cancelled:
                appointment.cancel()
                cancelled_count += 1
        
        self.message_user(request, f"Successfully cancelled {cancelled_count} appointment(s).")
    
    cancel_selected_appointments.short_description = "Cancel selected appointments"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'patient', 'assigned_dentist', 'service', 'confirmed_by'  # Changed from 'approved_by' to 'confirmed_by'
        )


class PaymentItemInline(admin.TabularInline):
    model = PaymentItem
    extra = 1
    readonly_fields = ['subtotal', 'discount_amount', 'total']
    
    def subtotal(self, obj):
        if obj.pk:
            return f"₱{obj.subtotal:,.2f}"
        return "-"
    subtotal.short_description = 'Subtotal'
    
    def discount_amount(self, obj):
        if obj.pk:
            return f"₱{obj.discount_amount:,.2f}"
        return "-"
    discount_amount.short_description = 'Discount'
    
    def total(self, obj):
        if obj.pk:
            return f"₱{obj.total:,.2f}"
        return "-"
    total.short_description = 'Total'


# Custom admin site configuration
admin.site.site_header = "Dental Clinic Administration"
admin.site.site_title = "Dental Clinic Admin"
admin.site.index_title = "Welcome to Dental Clinic Administration"