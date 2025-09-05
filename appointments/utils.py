# appointments/utils.py
from datetime import time, timedelta, datetime
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from core.models import SystemSetting

class AppointmentConfig:
    """Helper class for appointment-related configuration"""
   
    @classmethod
    def get_buffer_minutes(cls):
        """Get appointment buffer time in minutes"""
        return SystemSetting.get_int_setting('appointment_buffer_minutes', 15)
   
    @classmethod
    def get_clinic_hours(cls):
        """Get clinic operating hours"""
        start_time = SystemSetting.get_time_setting('clinic_start_time', time(10, 0))
        end_time = SystemSetting.get_time_setting('clinic_end_time', time(18, 0))
        return start_time, end_time
   
    @classmethod
    def get_lunch_break(cls):
        """Get lunch break hours"""
        start_time = SystemSetting.get_time_setting('lunch_start_time', time(12, 0))
        end_time = SystemSetting.get_time_setting('lunch_end_time', time(13, 0))
        return start_time, end_time
   
    @classmethod
    def get_time_slot_duration(cls):
        """Get time slot duration in minutes"""
        return SystemSetting.get_int_setting('appointment_time_slot_minutes', 30)
   
    @classmethod
    def get_minimum_booking_notice(cls):
        """Get minimum booking notice in hours"""
        return SystemSetting.get_int_setting('minimum_booking_notice_hours', 24)
   
    @classmethod
    def is_same_day_booking_enabled(cls):
        """Check if same-day booking is allowed"""
        return SystemSetting.get_bool_setting('enable_same_day_booking', False)
   
    @classmethod
    def get_max_concurrent_attempts(cls):
        """Get maximum concurrent booking attempts"""
        return SystemSetting.get_int_setting('max_concurrent_booking_attempts', 3)


@transaction.atomic
def create_appointment_atomic(patient, dentist, service, appointment_date, appointment_time, 
                            patient_type, reason='', buffer_minutes=15):
    """
    Atomically create appointment and schedule with proper conflict checking.
    
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
    from .models import Appointment, Schedule
    from users.models import User
    
    # Calculate end time based on service duration
    start_datetime = datetime.combine(appointment_date, appointment_time)
    end_datetime = start_datetime + timedelta(minutes=service.duration_minutes)
    end_time = end_datetime.time()
    
    # Calculate end time including buffer
    end_with_buffer = end_datetime + timedelta(minutes=buffer_minutes)
    
    # Use select_for_update to prevent race conditions
    dentist = User.objects.select_for_update().get(id=dentist.id, is_active_dentist=True)
    
    # Check for conflicts using the new method
    conflicts = Appointment.get_conflicting_appointments(
        dentist=dentist,
        start_datetime=start_datetime,
        end_datetime=end_with_buffer
    )
    
    if conflicts:
        conflict_times = [
            f"{c.schedule.start_time.strftime('%I:%M %p')}-{c.schedule.effective_end_time.strftime('%I:%M %p')}"
            for c in conflicts
        ]
        raise ValidationError(
            f"Time slot conflicts with existing appointments: {', '.join(conflict_times)}"
        )
    
    # Create schedule first
    try:
        schedule = Schedule.objects.create(
            dentist=dentist,
            date=appointment_date,
            start_time=appointment_time,
            end_time=end_time,
            buffer_minutes=buffer_minutes,
            is_available=True,
            notes='Created for appointment booking'
        )
    except IntegrityError:
        # Handle case where schedule already exists
        schedule = Schedule.objects.get(
            dentist=dentist,
            date=appointment_date,
            start_time=appointment_time,
            end_time=end_time
        )
        
        # Check if this schedule already has an appointment
        existing_appointment = Appointment.objects.filter(
            schedule=schedule,
            status__in=['pending', 'approved', 'completed']
        ).first()
        
        if existing_appointment:
            raise ValidationError("This time slot is already booked.")
    
    # Create appointment
    appointment = Appointment.objects.create(
        patient=patient,
        dentist=dentist,
        service=service,
        schedule=schedule,
        patient_type=patient_type,
        reason=reason,
        status='pending'
    )
    
    return appointment, True