# appointments/migrations/0006_cleanup_old_schedule_model.py
from django.db import migrations

class Migration(migrations.Migration):
    """
    Clean up old Schedule model after successful migration
    This migration should be run after confirming everything works correctly
    """

    dependencies = [
        ('appointments', '0005_migrate_dentist_schedule_settings'),
    ]

    operations = [
        # Remove the old schedule field from appointments
        migrations.RemoveField(
            model_name='appointment',
            name='schedule',
        ),
        
        # Delete the old Schedule model
        migrations.DeleteModel(
            name='Schedule',
        ),
        
        # Also delete the old DentistSchedule model if it exists
        # migrations.DeleteModel(
        #     name='DentistSchedule',
        # ),
    ]