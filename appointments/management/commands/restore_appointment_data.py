# appointments/management/commands/restore_appointment_data.py
import json
from django.core.management.base import BaseCommand
from appointments.models import Appointment
from patients.models import Patient
from services.models import Service
from users.models import User
from django.utils import timezone
from datetime import datetime

class Command(BaseCommand):
    help = 'Restore appointment data after migration reset'
    
    def add_arguments(self, parser):
        parser.add_argument('backup_file', type=str, help='Path to appointment backup JSON file')
    
    def handle(self, *args, **options):
        backup_file = options['backup_file']
        
        try:
            with open(backup_file, 'r') as f:
                data = json.load(f)
            
            restored_count = 0
            skipped_count = 0
            
            for item in data:
                if item['model'] == 'appointments.appointment':
                    fields = item['fields']
                    
                    # Skip if missing required new fields
                    if not fields.get('appointment_date') or not fields.get('period'):
                        self.stdout.write(
                            self.style.WARNING(f'Skipping appointment ID {item["pk"]} - missing date/period')
                        )
                        skipped_count += 1
                        continue
                    
                    try:
                        # Get related objects
                        patient = Patient.objects.get(id=fields['patient'])
                        service = Service.objects.get(id=fields['service'])
                        
                        assigned_dentist = None
                        if fields.get('assigned_dentist'):
                            try:
                                assigned_dentist = User.objects.get(id=fields['assigned_dentist'])
                            except User.DoesNotExist:
                                pass
                        
                        approved_by = None
                        if fields.get('approved_by'):
                            try:
                                approved_by = User.objects.get(id=fields['approved_by'])
                            except User.DoesNotExist:
                                pass
                        
                        # Parse dates
                        appointment_date = datetime.strptime(fields['appointment_date'], '%Y-%m-%d').date()
                        
                        requested_at = timezone.now()
                        if fields.get('requested_at'):
                            requested_at = datetime.fromisoformat(fields['requested_at'].replace('Z', '+00:00'))
                        
                        approved_at = None
                        if fields.get('approved_at'):
                            approved_at = datetime.fromisoformat(fields['approved_at'].replace('Z', '+00:00'))
                        
                        # Create appointment
                        appointment = Appointment.objects.create(
                            patient=patient,
                            service=service,
                            appointment_date=appointment_date,
                            period=fields['period'],
                            assigned_dentist=assigned_dentist,
                            status=fields.get('status', 'pending'),
                            patient_type=fields.get('patient_type', 'returning'),
                            reason=fields.get('reason', ''),
                            requested_at=requested_at,
                            approved_at=approved_at,
                            approved_by=approved_by,
                            staff_notes=fields.get('staff_notes', '')
                        )
                        
                        restored_count += 1
                        
                    except (Patient.DoesNotExist, Service.DoesNotExist) as e:
                        self.stdout.write(
                            self.style.ERROR(f'Skipping appointment ID {item["pk"]} - missing related object: {e}')
                        )
                        skipped_count += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'Error restoring appointment ID {item["pk"]}: {e}')
                        )
                        skipped_count += 1
            
            self.stdout.write(
                self.style.SUCCESS(f'Restored {restored_count} appointments, skipped {skipped_count}')
            )
            
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'Backup file not found: {backup_file}'))
        except json.JSONDecodeError:
            self.stdout.write(self.style.ERROR('Invalid JSON in backup file'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))