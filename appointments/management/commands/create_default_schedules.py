# appointments/management/commands/create_default_schedules.py

from django.core.management.base import BaseCommand
from django.db import transaction
from users.models import User
from appointments.models import DentistSchedule
from datetime import time  # Add this import!


class Command(BaseCommand):
    help = 'Create default working schedules for all active dentists'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update existing schedules',
        )
        parser.add_argument(
            '--dentist',
            type=int,
            help='Create schedule for specific dentist ID only',
        )
    
    def handle(self, *args, **options):
        force_update = options.get('force', False)
        dentist_id = options.get('dentist')
        
        # Get dentists to process - FIXED: Use role-based filtering
        if dentist_id:
            dentists = User.objects.filter(
                id=dentist_id, 
                is_active=True,
                role__name__icontains='dentist'  # Changed from is_active_dentist
            )
            if not dentists.exists():
                self.stdout.write(
                    self.style.ERROR(f'No active dentist found with ID {dentist_id}')
                )
                return
        else:
            dentists = User.objects.filter(
                is_active=True,
                role__name__icontains='dentist'  # Changed from is_active_dentist
            )
        
        if not dentists.exists():
            self.stdout.write(
                self.style.ERROR('No active dentists found!')
            )
            return
        
        created_count = 0
        updated_count = 0
        
        with transaction.atomic():
            for dentist in dentists:
                self.stdout.write(f'Processing Dr. {dentist.full_name}...')
                
                for weekday in range(7):  # 0=Monday to 6=Sunday
                    schedule, created = DentistSchedule.objects.get_or_create(
                        dentist=dentist,
                        weekday=weekday,
                        defaults={
                            'is_working': weekday < 5,  # Monday to Friday only
                            'start_time': time(10, 0),      # FIXED: Use time object
                            'end_time': time(18, 0),        # FIXED: Use time object
                            'lunch_start': time(12, 0),     # FIXED: Use time object
                            'lunch_end': time(13, 0),       # FIXED: Use time object
                            'has_lunch_break': weekday < 5,  # Only working days
                        }
                    )
                    
                    if created:
                        created_count += 1
                        day_name = schedule.get_weekday_display()
                        if schedule.is_working:
                            # FIXED: Safe access to working_hours_display
                            try:
                                display = schedule.working_hours_display
                                self.stdout.write(f'  ✓ Created {day_name}: {display}')
                            except AttributeError:
                                self.stdout.write(f'  ✓ Created {day_name}: Working')
                        else:
                            self.stdout.write(f'  ✓ Created {day_name}: Not Working')
                    elif force_update:
                        # Update existing schedule to default values
                        schedule.is_working = weekday < 5
                        schedule.start_time = time(10, 0)      # FIXED: Use time object
                        schedule.end_time = time(18, 0)        # FIXED: Use time object
                        schedule.lunch_start = time(12, 0)     # FIXED: Use time object
                        schedule.lunch_end = time(13, 0)       # FIXED: Use time object
                        schedule.has_lunch_break = weekday < 5
                        schedule.save()
                        updated_count += 1
                        self.stdout.write(f'  ↻ Updated {schedule.get_weekday_display()}')
                    else:
                        self.stdout.write(f'  - {schedule.get_weekday_display()}: Already exists')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully processed {dentists.count()} dentists. '
                f'Created {created_count} schedules, updated {updated_count} schedules.'
            )
        )
        
        if not force_update and created_count == 0:
            self.stdout.write(
                self.style.WARNING(
                    'No new schedules were created. Use --force to update existing schedules.'
                )
            )