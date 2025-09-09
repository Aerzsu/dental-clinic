# Create this as appointments/management/commands/debug_schedules.py

from django.core.management.base import BaseCommand
from appointments.models import DentistSchedule
from users.models import User

class Command(BaseCommand):
    help = 'Debug dentist schedule data types'

    def handle(self, *args, **options):
        schedules = DentistSchedule.objects.all()
        
        self.stdout.write(f"Found {schedules.count()} DentistSchedule records")
        
        if schedules.count() == 0:
            self.stdout.write("No DentistSchedule records found!")
            self.stdout.write("Let's check what users exist:")
            
            users = User.objects.all()
            self.stdout.write(f"Total users: {users.count()}")
            
            for user in users:
                self.stdout.write(f"- {user.full_name} (ID: {user.id})")
                if hasattr(user, 'role'):
                    self.stdout.write(f"  Role: {user.role}")
                else:
                    self.stdout.write("  No role assigned")
            
            return
        
        for schedule in schedules:
            self.stdout.write(f"\nSchedule ID: {schedule.id}")
            self.stdout.write(f"Dentist: {schedule.dentist.full_name}")
            self.stdout.write(f"Weekday: {schedule.get_weekday_display()}")
            self.stdout.write(f"Is Working: {schedule.is_working}")
            
            # Check data types
            self.stdout.write(f"start_time type: {type(schedule.start_time)} value: {schedule.start_time}")
            self.stdout.write(f"end_time type: {type(schedule.end_time)} value: {schedule.end_time}")
            self.stdout.write(f"lunch_start type: {type(schedule.lunch_start)} value: {schedule.lunch_start}")
            self.stdout.write(f"lunch_end type: {type(schedule.lunch_end)} value: {schedule.lunch_end}")
            
            # Try to access the property
            try:
                display = schedule.working_hours_display
                self.stdout.write(f"Display: {display}")
            except Exception as e:
                self.stdout.write(f"ERROR: {e}")
            
            self.stdout.write("-" * 50)