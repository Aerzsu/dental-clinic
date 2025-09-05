# core/management/commands/setup_appointment_settings.py
from django.core.management.base import BaseCommand
from core.models import SystemSetting

class Command(BaseCommand):
    help = 'Setup default system settings for appointment booking'
    
    def handle(self, *args, **options):
        settings = [
            {
                'key': 'appointment_buffer_minutes',
                'value': '15',
                'description': 'Buffer time in minutes after each appointment for cleaning and preparation'
            },
            {
                'key': 'clinic_start_time',
                'value': '10:00',
                'description': 'Clinic opening time (24-hour format)'
            },
            {
                'key': 'clinic_end_time',
                'value': '18:00',
                'description': 'Clinic closing time (24-hour format)'
            },
            {
                'key': 'lunch_start_time',
                'value': '12:00',
                'description': 'Lunch break start time (24-hour format)'
            },
            {
                'key': 'lunch_end_time',
                'value': '13:00',
                'description': 'Lunch break end time (24-hour format)'
            },
            {
                'key': 'appointment_time_slot_minutes',
                'value': '30',
                'description': 'Duration of each time slot in minutes'
            },
            {
                'key': 'minimum_booking_notice_hours',
                'value': '24',
                'description': 'Minimum hours in advance that appointments can be booked'
            },
            {
                'key': 'enable_same_day_booking',
                'value': 'false',
                'description': 'Allow appointments to be booked for the same day'
            },
            {
                'key': 'max_concurrent_booking_attempts',
                'value': '3',
                'description': 'Maximum number of concurrent booking attempts before rate limiting'
            }
        ]
        
        created_count = 0
        updated_count = 0
        
        for setting_data in settings:
            setting, created = SystemSetting.objects.get_or_create(
                key=setting_data['key'],
                defaults={
                    'value': setting_data['value'],
                    'description': setting_data['description']
                }
            )
            
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f'Created setting: {setting.key} = {setting.value}')
                )
            else:
                # Update description if it's different
                if setting.description != setting_data['description']:
                    setting.description = setting_data['description']
                    setting.save()
                    updated_count += 1
                self.stdout.write(f'Setting exists: {setting.key} = {setting.value}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nCompleted: {created_count} settings created, {updated_count} updated'
            )
        )
