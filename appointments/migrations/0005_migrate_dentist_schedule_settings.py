# appointments/migrations/0005_migrate_dentist_schedule_settings.py
from django.db import migrations
from datetime import time


def migrate_dentist_schedules(apps, schema_editor):
    """
    Migrate existing DentistSchedule objects to DentistScheduleSettings
    """
    DentistScheduleSettings = apps.get_model('appointments', 'DentistScheduleSettings')
    User = apps.get_model('users', 'User')
    
    # Try to get the old DentistSchedule model, but handle gracefully if it doesn't exist
    try:
        DentistSchedule = apps.get_model('appointments', 'DentistSchedule')
        has_old_model = True
    except LookupError:
        # DentistSchedule model doesn't exist, so we'll just create default schedules
        has_old_model = False
        DentistSchedule = None
    
    # Get all dentists
    try:
        dentists = User.objects.filter(is_active_dentist=True)
    except Exception:
        # If is_active_dentist field doesn't exist, try other approaches
        try:
            dentists = User.objects.filter(user_type='dentist')
        except Exception:
            # If no specific field, get users who might be dentists
            # You can adjust this query based on your User model structure
            dentists = User.objects.filter(is_staff=True)
    
    for dentist in dentists:
        # Check if they already have new schedule settings
        existing_settings = DentistScheduleSettings.objects.filter(dentist=dentist)
        
        if existing_settings.exists():
            # Skip if already has new settings
            continue
            
        if has_old_model:
            # Check if they have old schedule settings
            old_schedules = DentistSchedule.objects.filter(dentist=dentist)
            
            if old_schedules.exists():
                # Migrate existing schedules
                for old_schedule in old_schedules:
                    DentistScheduleSettings.objects.get_or_create(
                        dentist=dentist,
                        weekday=old_schedule.weekday,
                        defaults={
                            'is_working': old_schedule.is_working,
                            'start_time': old_schedule.start_time,
                            'end_time': old_schedule.end_time,
                            'has_lunch_break': getattr(old_schedule, 'has_lunch_break', True),
                            'lunch_start': getattr(old_schedule, 'lunch_start', time(12, 0)),
                            'lunch_end': getattr(old_schedule, 'lunch_end', time(13, 0)),
                            'default_buffer_minutes': 15,  # Default value
                            'slot_duration_minutes': 30,   # Default value
                        }
                    )
                continue  # Skip creating default schedule
        
        # Create default schedule for dentist (either no old model or no old schedules)
        for weekday in range(7):
            is_working = weekday < 5  # Mon-Fri default
            
            # Saturday gets shorter hours
            if weekday == 5:  # Saturday
                start_time = time(10, 0)
                end_time = time(14, 0)  # 2:00 PM
                has_lunch_break = False
            else:
                start_time = time(10, 0)
                end_time = time(18, 0)
                has_lunch_break = True
                
            DentistScheduleSettings.objects.get_or_create(
                dentist=dentist,
                weekday=weekday,
                defaults={
                    'is_working': is_working,
                    'start_time': start_time,
                    'end_time': end_time,
                    'has_lunch_break': has_lunch_break,
                    'lunch_start': time(12, 0),
                    'lunch_end': time(13, 0),
                    'default_buffer_minutes': 15,
                    'slot_duration_minutes': 30,
                }
            )


class Migration(migrations.Migration):
    dependencies = [
        ('appointments', '0004_update_appointment_references'),
    ]
    
    operations = [
        migrations.RunPython(
            migrate_dentist_schedules,
            migrations.RunPython.noop,
        ),
    ]