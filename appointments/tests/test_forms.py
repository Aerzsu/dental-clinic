# appointments/tests/test_forms.py
"""
Tests for appointment forms in the AM/PM slot system
"""
from django.test import TestCase
from django.utils import timezone
from datetime import date, timedelta
from appointments.forms import AppointmentForm, DailySlotsForm, PublicBookingForm
from appointments.models import DailySlots, Appointment
from patients.models import Patient
from services.models import Service
from users.models import User, Role


class AppointmentFormTest(TestCase):
    """Test AppointmentForm for staff/admin use"""
    
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
            email='test@test.com',
            is_active=True
        )
        
        self.service = Service.objects.create(
            name='Test Service',
            price=100.00,
            duration_minutes=30,
            is_archived=False
        )
        
        self.tomorrow = timezone.now().date() + timedelta(days=1)
    
    def test_valid_appointment_form(self):
        """Test valid appointment form submission"""
        # Create slots for tomorrow
        DailySlots.objects.create(
            date=self.tomorrow,
            am_slots=5,
            pm_slots=5,
            created_by=self.admin_user
        )
        
        form_data = {
            'patient': self.patient.id,
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'AM',
            'patient_type': 'returning',
            'reason': 'Regular checkup'
        }
        
        form = AppointmentForm(data=form_data, user=self.admin_user)
        self.assertTrue(form.is_valid())
    
    def test_past_date_validation(self):
        """Test form rejects past dates"""
        yesterday = timezone.now().date() - timedelta(days=1)
        
        form_data = {
            'patient': self.patient.id,
            'service': self.service.id,
            'appointment_date': yesterday,
            'period': 'AM',
            'patient_type': 'returning'
        }
        
        form = AppointmentForm(data=form_data, user=self.admin_user)
        self.assertFalse(form.is_valid())
        self.assertIn('appointment_date', form.errors)
    
    def test_sunday_validation(self):
        """Test form rejects Sundays"""
        # Find next Sunday
        today = timezone.now().date()
        days_ahead = 6 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        sunday = today + timedelta(days_ahead)
        
        form_data = {
            'patient': self.patient.id,
            'service': self.service.id,
            'appointment_date': sunday,
            'period': 'AM',
            'patient_type': 'returning'
        }
        
        form = AppointmentForm(data=form_data, user=self.admin_user)
        self.assertFalse(form.is_valid())
        self.assertIn('appointment_date', form.errors)
    
    def test_no_available_slots_validation(self):
        """Test form rejects when no slots available"""
        # Create slots with 0 AM slots
        DailySlots.objects.create(
            date=self.tomorrow,
            am_slots=0,
            pm_slots=5,
            created_by=self.admin_user
        )
        
        form_data = {
            'patient': self.patient.id,
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'AM',
            'patient_type': 'returning'
        }
        
        form = AppointmentForm(data=form_data, user=self.admin_user)
        self.assertFalse(form.is_valid())
        self.assertIn('Cannot book appointment', str(form.non_field_errors()))


class DailySlotsFormTest(TestCase):
    """Test DailySlotsForm for slot management"""
    
    def setUp(self):
        self.tomorrow = timezone.now().date() + timedelta(days=1)
    
    def test_valid_daily_slots_form(self):
        """Test valid daily slots form"""
        form_data = {
            'date': self.tomorrow,
            'am_slots': 6,
            'pm_slots': 8,
            'notes': 'Regular day'
        }
        
        form = DailySlotsForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_sunday_with_positive_slots_validation(self):
        """Test form rejects Sunday with positive slots"""
        # Find next Sunday
        today = timezone.now().date()
        days_ahead = 6 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        sunday = today + timedelta(days_ahead)
        
        form_data = {
            'date': sunday,
            'am_slots': 6,
            'pm_slots': 8,
            'notes': 'Should fail'
        }
        
        form = DailySlotsForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('date', form.errors)
    
    def test_sunday_with_zero_slots_valid(self):
        """Test form accepts Sunday with zero slots"""
        # Find next Sunday
        today = timezone.now().date()
        days_ahead = 6 - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        sunday = today + timedelta(days_ahead)
        
        form_data = {
            'date': sunday,
            'am_slots': 0,
            'pm_slots': 0,
            'notes': 'Sunday - closed'
        }
        
        form = DailySlotsForm(data=form_data)
        self.assertTrue(form.is_valid())


class PublicBookingFormTest(TestCase):
    """Test PublicBookingForm for patient booking"""
    
    def setUp(self):
        self.admin_role = Role.objects.create(name='Admin', can_manage_appointments=True)
        self.admin_user = User.objects.create_user(
            username='admin',
            email='admin@test.com',
            password='testpass123',
            role=self.admin_role
        )
        
        self.existing_patient = Patient.objects.create(
            first_name='Existing',
            last_name='Patient',
            email='existing@test.com',
            contact_number='+639123456789',
            is_active=True
        )
        
        self.service = Service.objects.create(
            name='Consultation',
            price=150.00,
            duration_minutes=30,
            is_archived=False
        )
        
        self.tomorrow = timezone.now().date() + timedelta(days=1)
        
        # Create slots for tomorrow
        DailySlots.objects.create(
            date=self.tomorrow,
            am_slots=5,
            pm_slots=5,
            created_by=self.admin_user
        )
    
    def test_new_patient_booking(self):
        """Test new patient booking form"""
        form_data = {
            'patient_type': 'new',
            'first_name': 'New',
            'last_name': 'Patient',
            'email': 'new@test.com',
            'contact_number': '+639987654321',
            'address': '123 Test Street',
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'AM',
            'reason': 'First visit',
            'agreed_to_terms': True
        }
        
        form = PublicBookingForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_existing_patient_booking_by_email(self):
        """Test existing patient booking using email"""
        form_data = {
            'patient_type': 'existing',
            'patient_identifier': 'existing@test.com',
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'PM',
            'reason': 'Follow-up',
            'agreed_to_terms': True
        }
        
        form = PublicBookingForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['patient'], self.existing_patient)
    
    def test_existing_patient_booking_by_phone(self):
        """Test existing patient booking using phone"""
        form_data = {
            'patient_type': 'existing',
            'patient_identifier': '+639123456789',
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'AM',
            'reason': 'Checkup',
            'agreed_to_terms': True
        }
        
        form = PublicBookingForm(data=form_data)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['patient'], self.existing_patient)
    
    def test_existing_patient_not_found(self):
        """Test existing patient not found"""
        form_data = {
            'patient_type': 'existing',
            'patient_identifier': 'notfound@test.com',
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'AM',
            'agreed_to_terms': True
        }
        
        form = PublicBookingForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('No patient record found', str(form.non_field_errors()))
    
    def test_new_patient_duplicate_email(self):
        """Test new patient with existing email"""
        form_data = {
            'patient_type': 'new',
            'first_name': 'Another',
            'last_name': 'Patient',
            'email': 'existing@test.com',  # Same as existing patient
            'contact_number': '+639111222333',
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'AM',
            'agreed_to_terms': True
        }
        
        form = PublicBookingForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('already exists', str(form.non_field_errors()))
    
    def test_invalid_phone_number(self):
        """Test invalid Philippine phone number format"""
        form_data = {
            'patient_type': 'new',
            'first_name': 'Test',
            'last_name': 'Patient',
            'email': 'test@test.com',
            'contact_number': '1234567890',  # Invalid format
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'AM',
            'agreed_to_terms': True
        }
        
        form = PublicBookingForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('contact_number', form.errors)
    
    def test_terms_not_agreed(self):
        """Test form requires terms agreement"""
        form_data = {
            'patient_type': 'new',
            'first_name': 'Test',
            'last_name': 'Patient',
            'email': 'test@test.com',
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'AM',
            'agreed_to_terms': False  # Not agreed
        }
        
        form = PublicBookingForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('agreed_to_terms', form.errors)
    
    def test_save_method_new_patient(self):
        """Test form save method creates new patient and appointment"""
        form_data = {
            'patient_type': 'new',
            'first_name': 'Save',
            'last_name': 'Test',
            'email': 'save@test.com',
            'contact_number': '+639888777666',
            'address': '456 Save Street',
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'AM',
            'reason': 'Test save',
            'agreed_to_terms': True
        }
        
        form = PublicBookingForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        appointment = form.save()
        
        # Check appointment was created
        self.assertEqual(appointment.patient.first_name, 'Save')
        self.assertEqual(appointment.patient.last_name, 'Test')
        self.assertEqual(appointment.patient.email, 'save@test.com')
        self.assertEqual(appointment.service, self.service)
        self.assertEqual(appointment.appointment_date, self.tomorrow)
        self.assertEqual(appointment.period, 'AM')
        self.assertEqual(appointment.patient_type, 'new')
        self.assertEqual(appointment.status, 'pending')
    
    def test_save_method_existing_patient(self):
        """Test form save method uses existing patient"""
        form_data = {
            'patient_type': 'existing',
            'patient_identifier': 'existing@test.com',
            'service': self.service.id,
            'appointment_date': self.tomorrow,
            'period': 'PM',
            'reason': 'Follow-up appointment',
            'agreed_to_terms': True
        }
        
        form = PublicBookingForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        appointment = form.save()
        
        # Check appointment uses existing patient
        self.assertEqual(appointment.patient, self.existing_patient)
        self.assertEqual(appointment.patient_type, 'returning')
        self.assertEqual(appointment.status, 'pending')