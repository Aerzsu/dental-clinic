# appointments/migrations/0002_rename_schedule_and_add_schedule_settings.py
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
from datetime import time

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('appointments', '0001_initial'),
    ]

    operations = [
        # Step 1: Create new models
        migrations.CreateModel(
            name='AppointmentSlot',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('is_available', models.BooleanField(default=True)),
                ('buffer_minutes', models.PositiveIntegerField(default=15, help_text='Buffer time after appointment for cleaning/prep')),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('dentist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='appointment_slots', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['date', 'start_time'],
                'indexes': [
                    models.Index(fields=['dentist', 'date'], name='appt_slot_dentist_date_idx'),
                    models.Index(fields=['date', 'start_time'], name='appt_slot_date_time_idx'),
                ],
            },
        ),
        
        migrations.CreateModel(
            name='DentistScheduleSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weekday', models.IntegerField(choices=[(0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')])),
                ('is_working', models.BooleanField(default=True)),
                ('start_time', models.TimeField(default=time(10, 0))),
                ('end_time', models.TimeField(default=time(18, 0))),
                ('has_lunch_break', models.BooleanField(default=True)),
                ('lunch_start', models.TimeField(default=time(12, 0))),
                ('lunch_end', models.TimeField(default=time(13, 0))),
                ('default_buffer_minutes', models.PositiveIntegerField(default=15, help_text='Default buffer time between appointments')),
                ('slot_duration_minutes', models.PositiveIntegerField(default=30, help_text='Duration of each appointment slot')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('dentist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_settings', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['dentist', 'weekday'],
                'indexes': [
                    models.Index(fields=['dentist', 'weekday'], name='dentist_sched_weekday_idx'),
                ],
            },
        ),
        
        migrations.CreateModel(
            name='TimeBlock',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('start_time', models.TimeField(blank=True, help_text='Leave empty to block entire day', null=True)),
                ('end_time', models.TimeField(blank=True, help_text='Leave empty to block entire day', null=True)),
                ('block_type', models.CharField(choices=[('vacation', 'Vacation'), ('sick_leave', 'Sick Leave'), ('meeting', 'Meeting'), ('training', 'Training'), ('maintenance', 'Equipment Maintenance'), ('personal', 'Personal Time'), ('other', 'Other')], default='other', max_length=20)),
                ('reason', models.CharField(max_length=255)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='created_time_blocks', to=settings.AUTH_USER_MODEL)),
                ('dentist', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='time_blocks', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['date', 'start_time'],
                'indexes': [
                    models.Index(fields=['dentist', 'date'], name='time_block_dentist_date_idx'),
                    models.Index(fields=['date', 'start_time'], name='time_block_date_time_idx'),
                ],
            },
        ),

        # Step 2: Add constraints
        migrations.AddConstraint(
            model_name='appointmentslot',
            constraint=models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')), 
                name='appointmentslot_end_after_start'
            ),
        ),
        migrations.AddConstraint(
            model_name='appointmentslot',
            constraint=models.CheckConstraint(
                check=models.Q(buffer_minutes__gte=0), 
                name='appointmentslot_non_negative_buffer'
            ),
        ),
        migrations.AddConstraint(
            model_name='appointmentslot',
            constraint=models.UniqueConstraint(
                fields=['dentist', 'date', 'start_time', 'end_time'], 
                name='unique_appointment_slot'
            ),
        ),
        
        migrations.AddConstraint(
            model_name='dentistschedulesettings',
            constraint=models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')), 
                name='dentist_settings_end_after_start'
            ),
        ),
        migrations.AddConstraint(
            model_name='dentistschedulesettings',
            constraint=models.CheckConstraint(
                check=models.Q(lunch_end__gt=models.F('lunch_start')), 
                name='dentist_settings_lunch_end_after_start'
            ),
        ),
        migrations.AddConstraint(
            model_name='dentistschedulesettings',
            constraint=models.CheckConstraint(
                check=models.Q(default_buffer_minutes__gte=0), 
                name='dentist_settings_non_negative_buffer'
            ),
        ),
        migrations.AddConstraint(
            model_name='dentistschedulesettings',
            constraint=models.CheckConstraint(
                check=models.Q(slot_duration_minutes__gt=0), 
                name='dentist_settings_positive_slot_duration'
            ),
        ),
        migrations.AddConstraint(
            model_name='dentistschedulesettings',
            constraint=models.UniqueConstraint(
                fields=['dentist', 'weekday'], 
                name='unique_dentist_weekday_setting'
            ),
        ),
        
        migrations.AddConstraint(
            model_name='timeblock',
            constraint=models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')) | 
                      (models.Q(start_time__isnull=True) & models.Q(end_time__isnull=True)),
                name='timeblock_valid_times'
            ),
        ),
    ]