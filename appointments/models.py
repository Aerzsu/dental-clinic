# appointments/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, time, timedelta

class AppointmentSlot(models.Model):
    """
    Renamed from Schedule - Represents a specific time slot for appointments
    """
    dentist = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='appointment_slots')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    buffer_minutes = models.PositiveIntegerField(default=15, help_text="Buffer time after appointment for cleaning/prep")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['date', 'start_time']
        unique_together = ['dentist', 'date', 'start_time', 'end_time']
        indexes = [
            models.Index(fields=['dentist', 'date'], name='appt_slot_dentist_date_idx'),
            models.Index(fields=['date', 'start_time'], name='appt_slot_date_time_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')), 
                name='appointmentslot_end_after_start'
            ),
            models.CheckConstraint(
                check=models.Q(buffer_minutes__gte=0), 
                name='appointmentslot_non_negative_buffer'
            ),
        ]
    
    def __str__(self):
        return f"{self.dentist.full_name} - {self.date} {self.start_time}-{self.end_time}"
    
    @property
    def effective_end_time(self):
        """End time including buffer"""
        end_datetime = datetime.combine(self.date, self.end_time)
        buffered_end = end_datetime + timedelta(minutes=self.buffer_minutes)
        return buffered_end.time()
    
    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError('End time must be after start time.')
        
        # Check for overlapping slots for the same dentist on the same date
        overlapping = AppointmentSlot.objects.filter(
            dentist=self.dentist,
            date=self.date
        ).exclude(pk=self.pk)
        
        for slot in overlapping:
            if self._slots_overlap(slot):
                raise ValidationError(
                    f'This time slot overlaps with existing slot: '
                    f'{slot.start_time}-{slot.end_time}'
                )
    
    def _slots_overlap(self, other_slot):
        """Check if this slot overlaps with another slot (including buffer)"""
        self_effective_end = self.effective_end_time
        other_effective_end = other_slot.effective_end_time
        
        return (self.start_time < other_effective_end and 
                self_effective_end > other_slot.start_time)


class DentistScheduleSettings(models.Model):
    """
    Individual working hours and settings for each dentist
    """
    WEEKDAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'), 
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    dentist = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='schedule_settings')
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES)
    is_working = models.BooleanField(default=True)
    start_time = models.TimeField(default=time(10, 0))  # 10:00 AM
    end_time = models.TimeField(default=time(18, 0))    # 6:00 PM
    
    # Lunch break settings
    has_lunch_break = models.BooleanField(default=True)
    lunch_start = models.TimeField(default=time(12, 0))  # 12:00 PM
    lunch_end = models.TimeField(default=time(13, 0))    # 1:00 PM
    
    # Buffer and slot settings
    default_buffer_minutes = models.PositiveIntegerField(default=15, help_text="Default buffer time between appointments")
    slot_duration_minutes = models.PositiveIntegerField(default=30, help_text="Duration of each appointment slot")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['dentist', 'weekday']
        ordering = ['dentist', 'weekday']
        indexes = [
            models.Index(fields=['dentist', 'weekday'], name='dentist_sched_weekday_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')), 
                name='dentist_settings_end_after_start'
            ),
            models.CheckConstraint(
                check=models.Q(lunch_end__gt=models.F('lunch_start')), 
                name='dentist_settings_lunch_end_after_start'
            ),
            models.CheckConstraint(
                check=models.Q(default_buffer_minutes__gte=0), 
                name='dentist_settings_non_negative_buffer'
            ),
            models.CheckConstraint(
                check=models.Q(slot_duration_minutes__gt=0), 
                name='dentist_settings_positive_slot_duration'
            ),
        ]
    
    def __str__(self):
        weekday_name = self.get_weekday_display()
        if self.is_working:
            return f"{self.dentist.full_name} - {weekday_name} ({self.start_time}-{self.end_time})"
        else:
            return f"{self.dentist.full_name} - {weekday_name} (Not Working)"
    
    def clean(self):
        if self.is_working:
            if self.end_time <= self.start_time:
                raise ValidationError('End time must be after start time.')
            
            if self.has_lunch_break:
                if self.lunch_end <= self.lunch_start:
                    raise ValidationError('Lunch end time must be after lunch start time.')
                
                # Check lunch break is within working hours
                if self.lunch_start < self.start_time or self.lunch_end > self.end_time:
                    raise ValidationError('Lunch break must be within working hours.')
                
                # Check lunch break duration (max 2 hours)
                lunch_duration = datetime.combine(datetime.today(), self.lunch_end) - \
                               datetime.combine(datetime.today(), self.lunch_start)
                if lunch_duration.total_seconds() > 7200:  # 2 hours in seconds
                    raise ValidationError('Lunch break cannot exceed 2 hours.')
    
    @property
    def working_hours_display(self):
        """Display working hours in readable format"""
        if not self.is_working:
            return "Not Working"
        
        hours = f"{self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"
        if self.has_lunch_break:
            lunch = f"{self.lunch_start.strftime('%I:%M %p')}-{self.lunch_end.strftime('%I:%M %p')}"
            hours += f" (Lunch: {lunch})"
        return hours
    
    @classmethod
    def create_default_schedule(cls, dentist):
        """Create default Mon-Fri working schedule for a dentist"""
        schedules = []
        for weekday in range(7):  # 0=Monday, 6=Sunday
            is_working = weekday < 5  # Monday to Friday only (Saturday optional)
            
            # Saturday gets shorter hours
            if weekday == 5:  # Saturday
                start_time = time(10, 0)
                end_time = time(14, 0)  # 2:00 PM
                has_lunch_break = False
            else:
                start_time = time(10, 0)
                end_time = time(18, 0)
                has_lunch_break = True
            
            schedule = cls.objects.get_or_create(
                dentist=dentist,
                weekday=weekday,
                defaults={
                    'is_working': is_working,
                    'start_time': start_time,
                    'end_time': end_time,
                    'has_lunch_break': has_lunch_break,
                    'lunch_start': time(12, 0),
                    'lunch_end': time(13, 0),
                    'default_buffer_minutes': 15,
                    'slot_duration_minutes': 30,
                }
            )[0]
            schedules.append(schedule)
        return schedules
    
    @classmethod
    def get_dentist_settings_for_date(cls, dentist, date):
        """Get schedule settings for a dentist on a specific date"""
        weekday = date.weekday()
        try:
            return cls.objects.get(dentist=dentist, weekday=weekday, is_working=True)
        except cls.DoesNotExist:
            return None
    
    def is_time_within_working_hours(self, time_obj):
        """Check if a time is within working hours (excluding lunch)"""
        if not self.is_working:
            return False
        
        if time_obj < self.start_time or time_obj >= self.end_time:
            return False
        
        # Check if time falls during lunch break
        if self.has_lunch_break:
            if self.lunch_start <= time_obj < self.lunch_end:
                return False
        
        return True


class TimeBlock(models.Model):
    """
    Blocks specific time ranges for dentists (vacations, meetings, etc.)
    """
    BLOCK_TYPE_CHOICES = [
        ('vacation', 'Vacation'),
        ('sick_leave', 'Sick Leave'),
        ('meeting', 'Meeting'),
        ('training', 'Training'),
        ('maintenance', 'Equipment Maintenance'),
        ('personal', 'Personal Time'),
        ('other', 'Other'),
    ]
    
    dentist = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='time_blocks')
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True, help_text="Leave empty to block entire day")
    end_time = models.TimeField(null=True, blank=True, help_text="Leave empty to block entire day")
    block_type = models.CharField(max_length=20, choices=BLOCK_TYPE_CHOICES, default='other')
    reason = models.CharField(max_length=255)
    notes = models.TextField(blank=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('users.User', on_delete=models.PROTECT, related_name='created_time_blocks')
    
    class Meta:
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['dentist', 'date'], name='time_block_dentist_date_idx'),
            models.Index(fields=['date', 'start_time'], name='time_block_date_time_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')) | 
                      (models.Q(start_time__isnull=True) & models.Q(end_time__isnull=True)),
                name='timeblock_valid_times'
            ),
        ]
    
    def __str__(self):
        if self.is_full_day:
            return f"{self.dentist.full_name} - {self.date} (Full Day) - {self.reason}"
        else:
            return f"{self.dentist.full_name} - {self.date} {self.start_time}-{self.end_time} - {self.reason}"
    
    @property
    def is_full_day(self):
        """Check if this is a full-day block"""
        return self.start_time is None and self.end_time is None
    
    def clean(self):
        # Full day blocks don't need time validation
        if self.is_full_day:
            return
        
        if not self.start_time or not self.end_time:
            raise ValidationError('Both start_time and end_time are required for partial day blocks.')
        
        if self.end_time <= self.start_time:
            raise ValidationError('End time must be after start time.')
        
        # Check for overlapping blocks for the same dentist on the same date
        overlapping = TimeBlock.objects.filter(
            dentist=self.dentist,
            date=self.date
        ).exclude(pk=self.pk)
        
        for block in overlapping:
            if self._blocks_overlap(block):
                raise ValidationError(
                    f'This time block overlaps with existing block: {block}'
                )
    
    def _blocks_overlap(self, other_block):
        """Check if this block overlaps with another block"""
        # If either block is full day, they overlap
        if self.is_full_day or other_block.is_full_day:
            return True
        
        # Check time overlap
        return (self.start_time < other_block.end_time and 
                self.end_time > other_block.start_time)
    
    def blocks_time(self, time_obj):
        """Check if this block covers a specific time"""
        if self.is_full_day:
            return True
        
        return self.start_time <= time_obj < self.end_time
    
    @classmethod
    def get_blocks_for_date(cls, dentist, date):
        """Get all active blocks for a dentist on a specific date"""
        return cls.objects.filter(dentist=dentist, date=date)
    
    @classmethod
    def is_time_blocked(cls, dentist, date, time_obj):
        """Check if a specific time is blocked for a dentist"""
        blocks = cls.get_blocks_for_date(dentist, date)
        return any(block.blocks_time(time_obj) for block in blocks)


class Appointment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('reassigned', 'Reassigned'),
        ('cancelled', 'Cancelled'),
        ('did_not_arrive', 'Did Not Arrive'),
        ('completed', 'Completed'),
    ]
    
    PATIENT_TYPE_CHOICES = [
        ('new', 'New Patient'),
        ('returning', 'Returning Patient'),
    ]
    
    # Define blocking statuses as a class attribute
    BLOCKING_STATUSES = ['pending', 'approved', 'completed']
    NON_BLOCKING_STATUSES = ['rejected', 'reassigned', 'cancelled', 'did_not_arrive']
    
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='appointments')
    dentist = models.ForeignKey('users.User', on_delete=models.PROTECT, related_name='appointments')
    service = models.ForeignKey('services.Service', on_delete=models.PROTECT)
    appointment_slot = models.ForeignKey(AppointmentSlot, on_delete=models.PROTECT, related_name='appointments')  # Updated reference
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    patient_type = models.CharField(max_length=10, choices=PATIENT_TYPE_CHOICES, default='returning')
    reason = models.TextField(blank=True)
    
    # Booking details
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_appointments')
    
    # Notes
    staff_notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['requested_at']
        indexes = [
            models.Index(fields=['status'], name='appt_status_idx'),
            models.Index(fields=['patient'], name='appt_patient_idx'),
            models.Index(fields=['dentist'], name='appt_dentist_idx'),
            models.Index(fields=['requested_at'], name='appt_requested_idx'),
            models.Index(fields=['dentist', 'status'], name='appt_dentist_status_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['appointment_slot'],
                condition=models.Q(status__in=['pending', 'approved', 'completed']),
                name='unique_active_appointment_per_slot'
            )
        ]
    
    def __str__(self):
        return f"{self.patient.full_name} - {self.appointment_slot.date} {self.appointment_slot.start_time}"
    
    @property
    def appointment_datetime(self):
        """Returns timezone-aware datetime for appointment"""
        naive_dt = datetime.combine(self.appointment_slot.date, self.appointment_slot.start_time)
        return timezone.make_aware(naive_dt) if timezone.is_naive(naive_dt) else naive_dt
    
    @property
    def appointment_end_datetime(self):
        """Returns timezone-aware datetime for appointment end (including buffer)"""
        naive_dt = datetime.combine(self.appointment_slot.date, self.appointment_slot.effective_end_time)
        return timezone.make_aware(naive_dt) if timezone.is_naive(naive_dt) else naive_dt
    
    @property
    def is_today(self):
        return self.appointment_slot.date == timezone.now().date()
    
    @property
    def is_upcoming(self):
        return self.appointment_datetime > timezone.now()
    
    @property
    def can_be_cancelled(self):
        """Can be cancelled if at least 24 hours before appointment"""
        if self.status in ['cancelled', 'completed', 'did_not_arrive']:
            return False
        
        current_time = timezone.now()
        appointment_time = self.appointment_datetime
        cutoff_time = current_time + timedelta(hours=24)
        
        return appointment_time > cutoff_time
    
    @property
    def blocks_time_slot(self):
        """Whether this appointment blocks its time slot"""
        return self.status in self.BLOCKING_STATUSES
    
    def approve(self, approved_by_user):
        """Approve the appointment"""
        self.status = 'approved'
        self.approved_at = timezone.now()
        self.approved_by = approved_by_user
        self.save()
    
    def reject(self):
        """Reject the appointment"""
        self.status = 'rejected'
        self.save()
    
    def cancel(self):
        """Cancel the appointment"""
        self.status = 'cancelled'
        self.save()
    
    def complete(self):
        """Mark appointment as completed"""
        self.status = 'completed'
        self.save()
    
    @classmethod
    def get_conflicting_appointments(cls, dentist, start_datetime, end_datetime, exclude_appointment_id=None):
        """
        Get appointments that conflict with the given time range
        FIXED VERSION with proper timezone handling
        """
        # Ensure we have timezone-aware datetimes
        if timezone.is_naive(start_datetime):
            start_datetime = timezone.make_aware(start_datetime)
        if timezone.is_naive(end_datetime):
            end_datetime = timezone.make_aware(end_datetime)
        
        conflicts = cls.objects.filter(
            dentist=dentist,
            appointment_slot__date=start_datetime.date(),
            status__in=cls.BLOCKING_STATUSES
        ).select_related('appointment_slot', 'service')
        
        if exclude_appointment_id:
            conflicts = conflicts.exclude(id=exclude_appointment_id)
        
        # Filter for time conflicts
        conflicting_appointments = []
        for appointment in conflicts:
            # Get timezone-aware datetimes for this appointment
            app_naive_start = datetime.combine(
                appointment.appointment_slot.date, 
                appointment.appointment_slot.start_time
            )
            app_naive_end = app_naive_start + timedelta(minutes=appointment.service.duration_minutes)
            app_naive_end_with_buffer = app_naive_end + timedelta(minutes=appointment.appointment_slot.buffer_minutes)
            
            # Make timezone-aware
            app_start = timezone.make_aware(app_naive_start) if timezone.is_naive(app_naive_start) else app_naive_start
            app_end = timezone.make_aware(app_naive_end_with_buffer) if timezone.is_naive(app_naive_end_with_buffer) else app_naive_end_with_buffer
            
            # Check for overlap - now both are timezone-aware
            if app_start < end_datetime and app_end > start_datetime:
                conflicting_appointments.append(appointment)
        
        return conflicting_appointments


class Payment(models.Model):
    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partially_paid', 'Partially Paid'),
        ('fully_paid', 'Fully Paid'),
    ]
    
    patient = models.ForeignKey('patients.Patient', on_delete=models.CASCADE, related_name='payments')
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='payments')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_datetime = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unpaid')
    next_due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-payment_datetime']
    
    def __str__(self):
        return f"{self.patient.full_name} - ₱{self.amount_paid} ({self.status})"


class PaymentItem(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='items')
    service = models.ForeignKey('services.Service', on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.ForeignKey('services.Discount', on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.service.name} x{self.quantity}"
    
    @property
    def subtotal(self):
        return self.unit_price * self.quantity
    
    @property
    def discount_amount(self):
        if not self.discount:
            return 0
        return self.discount.calculate_discount(self.subtotal)
    
    @property
    def total(self):
        return self.subtotal - self.discount_amount


# Keep the old DentistSchedule model for backward compatibility during migration
# This can be removed after all data is migrated to DentistScheduleSettings
# class DentistSchedule(models.Model):
#     """
#     DEPRECATED: Use DentistScheduleSettings instead
#     Kept for backward compatibility during migration
#     """
#     WEEKDAY_CHOICES = [
#         (0, 'Monday'),
#         (1, 'Tuesday'), 
#         (2, 'Wednesday'),
#         (3, 'Thursday'),
#         (4, 'Friday'),
#         (5, 'Saturday'),
#         (6, 'Sunday'),
#     ]
    
#     dentist = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='working_schedules')
#     weekday = models.IntegerField(choices=WEEKDAY_CHOICES)
#     is_working = models.BooleanField(default=True)
#     start_time = models.TimeField(default=time(10, 0))
#     end_time = models.TimeField(default=time(18, 0))
#     lunch_start = models.TimeField(default=time(12, 0))
#     lunch_end = models.TimeField(default=time(13, 0))
#     has_lunch_break = models.BooleanField(default=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
    
#     class Meta:
#         unique_together = ['dentist', 'weekday']
#         ordering = ['dentist', 'weekday']