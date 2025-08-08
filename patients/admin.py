# patients/admin.py
from django.contrib import admin
from .models import Patient, TreatmentNote

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ['last_name', 'first_name', 'email', 'contact_number', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at', 'date_of_birth']
    search_fields = ['first_name', 'last_name', 'email', 'contact_number']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'date_of_birth', 'email', 'contact_number', 'address')
        }),
        ('Emergency Contact', {
            'fields': ('emergency_contact_name', 'emergency_contact_phone')
        }),
        ('Medical Information', {
            'fields': ('medical_notes',)
        }),
        ('System Information', {
            'fields': ('is_active', 'created_at', 'updated_at'),
            'classes': ['collapse']
        }),
    )

@admin.register(TreatmentNote)
class TreatmentNoteAdmin(admin.ModelAdmin):
    list_display = ['patient', 'tooth_number', 'date_recorded', 'recorded_by']
    list_filter = ['date_recorded', 'recorded_by']
    search_fields = ['patient__first_name', 'patient__last_name', 'notes']
    readonly_fields = ['date_recorded']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('patient', 'recorded_by')