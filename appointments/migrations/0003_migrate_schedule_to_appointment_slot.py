# appointments/migrations/0003_migrate_schedule_to_appointment_slot.py
from django.db import migrations

def migrate_schedule_to_appointment_slot(apps, schema_editor):
    """
    Migrate existing Schedule objects to AppointmentSlot objects
    """
    Schedule = apps.get_model('appointments', 'Schedule')
    AppointmentSlot = apps.get_model('appointments', 'AppointmentSlot')
    
    # Copy all Schedule records to AppointmentSlot
    for schedule in Schedule.objects.all():
        AppointmentSlot.objects.create(
            dentist=schedule.dentist,
            date=schedule.date,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            is_available=schedule.is_available,
            buffer_minutes=getattr(schedule, 'buffer_minutes', 15),  # Default if field doesn't exist
            notes=getattr(schedule, 'notes', ''),  # Default if field doesn't exist
            created_at=schedule.created_at,
        )

def reverse_migrate_appointment_slot_to_schedule(apps, schema_editor):
    """
    Reverse migration - copy AppointmentSlot back to Schedule
    """
    Schedule = apps.get_model('appointments', 'Schedule')
    AppointmentSlot = apps.get_model('appointments', 'AppointmentSlot')
    
    # Copy all AppointmentSlot records back to Schedule
    for slot in AppointmentSlot.objects.all():
        Schedule.objects.create(
            dentist=slot.dentist,
            date=slot.date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            is_available=slot.is_available,
            buffer_minutes=getattr(slot, 'buffer_minutes', 15),
            notes=getattr(slot, 'notes', ''),
            created_at=slot.created_at,
        )

class Migration(migrations.Migration):

    dependencies = [
        ('appointments', '0002_rename_schedule_and_add_schedule_settings'),
    ]

    operations = [
        migrations.RunPython(
            migrate_schedule_to_appointment_slot,
            reverse_migrate_appointment_slot_to_schedule,
        ),
    ]