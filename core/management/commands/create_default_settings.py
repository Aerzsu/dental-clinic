# core/management/commands/create_default_settings.py

from django.core.management.base import BaseCommand
from core.models import SystemSetting

class Command(BaseCommand):
    help = 'Create default system settings for the dental clinic'

    def handle(self, *args, **options):
        """Create default settings"""
        
        settings = [
            {
                'key': 'appointment_buffer_minutes',
                'value': '15',
                'description': 'Buffer time between appointments in minutes'
            },
            {
                'key': 'clinic_start_time',
                'value': '10:00',
                'description': 'Daily clinic opening time (HH:MM format)'
            },
            {
                'key': 'clinic_end_time',
                'value': '18:00',
                'description': 'Daily clinic closing time (HH:MM format)'
            },
            {
                'key': 'lunch_start_time',
                'value': '12:00',
                'description': 'Lunch break start time (HH:MM format)'
            },
            {
                'key': 'lunch_end_time',
                'value': '13:00',
                'description': 'Lunch break end time (HH:MM format)'
            },
            {
                'key': 'appointment_time_slot_minutes',
                'value': '30',
                'description': 'Duration of each appointment time slot'
            },
            {
                'key': 'minimum_booking_notice_hours',
                'value': '24',
                'description': 'Minimum hours in advance for booking appointments'
            },
            {
                'key': 'enable_same_day_booking',
                'value': 'false',
                'description': 'Allow appointments to be booked for the same day'
            },
            {
                'key': 'clinic_name',
                'value': 'KingJoy Dental Clinic',
                'description': 'Name of the dental clinic'
            },
            {
                'key': 'clinic_phone',
                'value': '+63 2 8123 4567',
                'description': 'Primary clinic contact number'
            },
            {
                'key': 'clinic_email',
                'value': 'info@kingjoydental.com',
                'description': 'Primary clinic email address'
            },
            {
                'key': 'max_appointments_per_day',
                'value': '15',
                'description': 'Maximum number of appointments per day'
            },
        ]

        created_count = 0
        updated_count = 0

        for setting_data in settings:
            setting, created = SystemSetting.objects.get_or_create(
                key=setting_data['key'],
                defaults={
                    'value': setting_data['value'],
                    'description': setting_data['description'],
                    'is_active': True
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created setting: {setting.key} = {setting.value}')
                )
            else:
                # Update description if it's empty
                if not setting.description:
                    setting.description = setting_data['description']
                    setting.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'Updated description for: {setting.key}')
                    )
                else:
                    self.stdout.write(f'Setting already exists: {setting.key}')

        self.stdout.write(
            self.style.SUCCESS(
                f'\nDefault settings setup completed:'
                f'\n- Created: {created_count} new settings'
                f'\n- Updated: {updated_count} existing settings'
                f'\n- Total: {len(settings)} settings processed'
            )
        )
        
        # Display all current settings
        self.stdout.write('\nCurrent System Settings:')
        self.stdout.write('-' * 50)
        for setting in SystemSetting.objects.filter(is_active=True).order_by('key'):
            self.stdout.write(f'{setting.key}: {setting.value}')