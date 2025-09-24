# appointments/management/commands/cleanup_appointment_data.py
from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Clean up appointment data before migration'
    
    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            # Check appointments with missing new fields
            cursor.execute("""
                SELECT COUNT(*) FROM appointments_appointment 
                WHERE appointment_date IS NULL OR period IS NULL
            """)
            missing_count = cursor.fetchone()[0]
            
            if missing_count > 0:
                self.stdout.write(
                    self.style.WARNING(f'Found {missing_count} appointments missing appointment_date or period')
                )
                
                # Delete appointments without proper AM/PM data
                cursor.execute("""
                    DELETE FROM appointments_appointment 
                    WHERE appointment_date IS NULL OR period IS NULL
                """)
                self.stdout.write(
                    self.style.SUCCESS(f'Deleted {missing_count} incomplete appointments')
                )
            
            # Clean up foreign key references
            cursor.execute("UPDATE appointments_appointment SET appointment_slot_id = NULL")
            cursor.execute("UPDATE appointments_appointment SET dentist_id = NULL")
            
            self.stdout.write(self.style.SUCCESS('Cleaned up appointment data successfully'))