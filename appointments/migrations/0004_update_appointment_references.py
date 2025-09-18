# appointments/migrations/0004_update_appointment_references.py
from django.db import migrations, models
import django.db.models.deletion


def update_appointment_schedule_references(apps, schema_editor):
    """
    Update Appointment model to reference AppointmentSlot instead of Schedule
    """
    Appointment = apps.get_model('appointments', 'Appointment')
    AppointmentSlot = apps.get_model('appointments', 'AppointmentSlot')
    Schedule = apps.get_model('appointments', 'Schedule')
   
    # For each appointment, find the corresponding appointment slot
    for appointment in Appointment.objects.all():
        try:
            # Find matching appointment slot
            slot = AppointmentSlot.objects.get(
                dentist=appointment.schedule.dentist,
                date=appointment.schedule.date,
                start_time=appointment.schedule.start_time,
                end_time=appointment.schedule.end_time,
            )
            # Update appointment to reference the slot instead
            appointment.appointment_slot_id = slot.id
            appointment.save()
        except AppointmentSlot.DoesNotExist:
            # If no matching slot found, create one
            slot = AppointmentSlot.objects.create(
                dentist=appointment.schedule.dentist,
                date=appointment.schedule.date,
                start_time=appointment.schedule.start_time,
                end_time=appointment.schedule.end_time,
                is_available=appointment.schedule.is_available,
                buffer_minutes=getattr(appointment.schedule, 'buffer_minutes', 15),
                notes=getattr(appointment.schedule, 'notes', ''),
                created_at=appointment.schedule.created_at,
            )
            appointment.appointment_slot_id = slot.id
            appointment.save()


def check_and_remove_old_constraint(apps, schema_editor):
    """
    Safely remove the old constraint if it exists
    """
    from django.db import connection
    
    # Check if the constraint exists before trying to remove it
    with connection.cursor() as cursor:
        # For PostgreSQL
        if connection.vendor == 'postgresql':
            cursor.execute("""
                SELECT constraint_name 
                FROM information_schema.table_constraints 
                WHERE table_name = 'appointments_appointment' 
                AND constraint_name = 'unique_active_appointment_per_schedule'
            """)
        # For SQLite
        elif connection.vendor == 'sqlite':
            cursor.execute("""
                SELECT name 
                FROM sqlite_master 
                WHERE type = 'index' 
                AND tbl_name = 'appointments_appointment' 
                AND name LIKE '%unique_active_appointment_per_schedule%'
            """)
        # For MySQL
        elif connection.vendor == 'mysql':
            cursor.execute("""
                SELECT CONSTRAINT_NAME 
                FROM information_schema.TABLE_CONSTRAINTS 
                WHERE TABLE_NAME = 'appointments_appointment' 
                AND CONSTRAINT_NAME = 'unique_active_appointment_per_schedule'
            """)
        
        result = cursor.fetchone()
        return result is not None


class Migration(migrations.Migration):
    dependencies = [
        ('appointments', '0003_migrate_schedule_to_appointment_slot'),
    ]

    operations = [
        # Add new appointment_slot field to Appointment model
        migrations.AddField(
            model_name='appointment',
            name='appointment_slot',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='appointments',
                to='appointments.AppointmentSlot'
            ),
        ),
       
        # Migrate data
        migrations.RunPython(
            update_appointment_schedule_references,
            migrations.RunPython.noop,
        ),
       
        # Make appointment_slot required after data migration
        migrations.AlterField(
            model_name='appointment',
            name='appointment_slot',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='appointments',
                to='appointments.AppointmentSlot'
            ),
        ),
       
        # Add the new constraint (old constraint removal will be handled separately if needed)
        migrations.AddConstraint(
            model_name='appointment',
            constraint=models.UniqueConstraint(
                fields=['appointment_slot'],
                condition=models.Q(status__in=['pending', 'approved', 'completed']),
                name='unique_active_appointment_per_slot'
            ),
        ),
    ]