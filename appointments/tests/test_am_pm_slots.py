# appointments/tests/test_am_pm_slots.py
"""
Tests for the AM/PM slot appointment system
"""
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta
from appointments.models import DailySlots, Appointment
from patients.models import Patient
from services.models import Service
from users.models import User, Role


class DailySlotsModelTest(TestCase):
    """Test DailySlots model functionality"""
    
    def setUp(self):
        # Create test user
        self.admin_role = Role.objects.create(name='Admin', can_manage_appointments=True)
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            role=self.admin_role
        )
    
    def test_create_daily_slots(self):
        """Test creating daily slots"""
        tomorrow = timezone.now().date() + timedelta(days=1)
        slots = DailySlots.objects.create(
            date=tomorrow,
            am_slots=6,
            pm_slots=8,
            created_by=self.admin_user
        )
        
        self.assertEqual(slots.am_slots, 6)
        self.assertEqual(slots.pm_slots, 8)
        self.assertEqual(slots.total_slots, 14)
    
    def test_available_slots_calculation(self):
        """Test available slots calculation with bookings"""
        tomorrow = timezone.now().date() + timedelta(days=1)
        slots = DailySlots.objects.create(
            date=tomorrow,
            am_slots=6,
            pm_slots=8,
            created_by=self.admin_user
        )
        
        # Create test patient and service
        patient = Patient.objects.create(
            first_name='John',
            last_name='Doe',
            email='john@test.com'
        )
        service = Service.objects.create(
            name='Cleaning',
            price=100.00,
            duration_minutes=30
        )
        
        # Create 2 AM appointments
        Appointment.objects.create(
            patient=patient,
            service=service,
            appointment_date=tomorrow,
            period='AM',
            status='approved'
        )
        Appointment.objects.create(
            patient=patient,
            service=service,
            appointment_date=tomorrow,
            period='AM',
            status='pending'
        )
        
        # Create 1 PM appointment
        Appointment.objects.create(
            patient=patient,
            service=service,
            appointment_date=tomorrow,
            period='PM',
            status='approved'
        )
        
        self.assertEqual(slots.get_available_am_slots(), 4)  # 6 - 2
        self.assertEqual(slots.get_available_pm_slots(), 7)  # 8 - 1
    
    def test_sunday_slots_validation(self):
        """Test that Sunday slots cannot be created with positive values"""
        # Find next Sunday
        today = timezone.now().date()
        days_ahead = 6 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        sunday = today + timedelta(days_ahead)
        
        with self.assertRaises(ValidationError):
            slots = DailySlots(
                date=sunday,
                am_slots=6,
                pm_slots=8,
                created_by=self.admin_user
            )
            slots.full_clean()
    
    def test_past_date_validation(self):
        """Test that past dates cannot be used"""
        yesterday = timezone.now().date() - timedelta(days=1)
        
        with self.assertRaises(ValidationError):
            slots = DailySlots(
                date=yesterday,
                am_slots=6,
                pm_slots=8,
                created_by=self.admin_user
            )
            slots.full_clean()
    
    def test_get_or_create_for_date(self):
        """Test get or create functionality"""
        tomorrow = timezone.now().date() + timedelta(days=1)
        
        # Should create new slots
        slots1, created1 = DailySlots.get_or_create_for_date(tomorrow, self.admin_user)
        self.assertTrue(created1)
        self.assertEqual(slots1.am_slots, 6)
        self.assertEqual(slots1.pm_slots, 8)
        
        # Should get existing slots
        slots2, created2 = DailySlots.get_or_create_for_date(tomorrow, self.admin_user)
        self.assertFalse(created2)
        self.assertEqual(slots1.id, slots2.id)
    
    def test_availability_for_range(self):
        """Test getting availability for date range"""
        start_date = timezone.now().date() + timedelta(days=1)
        end_date = start_date + timedelta(days=5)
        
        # Create slots for one day
        DailySlots.objects.create(
            date=start_date + timedelta(days=2),
            am_slots=4,
            pm_slots=6,
            created_by=self.admin_user
        )
        
        availability = DailySlots.get_availability_for_range(start_date, end_date)
        
        # Should have default availability for dates without slots
        # and custom availability for the date with slots
        self.assertIn(start_date, availability)
        self.assertEqual(availability[start_date + timedelta(days=2)]['am_total'], 4)
        self.assertEqual(availability[start_date + timedelta(days=2)]['pm_total'], 6)


class AppointmentModelTest(TestCase):
    """Test Appointment model functionality for AM/PM system"""
    
    def setUp(self):
        # Create test data
        self.admin_role = Role.objects.create(name='Admin', can_manage_appointments=True)
        self.dentist_role = Role.objects.create(name='Dentist', can_manage_appointments=True)
        
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            role=self.admin_role
        )
        
        self.dentist_user = User.objects.create_user(
            username='dentist',
            email='dentist@test.com',
            password='testpass123',
            role=self.dentist_role,
            is_active_dentist=True
        )
        
        self.patient = Patient.objects.create(
            first_name='Jane',
            last_name='Smith',
            email='jane@test.com'
        )
        
        self.service = Service.objects.create(
            name='Checkup',
            price=150.00,
            duration_minutes=45
        )
        
        self.tomorrow = timezone.now().date() + timedelta(days=1)
    
    def test_create_appointment(self):
        """Test creating an appointment"""
        appointment = Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=self.tomorrow,
            period='AM',
            patient_type='new',
            reason='Regular checkup'
        )
        
        self.assertEqual(appointment.status, 'pending')
        self.assertEqual(appointment.period, 'AM')
        self.assertEqual(appointment.appointment_date, self.tomorrow)
    
    def test_appointment_datetime_property(self):
        """Test appointment datetime property"""
        am_appointment = Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=self.tomorrow,
            period='AM'
        )
        
        pm_appointment = Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=self.tomorrow,
            period='PM'
        )
        
        # AM should return 8:00 AM
        am_datetime = am_appointment.appointment_datetime
        self.assertEqual(am_datetime.hour, 8)
        self.assertEqual(am_datetime.minute, 0)
        
        # PM should return 1:00 PM
        pm_datetime = pm_appointment.appointment_datetime
        self.assertEqual(pm_datetime.hour, 13)
        self.assertEqual(pm_datetime.minute, 0)
    
    def test_appointment_validation(self):
        """Test appointment validation rules"""
        # Test past date validation
        yesterday = timezone.now().date() - timedelta(days=1)
        
        with self.assertRaises(ValidationError):
            appointment = Appointment(
                patient=self.patient,
                service=self.service,
                appointment_date=yesterday,
                period='AM'
            )
            appointment.full_clean()
        
        # Test Sunday validation
        today = timezone.now().date()
        days_ahead = 6 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        sunday = today + timedelta(days_ahead)
        
        with self.assertRaises(ValidationError):
            appointment = Appointment(
                patient=self.patient,
                service=self.service,
                appointment_date=sunday,
                period='AM'
            )
            appointment.full_clean()
    
    def test_appointment_approval_workflow(self):
        """Test appointment approval workflow"""
        appointment = Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=self.tomorrow,
            period='AM',
            status='pending'
        )
        
        # Test approval
        appointment.approve(self.admin_user, self.dentist_user)
        appointment.refresh_from_db()
        
        self.assertEqual(appointment.status, 'approved')
        self.assertEqual(appointment.approved_by, self.admin_user)
        self.assertEqual(appointment.assigned_dentist, self.dentist_user)
        self.assertIsNotNone(appointment.approved_at)
    
    def test_appointment_status_transitions(self):
        """Test appointment status transitions"""
        appointment = Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=self.tomorrow,
            period='AM',
            status='pending'
        )
        
        # Test reject
        appointment.reject()
        self.assertEqual(appointment.status, 'rejected')
        
        # Reset to approved for further tests
        appointment.status = 'approved'
        appointment.save()
        
        # Test cancel
        appointment.cancel()
        self.assertEqual(appointment.status, 'cancelled')
        
        # Reset to approved
        appointment.status = 'approved'
        appointment.save()
        
        # Test complete
        appointment.complete()
        self.assertEqual(appointment.status, 'completed')
    
    def test_can_book_appointment(self):
        """Test slot availability checking"""
        # Create daily slots
        DailySlots.objects.create(
            date=self.tomorrow,
            am_slots=2,
            pm_slots=3,
            created_by=self.admin_user
        )
        
        # Should be able to book initially
        can_book, message = Appointment.can_book_appointment(self.tomorrow, 'AM')
        self.assertTrue(can_book)
        self.assertIn('2 AM slots available', message)
        
        # Create 2 AM appointments
        Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=self.tomorrow,
            period='AM',
            status='approved'
        )
        Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=self.tomorrow,
            period='AM',
            status='pending'
        )
        
        # Should not be able to book more AM slots
        can_book, message = Appointment.can_book_appointment(self.tomorrow, 'AM')
        self.assertFalse(can_book)
        self.assertIn('No AM slots available', message)
        
        # PM should still be available
        can_book, message = Appointment.can_book_appointment(self.tomorrow, 'PM')
        self.assertTrue(can_book)
        self.assertIn('3 PM slots available', message)
    
    def test_can_be_cancelled_property(self):
        """Test cancellation rules"""
        # Future appointment - should be cancellable
        future_date = timezone.now().date() + timedelta(days=2)
        future_appointment = Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=future_date,
            period='AM',
            status='approved'
        )
        self.assertTrue(future_appointment.can_be_cancelled)
        
        # Tomorrow's appointment - should not be cancellable (within 24 hours)
        tomorrow_appointment = Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=self.tomorrow,
            period='AM',
            status='approved'
        )
        self.assertFalse(tomorrow_appointment.can_be_cancelled)
        
        # Completed appointment - should not be cancellable
        completed_appointment = Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=future_date,
            period='PM',
            status='completed'
        )
        self.assertFalse(completed_appointment.can_be_cancelled)


class AppointmentUtilsTest(TestCase):
    """Test appointment utility functions"""
    
    def setUp(self):
        self.admin_role = Role.objects.create(name='Admin', can_manage_appointments=True)
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            role=self.admin_role
        )
        
        self.patient = Patient.objects.create(
            first_name='Test',
            last_name='Patient',
            email='test@test.com'
        )
        
        self.service = Service.objects.create(
            name='Test Service',
            price=100.00,
            duration_minutes=30
        )
    
    def test_create_appointment_simple(self):
        """Test simple appointment creation utility"""
        from appointments.utils import create_appointment_simple
        
        tomorrow = timezone.now().date() + timedelta(days=1)
        
        # Create daily slots first
        DailySlots.objects.create(
            date=tomorrow,
            am_slots=5,
            pm_slots=5,
            created_by=self.admin_user
        )
        
        appointment, created = create_appointment_simple(
            patient=self.patient,
            service=self.service,
            appointment_date=tomorrow,
            period='AM',
            patient_type='new',
            reason='Test appointment'
        )
        
        self.assertTrue(created)
        self.assertEqual(appointment.patient, self.patient)
        self.assertEqual(appointment.service, self.service)
        self.assertEqual(appointment.appointment_date, tomorrow)
        self.assertEqual(appointment.period, 'AM')
        self.assertEqual(appointment.status, 'pending')
    
    def test_get_available_slots_for_date(self):
        """Test getting available slots for a date"""
        from appointments.utils import get_available_slots_for_date
        
        tomorrow = timezone.now().date() + timedelta(days=1)
        
        # Without DailySlots - should return defaults
        slots = get_available_slots_for_date(tomorrow)
        self.assertEqual(slots['am_available'], 6)
        self.assertEqual(slots['pm_available'], 8)
        
        # With custom DailySlots
        DailySlots.objects.create(
            date=tomorrow,
            am_slots=3,
            pm_slots=4,
            created_by=self.admin_user
        )
        
        slots = get_available_slots_for_date(tomorrow)
        self.assertEqual(slots['am_total'], 3)
        self.assertEqual(slots['pm_total'], 4)
        self.assertEqual(slots['am_available'], 3)
        self.assertEqual(slots['pm_available'], 4)
    
    def test_validate_appointment_date(self):
        """Test appointment date validation utility"""
        from appointments.utils import validate_appointment_date
        
        # Valid future date
        future_date = timezone.now().date() + timedelta(days=1)
        is_valid, message = validate_appointment_date(future_date)
        self.assertTrue(is_valid)
        
        # Invalid past date
        past_date = timezone.now().date() - timedelta(days=1)
        is_valid, message = validate_appointment_date(past_date)
        self.assertFalse(is_valid)
        self.assertIn('cannot be today or in the past', message)
        
        # Invalid Sunday
        today = timezone.now().date()
        days_ahead = 6 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        sunday = today + timedelta(days_ahead)
        
        is_valid, message = validate_appointment_date(sunday)
        self.assertFalse(is_valid)
        self.assertIn('No appointments available on Sundays', message)
    
    def test_get_period_display_time(self):
        """Test period display time utility"""
        from appointments.utils import get_period_display_time
        
        self.assertEqual(get_period_display_time('AM'), '8:00 AM - 12:00 PM')
        self.assertEqual(get_period_display_time('PM'), '1:00 PM - 6:00 PM')
        self.assertEqual(get_period_display_time('INVALID'), 'Invalid period')


class AppointmentIntegrationTest(TestCase):
    """Integration tests for appointment system"""
    
    def setUp(self):
        self.admin_role = Role.objects.create(name='Admin', can_manage_appointments=True)
        self.dentist_role = Role.objects.create(name='Dentist', can_manage_appointments=True)
        
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            role=self.admin_role
        )
        
        self.dentist_user = User.objects.create_user(
            username='dentist',
            email='dentist@test.com',
            password='testpass123',
            role=self.dentist_role,
            is_active_dentist=True
        )
        
        self.patient = Patient.objects.create(
            first_name='Integration',
            last_name='Test',
            email='integration@test.com'
        )
        
        self.service = Service.objects.create(
            name='Integration Service',
            price=200.00,
            duration_minutes=60
        )
        
        self.tomorrow = timezone.now().date() + timedelta(days=1)
    
    def test_complete_appointment_workflow(self):
        """Test complete appointment workflow from booking to completion"""
        # Step 1: Create daily slots
        slots = DailySlots.objects.create(
            date=self.tomorrow,
            am_slots=2,
            pm_slots=3,
            created_by=self.admin_user
        )
        
        # Step 2: Patient books appointment
        appointment = Appointment.objects.create(
            patient=self.patient,
            service=self.service,
            appointment_date=self.tomorrow,
            period='AM',
            patient_type='new',
            reason='First visit',
            status='pending'
        )
        
        # Verify slot consumption
        self.assertEqual(slots.get_available_am_slots(), 1)  # 2 - 1 pending
        
        # Step 3: Admin approves appointment
        appointment.approve(self.admin_user, self.dentist_user)
        appointment.refresh_from_db()
        
        self.assertEqual(appointment.status, 'approved')
        self.assertEqual(appointment.assigned_dentist, self.dentist_user)
        self.assertEqual(appointment.approved_by, self.admin_user)
        
        # Slot still consumed (approved status)
        self.assertEqual(slots.get_available_am_slots(), 1)
        
        # Step 4: Mark as completed
        appointment.complete()
        appointment.refresh_from_db()
        
        self.assertEqual(appointment.status, 'completed')
        
        # Slot still consumed (completed status blocks slots)
        self.assertEqual(slots.get_available_am_slots(), 1)
    
    def test_slot_availability_with_multiple_appointments(self):
        """Test slot availability calculation with various appointment statuses"""
        # Create slots
        DailySlots.objects.create(
            date=self.tomorrow,
            am_slots=5,
            pm_slots=5,
            created_by=self.admin_user
        )
        
        # Create appointments with different statuses
        statuses_and_periods = [
            ('pending', 'AM'),     # Should block slot
            ('approved', 'AM'),    # Should block slot
            ('completed', 'AM'),   # Should block slot
            ('rejected', 'AM'),    # Should NOT block slot
            ('cancelled', 'AM'),   # Should NOT block slot
            ('pending', 'PM'),     # Should block slot
            ('approved', 'PM'),    # Should block slot
        ]
        
        for status, period in statuses_and_periods:
            Appointment.objects.create(
                patient=self.patient,
                service=self.service,
                appointment_date=self.tomorrow,
                period=period,
                status=status
            )
        
        # Get fresh slots object
        slots = DailySlots.objects.get(date=self.tomorrow)
        
        # AM: 5 total - 3 blocking (pending, approved, completed) = 2 available
        self.assertEqual(slots.get_available_am_slots(), 2)
        
        # PM: 5 total - 2 blocking (pending, approved) = 3 available
        self.assertEqual(slots.get_available_pm_slots(), 3)