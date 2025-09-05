# appointments/tests/test_time_slot_blocking.py
from django.test import TestCase, TransactionTestCase
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, date, time, timedelta
from unittest.mock import patch
import threading
import time as time_module

from appointments.models import Appointment, Schedule
from appointments.views import create_appointment_atomic
from patients.models import Patient
from services.models import Service
from users.models import User
from core.models import Holiday, SystemSetting


class TimeSlotBlockingTestCase(TestCase):
    """Test suite for time slot blocking functionality"""
    
    def setUp(self):
        # Create test data
        self.dentist = User.objects.create_user(
            username='dentist1',
            email='dentist@clinic.com',
            first_name='John',
            last_name='Doe',
            is_active_dentist=True
        )
        
        self.patient = Patient.objects.create(
            first_name='Jane',
            last_name='Smith',
            email='jane@example.com',
            contact_number='+639123456789'
        )
        
        self.service_30min = Service.objects.create(
            name='Cleaning',
            duration_minutes=30,
            min_price=1500,
            max_price=2000
        )
        
        self.service_60min = Service.objects.create(
            name='Root Canal',
            duration_minutes=60,
            min_price=5000,
            max_price=8000
        )
        
        self.appointment_date = (timezone.now() + timedelta(days=1)).date()
    
    def test_basic_time_slot_blocking(self):
        """Test that a basic appointment blocks its time slot"""
        appointment = self._create_test_appointment(
            start_time=time(14, 0),  # 2:00 PM
            service=self.service_30min
        )
        
        # Try to create another appointment at the same time
        with self.assertRaises(ValidationError):
            self._create_test_appointment(
                start_time=time(14, 0),
                service=self.service_30min
            )
    
    def test_service_duration_blocking(self):
        """Test that longer services block multiple time slots"""
        # Book 60-minute service at 2:00 PM (should end at 3:00 PM)
        appointment1 = self._create_test_appointment(
            start_time=time(14, 0),
            service=self.service_60min
        )
        
        # Try to book 30-minute service at 2:30 PM (should conflict)
        with self.assertRaises(ValidationError):
            self._create_test_appointment(
                start_time=time(14, 30),
                service=self.service_30min
            )
        
        # Should be able to book at 3:00 PM (no buffer for this test)
        with patch.object(SystemSetting, 'get_int_setting', return_value=0):  # No buffer
            appointment2 = self._create_test_appointment(
                start_time=time(15, 0),
                service=self.service_30min
            )
            self.assertEqual(appointment2.schedule.start_time, time(15, 0))
    
    def test_buffer_time_blocking(self):
        """Test that buffer time is respected between appointments"""
        # Create appointment ending at 3:00 PM with 15-minute buffer
        appointment1 = self._create_test_appointment(
            start_time=time(14, 30),
            service=self.service_30min,
            buffer_minutes=15
        )
        
        # Try to book at 3:00 PM (should conflict due to buffer)
        with self.assertRaises(ValidationError):
            self._create_test_appointment(
                start_time=time(15, 0),
                service=self.service_30min
            )
        
        # Should be able to book at 3:15 PM
        appointment2 = self._create_test_appointment(
            start_time=time(15, 15),
            service=self.service_30min
        )
        self.assertEqual(appointment2.schedule.start_time, time(15, 15))
    
    def test_status_based_blocking(self):
        """Test that only certain appointment statuses block time slots"""
        blocking_statuses = ['pending', 'approved', 'completed']
        non_blocking_statuses = ['cancelled', 'rejected', 'did_not_arrive']
        
        for status in blocking_statuses:
            with self.subTest(status=status):
                # Create appointment with blocking status
                appointment = self._create_test_appointment(
                    start_time=time(10, 0),
                    service=self.service_30min
                )
                appointment.status = status
                appointment.save()
                
                # Should not be able to create another appointment
                with self.assertRaises(ValidationError):
                    self._create_test_appointment(
                        start_time=time(10, 0),
                        service=self.service_30min
                    )
                
                # Clean up
                appointment.delete()
        
        for status in non_blocking_statuses:
            with self.subTest(status=status):
                # Create appointment with non-blocking status
                appointment = self._create_test_appointment(
                    start_time=time(11, 0),
                    service=self.service_30min
                )
                appointment.status = status
                appointment.save()
                
                # Should be able to create another appointment
                appointment2 = self._create_test_appointment(
                    start_time=time(11, 0),
                    service=self.service_30min
                )
                self.assertEqual(appointment2.schedule.start_time, time(11, 0))
                
                # Clean up
                appointment.delete()
                appointment2.delete()
    
    def test_lunch_break_blocking(self):
        """Test that appointments can't be scheduled during lunch break"""
        # Try to schedule during lunch (12:00 PM - 1:00 PM)
        with self.assertRaises(ValidationError) as cm:
            self._create_test_appointment(
                start_time=time(12, 30),
                service=self.service_30min
            )
        
        self.assertIn('lunch break', str(cm.exception).lower())
    
    def test_clinic_hours_blocking(self):
        """Test that appointments can't be scheduled outside clinic hours"""
        # Before opening (10:00 AM)
        with self.assertRaises(ValidationError):
            self._create_test_appointment(
                start_time=time(9, 0),
                service=self.service_30min
            )
        
        # After closing (6:00 PM)
        with self.assertRaises(ValidationError):
            self._create_test_appointment(
                start_time=time(18, 30),
                service=self.service_30min
            )
        
        # Service extending past closing time
        with self.assertRaises(ValidationError):
            self._create_test_appointment(
                start_time=time(17, 45),
                service=self.service_30min  # Would end at 6:15 PM
            )
    
    def test_holiday_blocking(self):
        """Test that appointments can't be scheduled on holidays"""
        holiday_date = self.appointment_date
        Holiday.objects.create(
            name='Test Holiday',
            date=holiday_date,
            is_active=True
        )
        
        with self.assertRaises(ValidationError) as cm:
            self._create_test_appointment(
                start_time=time(14, 0),
                service=self.service_30min,
                appointment_date=holiday_date
            )
        
        self.assertIn('holiday', str(cm.exception).lower())
    
    def test_sunday_blocking(self):
        """Test that appointments can't be scheduled on Sundays"""
        # Find next Sunday
        sunday_date = self.appointment_date
        while sunday_date.weekday() != 6:
            sunday_date += timedelta(days=1)
        
        with self.assertRaises(ValidationError) as cm:
            self._create_test_appointment(
                start_time=time(14, 0),
                service=self.service_30min,
                appointment_date=sunday_date
            )
        
        self.assertIn('sunday', str(cm.exception).lower())
    
    def test_past_date_blocking(self):
        """Test that appointments can't be scheduled in the past"""
        past_date = timezone.now().date() - timedelta(days=1)
        
        with self.assertRaises(ValidationError) as cm:
            self._create_test_appointment(
                start_time=time(14, 0),
                service=self.service_30min,
                appointment_date=past_date
            )
        
        self.assertIn('future', str(cm.exception).lower())
    
    def _create_test_appointment(self, start_time, service, appointment_date=None, buffer_minutes=15):
        """Helper method to create test appointments"""
        if appointment_date is None:
            appointment_date = self.appointment_date
        
        return create_appointment_atomic(
            patient=self.patient,
            dentist=self.dentist,
            service=service,
            appointment_date=appointment_date,
            appointment_time=start_time,
            patient_type='returning',
            reason='Test appointment',
            buffer_minutes=buffer_minutes
        )[0]


class RaceConditionTestCase(TransactionTestCase):
    """Test race condition prevention using TransactionTestCase for better threading support"""
    
    def setUp(self):
        self.dentist = User.objects.create_user(
            username='dentist1',
            email='dentist@clinic.com',
            first_name='John',
            last_name='Doe',
            is_active_dentist=True
        )
        
        self.patient1 = Patient.objects.create(
            first_name='Patient',
            last_name='One',
            email='patient1@example.com'
        )
        
        self.patient2 = Patient.objects.create(
            first_name='Patient',
            last_name='Two',
            email='patient2@example.com'
        )
        
        self.service = Service.objects.create(
            name='Cleaning',
            duration_minutes=30,
            min_price=1500,
            max_price=2000
        )
        
        self.appointment_date = (timezone.now() + timedelta(days=1)).date()
        self.appointment_time = time(14, 0)  # 2:00 PM
    
    def test_concurrent_booking_prevention(self):
        """Test that concurrent bookings for the same time slot are prevented"""
        results = {}
        exceptions = {}
        
        def book_appointment(patient, result_key):
            try:
                appointment = create_appointment_atomic(
                    patient=patient,
                    dentist=self.dentist,
                    service=self.service,
                    appointment_date=self.appointment_date,
                    appointment_time=self.appointment_time,
                    patient_type='returning',
                    buffer_minutes=15
                )
                results[result_key] = appointment[0]
            except Exception as e:
                exceptions[result_key] = e
        
        # Create two threads trying to book the same time slot
        thread1 = threading.Thread(
            target=book_appointment, 
            args=(self.patient1, 'patient1')
        )
        thread2 = threading.Thread(
            target=book_appointment, 
            args=(self.patient2, 'patient2')
        )
        
        # Start both threads simultaneously
        thread1.start()
        thread2.start()
        
        # Wait for both to complete
        thread1.join()
        thread2.join()
        
        # One should succeed, one should fail
        success_count = len(results)
        failure_count = len(exceptions)
        
        self.assertEqual(success_count, 1, "Exactly one appointment should succeed")
        self.assertEqual(failure_count, 1, "Exactly one appointment should fail")
        
        # The successful appointment should be properly saved
        if results:
            appointment = list(results.values())[0]
            self.assertEqual(appointment.schedule.start_time, self.appointment_time)
            self.assertEqual(appointment.dentist, self.dentist)
        
        # The failed attempt should have a meaningful error
        if exceptions:
            exception = list(exceptions.values())[0]
            self.assertIn('conflict', str(exception).lower())
    
    def test_rapid_successive_bookings(self):
        """Test multiple rapid bookings in succession"""
        times = [time(10, 0), time(10, 30), time(11, 0), time(11, 30), time(14, 0)]
        patients = [
            Patient.objects.create(
                first_name=f'Patient{i}',
                last_name='Test',
                email=f'patient{i}@example.com'
            ) for i in range(5)
        ]
        
        results = {}
        exceptions = {}
        
        def book_appointment(patient, appointment_time, result_key):
            try:
                appointment = create_appointment_atomic(
                    patient=patient,
                    dentist=self.dentist,
                    service=self.service,
                    appointment_date=self.appointment_date,
                    appointment_time=appointment_time,
                    patient_type='new',
                    buffer_minutes=15
                )
                results[result_key] = appointment[0]
            except Exception as e:
                exceptions[result_key] = e
        
        # Create and start multiple threads
        threads = []
        for i, (patient, appointment_time) in enumerate(zip(patients, times)):
            thread = threading.Thread(
                target=book_appointment,
                args=(patient, appointment_time, f'booking_{i}')
            )
            threads.append(thread)
            thread.start()
            # Small delay to make race conditions more likely
            time_module.sleep(0.01)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All bookings should succeed since they're for different times
        self.assertEqual(len(results), 5, "All bookings should succeed")
        self.assertEqual(len(exceptions), 0, "No bookings should fail")
        
        # Verify all appointments are properly saved
        for i, appointment in enumerate(results.values()):
            self.assertEqual(appointment.dentist, self.dentist)
            self.assertIn(appointment.schedule.start_time, times)


class ConflictDetectionTestCase(TestCase):
    """Test the conflict detection algorithm"""
    
    def setUp(self):
        self.dentist = User.objects.create_user(
            username='dentist1',
            email='dentist@clinic.com',
            first_name='John',
            last_name='Doe',
            is_active_dentist=True
        )
        
        self.patient = Patient.objects.create(
            first_name='Jane',
            last_name='Smith',
            email='jane@example.com'
        )
        
        self.service = Service.objects.create(
            name='Test Service',
            duration_minutes=30,
            min_price=1500,
            max_price=2000
        )
        
        self.appointment_date = (timezone.now() + timedelta(days=1)).date()
    
    def test_exact_overlap_detection(self):
        """Test detection of exact time overlaps"""
        # Create first appointment 2:00-2:30 PM
        existing_appointment = self._create_appointment(
            start_time=time(14, 0),
            end_time=time(14, 30)
        )
        
        # Test exact same time
        conflicts = Appointment.get_conflicting_appointments(
            dentist=self.dentist,
            start_datetime=datetime.combine(self.appointment_date, time(14, 0)),
            end_datetime=datetime.combine(self.appointment_date, time(14, 30))
        )
        self.assertEqual(len(conflicts), 1)
    
    def test_partial_overlap_detection(self):
        """Test detection of partial overlaps"""
        # Existing appointment: 2:00-3:00 PM  
        existing_appointment = self._create_appointment(
            start_time=time(14, 0),
            end_time=time(15, 0)
        )
        
        # Test cases for partial overlaps
        test_cases = [
            # New appointment starts during existing
            (time(14, 30), time(15, 30)),  # 2:30-3:30 PM
            # New appointment ends during existing  
            (time(13, 30), time(14, 30)),  # 1:30-2:30 PM
            # New appointment completely within existing
            (time(14, 15), time(14, 45)),  # 2:15-2:45 PM
            # New appointment completely contains existing
            (time(13, 30), time(15, 30)),  # 1:30-3:30 PM
        ]
        
        for start, end in test_cases:
            with self.subTest(start=start, end=end):
                conflicts = Appointment.get_conflicting_appointments(
                    dentist=self.dentist,
                    start_datetime=datetime.combine(self.appointment_date, start),
                    end_datetime=datetime.combine(self.appointment_date, end)
                )
                self.assertEqual(len(conflicts), 1, 
                    f"Should detect conflict for {start}-{end} vs existing 14:00-15:00")
    
    def test_no_conflict_detection(self):
        """Test that adjacent appointments don't conflict"""
        # Existing appointment: 2:00-2:30 PM
        existing_appointment = self._create_appointment(
            start_time=time(14, 0),
            end_time=time(14, 30)
        )
        
        # Test adjacent times (no buffer for this test)
        test_cases = [
            # Before existing appointment
            (time(13, 30), time(14, 0)),  # 1:30-2:00 PM
            # After existing appointment
            (time(14, 30), time(15, 0)),  # 2:30-3:00 PM
        ]
        
        for start, end in test_cases:
            with self.subTest(start=start, end=end):
                conflicts = Appointment.get_conflicting_appointments(
                    dentist=self.dentist,
                    start_datetime=datetime.combine(self.appointment_date, start),
                    end_datetime=datetime.combine(self.appointment_date, end)
                )
                self.assertEqual(len(conflicts), 0, 
                    f"Should NOT detect conflict for {start}-{end} vs existing 14:00-14:30")
    
    def test_buffer_time_conflict_detection(self):
        """Test that buffer time is included in conflict detection"""
        # Existing appointment: 2:00-2:30 PM with 15-min buffer (effective end: 2:45 PM)
        schedule = Schedule.objects.create(
            dentist=self.dentist,
            date=self.appointment_date,
            start_time=time(14, 0),
            end_time=time(14, 30),
            buffer_minutes=15
        )
        
        existing_appointment = Appointment.objects.create(
            patient=self.patient,
            dentist=self.dentist,
            service=self.service,
            schedule=schedule,
            status='approved'
        )
        
        # Should conflict with appointment starting at 2:30 PM (within buffer)
        conflicts = Appointment.get_conflicting_appointments(
            dentist=self.dentist,
            start_datetime=datetime.combine(self.appointment_date, time(14, 30)),
            end_datetime=datetime.combine(self.appointment_date, time(15, 0))
        )
        self.assertEqual(len(conflicts), 1)
        
        # Should NOT conflict with appointment starting at 2:45 PM (after buffer)
        conflicts = Appointment.get_conflicting_appointments(
            dentist=self.dentist,
            start_datetime=datetime.combine(self.appointment_date, time(14, 45)),
            end_datetime=datetime.combine(self.appointment_date, time(15, 15))
        )
        self.assertEqual(len(conflicts), 0)
    
    def _create_appointment(self, start_time, end_time):
        """Helper to create appointment with specific times"""
        schedule = Schedule.objects.create(
            dentist=self.dentist,
            date=self.appointment_date,
            start_time=start_time,
            end_time=end_time,
            buffer_minutes=0  # No buffer unless specified
        )
        
        return Appointment.objects.create(
            patient=self.patient,
            dentist=self.dentist,
            service=self.service,
            schedule=schedule,
            status='approved'
        )


class PerformanceTestCase(TestCase):
    """Test performance of time slot blocking queries"""
    
    def setUp(self):
        # Create multiple dentists and appointments for performance testing
        self.dentists = [
            User.objects.create_user(
                username=f'dentist{i}',
                email=f'dentist{i}@clinic.com',
                first_name=f'Dentist',
                last_name=f'{i}',
                is_active_dentist=True
            ) for i in range(5)
        ]
        
        self.patients = [
            Patient.objects.create(
                first_name=f'Patient{i}',
                last_name='Test',
                email=f'patient{i}@example.com'
            ) for i in range(50)
        ]
        
        self.service = Service.objects.create(
            name='Test Service',
            duration_minutes=30,
            min_price=1500,
            max_price=2000
        )
    
    @patch('django.test.utils.override_settings')
    def test_large_dataset_performance(self):
        """Test performance with many existing appointments"""
        # Create 100 appointments across different dentists and dates
        appointments = []
        for i in range(100):
            dentist = self.dentists[i % 5]
            patient = self.patients[i % 50]
            appointment_date = timezone.now().date() + timedelta(days=i % 30)
            
            schedule = Schedule.objects.create(
                dentist=dentist,
                date=appointment_date,
                start_time=time(10 + (i % 8), 0),  # 10 AM to 5 PM
                end_time=time(10 + (i % 8), 30),
                buffer_minutes=15
            )
            
            appointment = Appointment.objects.create(
                patient=patient,
                dentist=dentist,
                service=self.service,
                schedule=schedule,
                status='approved'
            )
            appointments.append(appointment)
        
        # Test conflict detection performance
        start_time = timezone.now()
        
        conflicts = Appointment.get_conflicting_appointments(
            dentist=self.dentists[0],
            start_datetime=datetime.combine(
                timezone.now().date() + timedelta(days=1),
                time(14, 0)
            ),
            end_datetime=datetime.combine(
                timezone.now().date() + timedelta(days=1),
                time(14, 30)
            )
        )
        
        end_time = timezone.now()
        query_duration = (end_time - start_time).total_seconds()
        
        # Query should complete in under 1 second even with 100 appointments
        self.assertLess(query_duration, 1.0, "Conflict detection should be fast")
        
    def test_query_optimization(self):
        """Test that queries use proper indexes and joins"""
        from django.test.utils import override_settings
        from django.db import connection
        
        with override_settings(DEBUG=True):
            # Clear any existing queries
            connection.queries_log.clear()
            
            # Run conflict detection
            conflicts = Appointment.get_conflicting_appointments(
                dentist=self.dentists[0],
                start_datetime=datetime.combine(
                    timezone.now().date() + timedelta(days=1),
                    time(14, 0)
                ),
                end_datetime=datetime.combine(
                    timezone.now().date() + timedelta(days=1),
                    time(14, 30)
                )
            )
            
            # Check that the query uses appropriate joins
            queries = connection.queries
            self.assertTrue(len(queries) > 0, "Should have executed queries")
            
            # The main query should include joins for related tables
            main_query = queries[-1]['sql'].lower()
            self.assertIn('select_related', main_query.lower() or 'join', "Should use joins for performance")