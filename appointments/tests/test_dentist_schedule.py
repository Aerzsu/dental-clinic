# appointments/tests/test_dentist_schedule.py

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from datetime import time, datetime
from appointments.models import DentistSchedule
from users.models import Role

User = get_user_model()


class DentistScheduleModelTest(TestCase):
    def setUp(self):
        # Create dentist role and user
        self.dentist_role = Role.objects.create(
            name='dentist',
            display_name='Dentist',
            permissions={'appointments': True}
        )
        self.dentist = User.objects.create_user(
            username='dentist1',
            email='dentist@example.com',
            first_name='John',
            last_name='Doe',
            role=self.dentist_role,
            is_active_dentist=True
        )
    
    def test_create_dentist_schedule(self):
        """Test creating a dentist schedule"""
        schedule = DentistSchedule.objects.create(
            dentist=self.dentist,
            weekday=0,  # Monday
            is_working=True,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )
        
        self.assertEqual(schedule.dentist, self.dentist)
        self.assertEqual(schedule.weekday, 0)
        self.assertTrue(schedule.is_working)
        self.assertEqual(schedule.start_time, time(9, 0))
        self.assertEqual(schedule.end_time, time(17, 0))
    
    def test_unique_dentist_weekday_constraint(self):
        """Test that dentist can only have one schedule per weekday"""
        DentistSchedule.objects.create(
            dentist=self.dentist,
            weekday=0,
            is_working=True
        )
        
        with self.assertRaises(IntegrityError):
            DentistSchedule.objects.create(
                dentist=self.dentist,
                weekday=0,  # Same weekday
                is_working=False
            )
    
    def test_working_hours_validation(self):
        """Test validation of working hours"""
        schedule = DentistSchedule(
            dentist=self.dentist,
            weekday=0,
            is_working=True,
            start_time=time(17, 0),  # Start after end
            end_time=time(9, 0)
        )
        
        with self.assertRaises(ValidationError):
            schedule.clean()
    
    def test_lunch_break_validation(self):
        """Test lunch break validation"""
        # Lunch break outside working hours
        schedule = DentistSchedule(
            dentist=self.dentist,
            weekday=0,
            is_working=True,
            start_time=time(9, 0),
            end_time=time(17, 0),
            has_lunch_break=True,
            lunch_start=time(8, 0),  # Before work starts
            lunch_end=time(9, 0)
        )
        
        with self.assertRaises(ValidationError):
            schedule.clean()
        
        # Lunch break too long (over 2 hours)
        schedule2 = DentistSchedule(
            dentist=self.dentist,
            weekday=1,
            is_working=True,
            start_time=time(9, 0),
            end_time=time(17, 0),
            has_lunch_break=True,
            lunch_start=time(12, 0),
            lunch_end=time(15, 0)  # 3 hours lunch
        )
        
        with self.assertRaises(ValidationError):
            schedule2.clean()
    
    def test_working_hours_display(self):
        """Test working hours display property"""
        # Working day
        schedule = DentistSchedule.objects.create(
            dentist=self.dentist,
            weekday=0,
            is_working=True,
            start_time=time(9, 0),
            end_time=time(17, 0),
            has_lunch_break=True,
            lunch_start=time(12, 0),
            lunch_end=time(13, 0)
        )
        
        display = schedule.working_hours_display
        self.assertIn('09:00 AM', display)
        self.assertIn('05:00 PM', display)
        self.assertIn('Lunch', display)
        
        # Non-working day
        schedule2 = DentistSchedule.objects.create(
            dentist=self.dentist,
            weekday=6,  # Sunday
            is_working=False
        )
        
        self.assertEqual(schedule2.working_hours_display, "Not Working")
    
    def test_get_dentist_working_hours(self):
        """Test getting working hours for specific dentist and day"""
        schedule = DentistSchedule.objects.create(
            dentist=self.dentist,
            weekday=0,
            is_working=True
        )
        
        # Should return the schedule
        result = DentistSchedule.get_dentist_working_hours(self.dentist, 0)
        self.assertEqual(result, schedule)
        
        # Should return None for non-working day
        DentistSchedule.objects.create(
            dentist=self.dentist,
            weekday=6,
            is_working=False
        )
        
        result = DentistSchedule.get_dentist_working_hours(self.dentist, 6)
        self.assertIsNone(result)
        
        # Should return None for non-existent schedule
        result = DentistSchedule.get_dentist_working_hours(self.dentist, 3)
        self.assertIsNone(result)
    
    def test_create_default_schedule(self):
        """Test creating default schedule for dentist"""
        schedules = DentistSchedule.create_default_schedule(self.dentist)
        
        self.assertEqual(len(schedules), 7)  # 7 days of the week
        
        # Check Monday to Friday are working days
        for i in range(5):
            schedule = schedules[i]
            self.assertTrue(schedule.is_working)
            self.assertEqual(schedule.start_time, time(10, 0))
            self.assertEqual(schedule.end_time, time(18, 0))
            self.assertTrue(schedule.has_lunch_break)
        
        # Check Saturday and Sunday are non-working days
        for i in range(5, 7):
            schedule = schedules[i]
            self.assertFalse(schedule.is_working)
            self.assertFalse(schedule.has_lunch_break)


class DentistScheduleViewTest(TestCase):
    def setUp(self):
        # Create dentist role and user
        self.dentist_role = Role.objects.create(
            name='dentist',
            display_name='Dentist',
            permissions={'appointments': True}
        )
        self.dentist = User.objects.create_user(
            username='dentist1',
            email='dentist@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe',
            role=self.dentist_role,
            is_active_dentist=True
        )
        
        # Create admin user
        self.admin_role = Role.objects.create(
            name='admin',
            display_name='Admin',
            permissions={'appointments': True, 'maintenance': True}
        )
        self.admin = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='testpass123',
            role=self.admin_role,
            is_superuser=True
        )
        
        self.client = Client()
    
    def test_dentist_schedule_access_permission(self):
        """Test that only dentists can access their schedule page"""
        url = reverse('appointments:dentist_schedule')
        
        # Anonymous user should be redirected to login
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        
        # Regular user without dentist role should be denied
        regular_user = User.objects.create_user(
            username='regular',
            email='regular@example.com',
            password='testpass123'
        )
        self.client.login(username='regular', password='testpass123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        
        # Dentist should have access
        self.client.login(username='dentist1', password='testpass123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
    
    def test_dentist_schedule_get_view(self):
        """Test GET request to dentist schedule view"""
        self.client.login(username='dentist1', password='testpass123')
        url = reverse('appointments:dentist_schedule')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'My Weekly Schedule')
        self.assertContains(response, 'Monday')
        self.assertContains(response, 'Tuesday')
        
        # Should create default schedules for all weekdays
        self.assertEqual(
            DentistSchedule.objects.filter(dentist=self.dentist).count(),
            7
        )
    
    def test_dentist_schedule_post_valid(self):
        """Test POST request with valid schedule data"""
        self.client.login(username='dentist1', password='testpass123')
        url = reverse('appointments:dentist_schedule')
        
        # First create the schedules with GET request
        self.client.get(url)
        
        # Prepare POST data for all 7 days
        post_data = {}
        for day in range(7):
            prefix = f'day_{day}'
            if day < 5:  # Monday to Friday - working days
                post_data.update({
                    f'{prefix}-is_working': 'on',
                    f'{prefix}-start_time': '09:00',
                    f'{prefix}-end_time': '18:00',
                    f'{prefix}-has_lunch_break': 'on',
                    f'{prefix}-lunch_start': '12:00',
                    f'{prefix}-lunch_end': '13:00',
                })
            # Weekends - no working data (defaults to not working)
        
        response = self.client.post(url, post_data, follow=True)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'updated successfully')
        
        # Verify schedule was updated
        monday_schedule = DentistSchedule.objects.get(dentist=self.dentist, weekday=0)
        self.assertTrue(monday_schedule.is_working)
        self.assertEqual(monday_schedule.start_time, time(9, 0))
        self.assertEqual(monday_schedule.end_time, time(18, 0))
    
    def test_dentist_schedule_post_invalid(self):
        """Test POST request with invalid schedule data"""
        self.client.login(username='dentist1', password='testpass123')
        url = reverse('appointments:dentist_schedule')
        
        # First create the schedules with GET request
        self.client.get(url)
        
        # Invalid data - end time before start time
        post_data = {
            'day_0-is_working': 'on',
            'day_0-start_time': '18:00',  # Invalid - after end time
            'day_0-end_time': '09:00',
            'day_0-has_lunch_break': '',
            'day_0-lunch_start': '12:00',
            'day_0-lunch_end': '13:00',
        }
        
        # Add valid data for other days to avoid missing form errors
        for day in range(1, 7):
            prefix = f'day_{day}'
            post_data.update({
                f'{prefix}-is_working': '',
                f'{prefix}-start_time': '10:00',
                f'{prefix}-end_time': '18:00',
                f'{prefix}-has_lunch_break': '',
                f'{prefix}-lunch_start': '12:00',
                f'{prefix}-lunch_end': '13:00',
            })
        
        response = self.client.post(url, post_data)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'End time must be after start time')
    
    def test_schedule_overview_access(self):
        """Test schedule overview access permissions"""
        url = reverse('appointments:schedule_overview')
        
        # Anonymous user should be redirected
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        
        # User with appointments permission should have access
        self.client.login(username='admin', password='testpass123')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Schedule Overview')
    
    def test_schedule_overview_display(self):
        """Test schedule overview displays dentist schedules correctly"""
        # Create a schedule for the dentist
        DentistSchedule.objects.create(
            dentist=self.dentist,
            weekday=0,  # Monday
            is_working=True,
            start_time=time(9, 0),
            end_time=time(17, 0),
            has_lunch_break=True,
            lunch_start=time(12, 0),
            lunch_end=time(13, 0)
        )
        
        self.client.login(username='admin', password='testpass123')
        url = reverse('appointments:schedule_overview')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dr. John Doe')
        self.assertContains(response, '09:00 AM')
        self.assertContains(response, '05:00 PM')
        self.assertContains(response, 'L: 12:00-13:00')  # Lunch break


class DentistScheduleFormTest(TestCase):
    def setUp(self):
        self.dentist_role = Role.objects.create(
            name='dentist',
            display_name='Dentist'
        )
        self.dentist = User.objects.create_user(
            username='dentist1',
            email='dentist@example.com',
            role=self.dentist_role,
            is_active_dentist=True
        )
    
    def test_form_valid_data(self):
        """Test form with valid data"""
        from appointments.forms import DentistScheduleForm
        
        form_data = {
            'is_working': True,
            'start_time': '09:00',
            'end_time': '17:00',
            'has_lunch_break': True,
            'lunch_start': '12:00',
            'lunch_end': '13:00',
        }
        
        form = DentistScheduleForm(data=form_data)
        self.assertTrue(form.is_valid())
    
    def test_form_invalid_working_hours(self):
        """Test form with invalid working hours"""
        from appointments.forms import DentistScheduleForm
        
        form_data = {
            'is_working': True,
            'start_time': '17:00',  # After end time
            'end_time': '09:00',
            'has_lunch_break': False,
            'lunch_start': '12:00',
            'lunch_end': '13:00',
        }
        
        form = DentistScheduleForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('End time must be after start time', str(form.errors))
    
    def test_form_invalid_lunch_hours(self):
        """Test form with invalid lunch break"""
        from appointments.forms import DentistScheduleForm
        
        # Lunch break outside working hours
        form_data = {
            'is_working': True,
            'start_time': '09:00',
            'end_time': '17:00',
            'has_lunch_break': True,
            'lunch_start': '08:00',  # Before work starts
            'lunch_end': '09:00',
        }
        
        form = DentistScheduleForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('Lunch break must be within working hours', str(form.errors))
    
    def test_form_not_working_clears_lunch(self):
        """Test that setting not working clears lunch break"""
        from appointments.forms import DentistScheduleForm
        
        form_data = {
            'is_working': False,
            'start_time': '09:00',
            'end_time': '17:00',
            'has_lunch_break': True,  # Should be cleared
            'lunch_start': '12:00',
            'lunch_end': '13:00',
        }
        
        form = DentistScheduleForm(data=form_data)
        self.assertTrue(form.is_valid())
        
        cleaned_data = form.clean()
        self.assertFalse(cleaned_data['has_lunch_break'])