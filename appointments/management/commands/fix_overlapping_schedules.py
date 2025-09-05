# appointments/management/commands/fix_overlapping_schedules.py
from django.core.management.base import BaseCommand
from django.db import transaction
from appointments.models import Schedule, Appointment
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix overlapping schedules by consolidating or removing duplicates'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='Show what would be changed without making actual changes',
        )
        parser.add_argument(
            '--auto-fix',
            action='store_true',
            dest='auto_fix',
            help='Automatically fix overlaps by merging or removing duplicate schedules',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        auto_fix = options['auto_fix']
        
        self.stdout.write('Scanning for overlapping schedules...')
        
        # Get all schedules grouped by dentist and date
        schedules = Schedule.objects.select_related('dentist').order_by('dentist', 'date', 'start_time')
        
        overlapping_groups = []
        processed_schedule_ids = set()
        
        for schedule in schedules:
            if schedule.id in processed_schedule_ids:
                continue
                
            # Find all schedules for same dentist on same date that might overlap
            same_day_schedules = Schedule.objects.filter(
                dentist=schedule.dentist,
                date=schedule.date
            ).exclude(id__in=processed_schedule_ids).order_by('start_time')
            
            if len(same_day_schedules) <= 1:
                processed_schedule_ids.add(schedule.id)
                continue
                
            # Check for overlaps within this group
            overlapping_in_group = []
            
            for i, sched1 in enumerate(same_day_schedules):
                for sched2 in same_day_schedules[i+1:]:
                    if self._schedules_overlap(sched1, sched2):
                        if sched1 not in overlapping_in_group:
                            overlapping_in_group.append(sched1)
                        if sched2 not in overlapping_in_group:
                            overlapping_in_group.append(sched2)
            
            if overlapping_in_group:
                overlapping_groups.append(overlapping_in_group)
                processed_schedule_ids.update([s.id for s in overlapping_in_group])
            else:
                processed_schedule_ids.update([s.id for s in same_day_schedules])
        
        if not overlapping_groups:
            self.stdout.write(self.style.SUCCESS('No overlapping schedules found!'))
            return
        
        self.stdout.write(f'Found {len(overlapping_groups)} groups with overlapping schedules:')
        
        for i, group in enumerate(overlapping_groups):
            self.stdout.write(f'\nGroup {i+1}: {group[0].dentist.full_name} on {group[0].date}')
            
            for schedule in group:
                appointments = Appointment.objects.filter(
                    schedule=schedule, 
                    status__in=['pending', 'approved', 'completed']
                ).count()
                
                self.stdout.write(
                    f'  - {schedule.start_time} to {schedule.end_time} '
                    f'(ID: {schedule.id}, {appointments} appointments)'
                )
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY RUN] No changes made. Use --auto-fix to apply changes.'))
            return
        
        if not auto_fix:
            self.stdout.write(
                self.style.WARNING(
                    '\nUse --auto-fix to automatically resolve overlaps, '
                    'or manually review and fix these schedules.'
                )
            )
            return
        
        # Auto-fix overlaps
        self.stdout.write('\nAttempting to automatically fix overlaps...')
        
        fixed_count = 0
        error_count = 0
        
        for group in overlapping_groups:
            try:
                with transaction.atomic():
                    fixed = self._fix_overlapping_group(group)
                    if fixed:
                        fixed_count += 1
                    else:
                        error_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error fixing group: {str(e)}')
                )
                error_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nCompleted: {fixed_count} groups fixed, {error_count} errors'
            )
        )
    
    def _schedules_overlap(self, schedule1, schedule2):
        """Check if two schedules overlap (including buffer time)"""
        # Calculate effective end times including buffer
        sched1_end = self._get_effective_end_time(schedule1)
        sched2_end = self._get_effective_end_time(schedule2)
        
        # Two schedules overlap if:
        # schedule1 starts before schedule2 ends AND schedule1 ends after schedule2 starts
        return (schedule1.start_time < sched2_end and 
                sched1_end > schedule2.start_time)
    
    def _get_effective_end_time(self, schedule):
        """Get end time including buffer"""
        buffer_minutes = getattr(schedule, 'buffer_minutes', 15)
        end_datetime = datetime.combine(schedule.date, schedule.end_time)
        buffered_end = end_datetime + timedelta(minutes=buffer_minutes)
        return buffered_end.time()
    
    def _fix_overlapping_group(self, schedules):
        """
        Fix a group of overlapping schedules by consolidating appointments
        into the earliest suitable schedule and removing duplicates
        """
        # Sort schedules by start time
        schedules = sorted(schedules, key=lambda s: s.start_time)
        
        # Find the schedule with appointments (if any)
        schedule_appointments = {}
        for schedule in schedules:
            appointments = list(Appointment.objects.filter(
                schedule=schedule,
                status__in=['pending', 'approved', 'completed']
            ))
            schedule_appointments[schedule.id] = appointments
        
        # Strategy: Keep the earliest schedule that has appointments,
        # or the earliest schedule if none have appointments
        primary_schedule = None
        
        # First, try to find a schedule with appointments
        for schedule in schedules:
            if schedule_appointments[schedule.id]:
                primary_schedule = schedule
                break
        
        # If no schedule has appointments, use the first one
        if not primary_schedule:
            primary_schedule = schedules[0]
        
        self.stdout.write(
            f'  Consolidating into schedule {primary_schedule.id} '
            f'({primary_schedule.start_time} - {primary_schedule.end_time})'
        )
        
        # Move all appointments to the primary schedule
        moved_count = 0
        for schedule in schedules:
            if schedule == primary_schedule:
                continue
                
            appointments = schedule_appointments[schedule.id]
            for appointment in appointments:
                appointment.schedule = primary_schedule
                appointment.save()
                moved_count += 1
            
            # Delete the now-empty schedule
            schedule.delete()
            self.stdout.write(f'    Removed duplicate schedule {schedule.id}')
        
        if moved_count > 0:
            self.stdout.write(f'    Moved {moved_count} appointments')
        
        return True