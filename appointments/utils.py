# appointments/utils.py - Simplified for AM/PM slot system
from datetime import time, timedelta, datetime
from django.db import transaction
from django.core.exceptions import ValidationError
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
        """Get clinic operating hours"""
        return time(8, 0), time(18, 0)  # 8 AM to 6 PM
   
    @classmethod
    def get_lunch_break(cls):
        """Get lunch break hours"""
        return time(12, 0), time(13, 0)  # 12 PM to 1 PM
   
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
def create_appointment_simple(patient, service, appointment_date, period, patient_type, reason=''):
    """
    Simple appointment creation for AM/PM slot system
    
    Args:
        patient: Patient instance
        service: Service instance
        appointment_date: date object
        period: str ('AM' or 'PM')
        patient_type: str ('new' or 'returning')
        reason: str (optional)
    
    Returns:
        tuple: (appointment, created) where created is boolean
    
    Raises:
        ValidationError: If there are conflicts or validation errors
    """
    from .models import Appointment
    
    # Check slot availability
    can_book, message = Appointment.can_book_appointment(appointment_date, period)
    
    if not can_book:
        raise ValidationError(message)
    
    # Create appointment
    appointment = Appointment.objects.create(
        patient=patient,
        service=service,
        appointment_date=appointment_date,
        period=period,
        patient_type=patient_type,
        reason=reason,
        status='pending'
    )
    
    return appointment, True


def get_available_slots_for_date(date_obj):
    """
    Get available AM/PM slots for a specific date
    
    Args:
        date_obj: date object
    
    Returns:
        dict: {
            'am_available': int,
            'pm_available': int,
            'am_total': int,
            'pm_total': int
        }
    """
    from .models import DailySlots
    
    # Don't allow Sundays or past dates
    if date_obj.weekday() == 6 or date_obj < timezone.now().date():
        return {
            'am_available': 0,
            'pm_available': 0,
            'am_total': 0,
            'pm_total': 0
        }
    
    daily_slots, _ = DailySlots.get_or_create_for_date(date_obj)
    
    if daily_slots:
        return {
            'am_available': daily_slots.get_available_am_slots(),
            'pm_available': daily_slots.get_available_pm_slots(),
            'am_total': daily_slots.am_slots,
            'pm_total': daily_slots.pm_slots
        }
    else:
        return {
            'am_available': 0,
            'pm_available': 0,
            'am_total': 0,
            'pm_total': 0
        }


def get_next_available_dates(days_ahead=30):
    """
    Get list of dates with available slots in the next N days
    
    Args:
        days_ahead: int (default 30)
    
    Returns:
        list: List of date objects with available slots
    """
    available_dates = []
    start_date = timezone.now().date() + timedelta(days=1)  # Start from tomorrow
    
    for i in range(days_ahead):
        check_date = start_date + timedelta(days=i)
        
        # Skip Sundays
        if check_date.weekday() == 6:
            continue
        
        slots = get_available_slots_for_date(check_date)
        if slots['am_available'] > 0 or slots['pm_available'] > 0:
            available_dates.append(check_date)
    
    return available_dates


def validate_appointment_date(appointment_date):
    """
    Validate if an appointment date is acceptable
    
    Args:
        appointment_date: date object
    
    Returns:
        tuple: (is_valid, error_message)
    """
    if not appointment_date:
        return False, "Appointment date is required"
    
    # Check if date is in the past
    if appointment_date <= timezone.now().date():
        return False, "Appointment date cannot be today or in the past"
    
    # Check if it's Sunday
    if appointment_date.weekday() == 6:
        return False, "No appointments available on Sundays"
    
    return True, "Date is valid"


def get_period_display_time(period):
    """
    Get display time range for AM/PM period
    
    Args:
        period: str ('AM' or 'PM')
    
    Returns:
        str: Time range display
    """
    if period == 'AM':
        return "8:00 AM - 12:00 PM"
    elif period == 'PM':
        return "1:00 PM - 6:00 PM"
    else:
        return "Invalid period"