# appointments/management/commands/initialize_slot_system.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
import logging

from appointments.models import DailySlots, Appointment
from users.models import User


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Initialize AM/PM slot system and migrate existing appointment data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead',
            type=int,
            default=90,
            help='Number of days ahead to create default slots (default: 90)'
        )
        parser.add_argument(
            '--am-slots',
            type=int,
            default=6,
            help='Default number of AM slots per day (default: 6)'
        )
        parser.add_argument(
            '--pm-slots',
            type=int,
            default=8,
            help='Default number of PM slots per day (default: 8)'
        )
        parser.add_argument(
            '--migrate-existing',
            action='store_true',
            help='Migrate existing appointments to new AM/PM format'
        )
        parser.add_argument(
            '--clean-old-data',
            action='store_true',
            help='Clean up old scheduling system data'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )

    def handle(self, *args, **options):
        days_ahead = options['days_ahead']
        am_slots = options['am_slots']
        pm_slots = options['pm_slots']
        migrate_existing = options['migrate_existing']
        clean_old_data = options['clean_old_data']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )

        self.stdout.write(f'Initializing slot system for {days_ahead} days ahead...')
        self.stdout.write(f'Default slots: AM={am_slots}, PM={pm_slots} (same for all days including weekends)')

        try:
            with transaction.atomic():
                if migrate_existing:
                    self._migrate_existing_appointments(dry_run)
                
                self._create_default_slots(days_ahead, am_slots, pm_slots, dry_run)
                
                if clean_old_data:
                    self._clean_old_data(dry_run)
                
                if dry_run:
                    # Force rollback in dry run
                    raise Exception("Dry run - rolling back transaction")
                    
        except Exception as e:
            if dry_run and "Dry run" in str(e):
                self.stdout.write(
                    self.style.SUCCESS('Dry run completed successfully!')
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f'Error: {str(e)}')
                )
                raise

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS('Slot system initialization completed successfully!')
            )

    def _migrate_existing_appointments(self, dry_run):
        """Migrate existing appointments to AM/PM format"""
        self.stdout.write('Migrating existing appointments...')
        
        # Get appointments that need migration (have appointment_slot but no appointment_date)
        appointments_to_migrate = Appointment.objects.filter(
            appointment_slot__isnull=False,
            appointment_date__isnull=True
        ).select_related('appointment_slot')
        
        migrated_count = 0
        
        for appointment in appointments_to_migrate:
            if appointment.appointment_slot:
                # Determine period based on start time
                start_time = appointment.appointment_slot.start_time
                
                if start_time.hour < 13:  # Before 1 PM
                    period = 'AM'
                else:
                    period = 'PM'
                
                if not dry_run:
                    appointment.appointment_date = appointment.appointment_slot.date
                    appointment.period = period
                    
                    # If appointment has a dentist assigned via slot, move to assigned_dentist
                    if appointment.appointment_slot.dentist and not appointment.assigned_dentist:
                        appointment.assigned_dentist = appointment.appointment_slot.dentist
                    
                    appointment.save()
                
                migrated_count += 1
                
                self.stdout.write(
                    f'  {"Would migrate" if dry_run else "Migrated"}: '
                    f'{appointment.patient.full_name} - '
                    f'{appointment.appointment_slot.date} {period}'
                )
        
        self.stdout.write(f'{"Would migrate" if dry_run else "Migrated"} {migrated_count} appointments')

    def _create_default_slots(self, days_ahead, am_slots, pm_slots, dry_run):
        """Create default daily slots for future dates"""
        self.stdout.write(f'Creating default slots for next {days_ahead} days...')
        
        start_date = timezone.now().date()
        created_count = 0
        skipped_count = 0
        
        admin_user = User.objects.filter(is_superuser=True).first()
        
        for i in range(days_ahead):
            current_date = start_date + timedelta(days=i)
            
            # Skip Sundays
            if current_date.weekday() == 6:
                skipped_count += 1
                continue
            
            # Check if slots already exist
            if DailySlots.objects.filter(date=current_date).exists():
                skipped_count += 1
                continue
            
            if not dry_run:
                DailySlots.objects.create(
                    date=current_date,
                    am_slots=am_slots,
                    pm_slots=pm_slots,
                    created_by=admin_user,
                    notes='Auto-created by initialization command'
                )
            
            created_count += 1
            
            if created_count <= 10 or created_count % 10 == 0:  # Show first 10, then every 10th
                self.stdout.write(
                    f'  {"Would create" if dry_run else "Created"} slots for '
                    f'{current_date} (AM: {am_slots}, PM: {pm_slots})'
                )
        
        self.stdout.write(
            f'{"Would create" if dry_run else "Created"} {created_count} daily slot records'
        )
        self.stdout.write(f'Skipped {skipped_count} dates (Sundays or existing records)')

    def _clean_old_data(self, dry_run):
        """Clean up old scheduling data"""
        self.stdout.write('Cleaning up old scheduling data...')
        
        # Count records that would be deleted
        from appointments.models import AppointmentSlot, DentistScheduleSettings, TimeBlock
        
        old_slots_count = AppointmentSlot.objects.count()
        old_settings_count = DentistScheduleSettings.objects.count() if hasattr(AppointmentSlot, 'DentistScheduleSettings') else 0
        old_blocks_count = TimeBlock.objects.count() if hasattr(AppointmentSlot, 'TimeBlock') else 0
        
        self.stdout.write(f'Found {old_slots_count} old appointment slots to clean')
        if old_settings_count > 0:
            self.stdout.write(f'Found {old_settings_count} old dentist schedule settings to clean')
        if old_blocks_count > 0:
            self.stdout.write(f'Found {old_blocks_count} old time blocks to clean')
        
        if not dry_run:
            # Delete old data
            deleted_slots = AppointmentSlot.objects.all().delete()
            self.stdout.write(f'Deleted {deleted_slots[0]} appointment slots')
            
            # Only try to delete if the models exist
            try:
                deleted_settings = DentistScheduleSettings.objects.all().delete()
                self.stdout.write(f'Deleted {deleted_settings[0]} dentist schedule settings')
            except:
                pass
                
            try:
                deleted_blocks = TimeBlock.objects.all().delete()
                self.stdout.write(f'Deleted {deleted_blocks[0]} time blocks')
            except:
                pass
            
            self.stdout.write(
                self.style.SUCCESS('Old scheduling data cleaned up successfully')
            )
        else:
            self.stdout.write('Would clean up all old scheduling data')