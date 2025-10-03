# core/management/commands/cleanup_old_logs.py
"""
Management command to clean up old audit logs
Usage: python manage.py cleanup_old_logs --days=365
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import AuditLog


class Command(BaseCommand):
    help = 'Clean up audit logs older than specified days'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='Delete logs older than this many days (default: 365)'
        )
        
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting'
        )
    
    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        
        # Calculate cutoff date
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Get logs to delete
        old_logs = AuditLog.objects.filter(timestamp__lt=cutoff_date)
        count = old_logs.count()
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'DRY RUN: Would delete {count} audit logs older than {days} days '
                    f'(before {cutoff_date.strftime("%Y-%m-%d")})'
                )
            )
            
            # Show breakdown by action
            self.stdout.write('\nBreakdown by action:')
            for action, label in AuditLog.ACTION_CHOICES:
                action_count = old_logs.filter(action=action).count()
                if action_count > 0:
                    self.stdout.write(f'  {label}: {action_count}')
        else:
            if count == 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'No audit logs older than {days} days found.'
                    )
                )
            else:
                # Delete old logs
                old_logs.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully deleted {count} audit logs older than {days} days '
                        f'(before {cutoff_date.strftime("%Y-%m-%d")})'
                    )
                )