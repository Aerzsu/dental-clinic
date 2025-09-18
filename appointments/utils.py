# appointments/utils.py - Fixed version with proper timezone handling
from datetime import time, timedelta, datetime
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from core.models import SystemSetting

class AppointmentConfig:
    """Helper class for appointment-related configuration - SIMPLIFIED"""
   
    @classmethod
    def get_buffer_minutes(cls):
        """Get appointment buffer time in minutes"""
        try:
            return SystemSetting.get_int_setting('appointment_buffer_minutes', 15)
        except:
            return 15  # Default fallback
   
    @classmethod
    def get_clinic_hours(cls):
        """Get clinic operating hours - HARDCODED for simplicity"""
        return time(10, 0), time(18, 0)  # 10 AM to 6 PM
   
    @classmethod
    def get_lunch_break(cls):
        """Get lunch break hours - HARDCODED for simplicity"""
        return time(12, 0), time(13, 0)  # 12 PM to 1 PM
   
    @classmethod
    def get_time_slot_duration(cls):
        """Get time slot duration in minutes"""
        try:
            return SystemSetting.get_int_setting('appointment_time_slot_minutes', 30)
        except:
            return 30  # Default fallback
   
    @classmethod
    def get_minimum_booking_notice(cls):
        """Get minimum booking notice in hours"""
        try:
            return SystemSetting.get_int_setting('minimum_booking_notice_hours', 24)
        except:
            return 24  # Default fallback
   
    @classmethod
    def is_same_day_booking_enabled(cls):
        """Check if same-day booking is allowed"""
        try:
            return SystemSetting.get_bool_setting('enable_same_day_booking', False)
        except:
            return False  # Default fallback


@transaction.atomic
def create_appointment_atomic(patient, dentist, service, appointment_date, appointment_time, 
                            patient_type, reason='', buffer_minutes=15):
    """
    Atomically create appointment and schedule with proper conflict checking.
    FIXED VERSION with proper timezone handling.
    
    Args:
        patient: Patient instance
        dentist: User instance (dentist)
        service: Service instance
        appointment_date: date object
        appointment_time: time object
        patient_type: str ('new' or 'returning')
        reason: str (optional)
        buffer_minutes: int (buffer time after appointment)
    
    Returns:
        tuple: (appointment, created) where created is boolean
    
    Raises:
        ValidationError: If there are conflicts or validation errors
    """
    # Import here to avoid circular imports
    from .models import Appointment, AppointmentSlot
    from users.models import User
    
    # Create timezone-aware datetimes for consistency
    naive_start = datetime.combine(appointment_date, appointment_time)
    naive_end = naive_start + timedelta(minutes=service.duration_minutes)
    naive_end_with_buffer = naive_start + timedelta(minutes=service.duration_minutes + buffer_minutes)
    
    # Make timezone-aware if needed
    if timezone.is_naive(naive_start):
        start_datetime = timezone.make_aware(naive_start)
        end_datetime = timezone.make_aware(naive_end)
        end_with_buffer = timezone.make_aware(naive_end_with_buffer)
    else:
        start_datetime = naive_start
        end_datetime = naive_end
        end_with_buffer = naive_end_with_buffer
    
    end_time = end_datetime.time()
    
    # Use select_for_update to prevent race conditions
    dentist = User.objects.select_for_update().get(id=dentist.id, is_active_dentist=True)
    
    # SIMPLIFIED conflict checking approach
    # Instead of using the complex model method, do direct database query
    conflicting_appointments = Appointment.objects.filter(
        dentist=dentist,
        appointment_slot__date=appointment_date,
        status__in=Appointment.BLOCKING_STATUSES
    ).select_related('appointment_slot', 'service')
    
    for existing in conflicting_appointments:
        # Create timezone-aware datetimes for existing appointment
        existing_naive_start = datetime.combine(appointment_date, existing.appointment_slot.start_time)
        existing_naive_end = existing_naive_start + timedelta(minutes=existing.service.duration_minutes)
        existing_naive_end_with_buffer = existing_naive_end + timedelta(minutes=existing.appointment_slot.buffer_minutes)
        
        # Make timezone-aware
        if timezone.is_naive(existing_naive_start):
            existing_start = timezone.make_aware(existing_naive_start)
            existing_end_with_buffer = timezone.make_aware(existing_naive_end_with_buffer)
        else:
            existing_start = existing_naive_start
            existing_end_with_buffer = existing_naive_end_with_buffer
        
        # Check for overlap - now both datetimes are timezone-aware
        if start_datetime < existing_end_with_buffer and end_with_buffer > existing_start:
            raise ValidationError(
                f"Time slot conflicts with existing appointment: "
                f"{existing.appointment_slot.start_time.strftime('%I:%M %p')}-"
                f"{existing_end_with_buffer.time().strftime('%I:%M %p')}"
            )
    
    # Create appointment slot first
    try:
        appointment_slot = AppointmentSlot.objects.create(
            dentist=dentist,
            date=appointment_date,
            start_time=appointment_time,
            end_time=end_time,
            buffer_minutes=buffer_minutes,
            is_available=True,
            notes='Created for appointment booking'
        )
    except IntegrityError:
        # Handle case where slot already exists with exact same times
        try:
            appointment_slot = AppointmentSlot.objects.get(
                dentist=dentist,
                date=appointment_date,
                start_time=appointment_time,
                end_time=end_time
            )
            
            # Check if this slot already has an appointment
            existing_appointment = Appointment.objects.filter(
                appointment_slot=appointment_slot,
                status__in=Appointment.BLOCKING_STATUSES
            ).first()
            
            if existing_appointment:
                raise ValidationError("This time slot is already booked.")
        except AppointmentSlot.DoesNotExist:
            # If we can't get the slot, there's a conflict
            raise ValidationError("Unable to create appointment slot. Time may be unavailable.")
    
    # Create appointment
    appointment = Appointment.objects.create(
        patient=patient,
        dentist=dentist,
        service=service,
        appointment_slot=appointment_slot,
        patient_type=patient_type,
        reason=reason,
        status='pending'
    )
    
    return appointment, True