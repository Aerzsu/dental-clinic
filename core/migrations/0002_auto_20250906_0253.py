# core/migrations/XXXX_add_default_system_settings.py
# Run: python manage.py makemigrations --empty core
# Then replace the generated migration content with this

from django.db import migrations


def create_default_settings(apps, schema_editor):
    SystemSetting = apps.get_model('core', 'SystemSetting')
    
    # Define settings without 'setting_type' field
    default_settings = [
        {
            'key': 'clinic_name',
            'value': 'My Dental Clinic',
            'description': 'Name of the dental clinic',
        },
        {
            'key': 'clinic_phone',
            'value': '+1234567890',
            'description': 'Clinic contact phone number',
        },
        {
            'key': 'clinic_email',
            'value': 'info@dentalclinic.com',
            'description': 'Clinic contact email',
        },
        {
            'key': 'appointment_duration',
            'value': '60',
            'description': 'Default appointment duration in minutes',
        },
        {
            'key': 'working_hours_start',
            'value': '10:00',
            'description': 'Clinic opening time',
        },
        {
            'key': 'working_hours_end',
            'value': '18:00',
            'description': 'Clinic closing time',
        },
    ]
    
    for setting_data in default_settings:
        SystemSetting.objects.get_or_create(
            key=setting_data['key'],
            defaults={
                'value': setting_data['value'],
                'description': setting_data['description'],
            }
        )


def remove_default_settings(apps, schema_editor):
    SystemSetting = apps.get_model('core', 'SystemSetting')
    
    setting_keys = [
        'clinic_start_time',
        'clinic_end_time',
        'lunch_start_time',
        'lunch_end_time',
        'appointment_buffer_minutes',
        'appointment_time_slot_minutes',
        'minimum_booking_notice_hours',
        'enable_same_day_booking',
        'max_concurrent_booking_attempts'
    ]
    
    SystemSetting.objects.filter(key__in=setting_keys).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),  # Replace with your latest core migration
    ]

    operations = [
        migrations.RunPython(create_default_settings, remove_default_settings),
    ]