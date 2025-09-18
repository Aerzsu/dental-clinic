# appointments/management/commands/create_default_schedule_settings.py
"""
Management command to create default schedule settings for all dentists
Usage: python manage.py create_default_schedule_settings
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from users.models import User
from appointments.models import DentistScheduleSettings

class Command(BaseCommand):
    help = 'Create default schedule settings for all active dentists'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dentist-id',
            type=int,
            help='Create settings for specific dentist only',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreation of existing settings',
        )

    def handle(self, *args, **options):
        dentist_id = options.get('dentist_id')
        force = options.get('force')
        
        # Get dentists to process
        if dentist_id:
            dentists = User.objects.filter(id=dentist_id, is_active_dentist=True)
            if not dentists.exists():
                self.stdout.write(
                    self.style.ERROR(f'No active dentist found with ID {dentist_id}')
                )
                return
        else:
            dentists = User.objects.filter(is_active_dentist=True)
        
        created_count = 0
        updated_count = 0
        
        with transaction.atomic():
            for dentist in dentists:
                self.stdout.write(f'Processing Dr. {dentist.full_name}...')
                
                if force:
                    # Delete existing settings
                    deleted_count = DentistScheduleSettings.objects.filter(dentist=dentist).count()
                    DentistScheduleSettings.objects.filter(dentist=dentist).delete()
                    if deleted_count > 0:
                        self.stdout.write(f'  Deleted {deleted_count} existing settings')
                
                # Create default settings
                schedules = DentistScheduleSettings.create_default_schedule(dentist)
                
                new_schedules = [s for s in schedules if s._state.adding]
                existing_schedules = [s for s in schedules if not s._state.adding]
                
                created_count += len(new_schedules)
                updated_count += len(existing_schedules)
                
                if new_schedules:
                    self.stdout.write(f'  Created {len(new_schedules)} new schedule settings')
                if existing_schedules:
                    self.stdout.write(f'  Found {len(existing_schedules)} existing schedule settings')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully processed {dentists.count()} dentists: '
                f'{created_count} created, {updated_count} existing'
            )
        )