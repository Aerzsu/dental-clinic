# appointments/models.py
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, time, timedelta


class Schedule(models.Model):
    dentist = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='schedules')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    buffer_minutes = models.PositiveIntegerField(default=15, help_text="Buffer time after appointment for cleaning/prep")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['date', 'start_time']
        # Updated constraint to prevent overlapping schedules
        unique_together = ['dentist', 'date', 'start_time', 'end_time']
        indexes = [
            models.Index(fields=['dentist', 'date']),
            models.Index(fields=['date', 'start_time']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')), 
                name='schedule_end_after_start'
            ),
            models.CheckConstraint(
                check=models.Q(buffer_minutes__gte=0), 
                name='schedule_non_negative_buffer'
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
        
        # Check for overlapping schedules for the same dentist on the same date
        overlapping = Schedule.objects.filter(
            dentist=self.dentist,
            date=self.date
        ).exclude(pk=self.pk)
        
        for schedule in overlapping:
            if self._schedules_overlap(schedule):
                raise ValidationError(
                    f'This schedule overlaps with existing schedule: '
                    f'{schedule.start_time}-{schedule.end_time}'
                )
    
    def _schedules_overlap(self, other_schedule):
        """Check if this schedule overlaps with another schedule (including buffer)"""
        # Use effective end times that include buffer
        self_effective_end = self.effective_end_time
        other_effective_end = other_schedule.effective_end_time
        
        # Two schedules overlap if:
        # - This schedule starts before other ends AND this schedule ends after other starts
        return (self.start_time < other_effective_end and 
                self_effective_end > other_schedule.start_time)


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
    schedule = models.ForeignKey(Schedule, on_delete=models.PROTECT, related_name='appointments')
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
            models.Index(fields=['status']),
            models.Index(fields=['patient']),
            models.Index(fields=['dentist']),
            models.Index(fields=['requested_at']),
            # Index for efficient conflict detection
            models.Index(fields=['dentist', 'status']),
        ]
        constraints = [
            # Use string values instead of referencing class attribute
            models.UniqueConstraint(
                fields=['schedule'],
                condition=models.Q(status__in=['pending', 'approved', 'completed']),
                name='unique_active_appointment_per_schedule'
            )
        ]
    
    def __str__(self):
        return f"{self.patient.full_name} - {self.schedule.date} {self.schedule.start_time}"
    
    @property
    def appointment_datetime(self):
        """Returns timezone-aware datetime for appointment"""
        naive_dt = datetime.combine(self.schedule.date, self.schedule.start_time)
        return timezone.make_aware(naive_dt) if timezone.is_naive(naive_dt) else naive_dt
    
    @property
    def appointment_end_datetime(self):
        """Returns timezone-aware datetime for appointment end (including buffer)"""
        naive_dt = datetime.combine(self.schedule.date, self.schedule.effective_end_time)
        return timezone.make_aware(naive_dt) if timezone.is_naive(naive_dt) else naive_dt
    
    @property
    def is_today(self):
        return self.schedule.date == timezone.now().date()
    
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
        Get appointments that conflict with the given time range.
        
        Args:
            dentist: User object (dentist)
            start_datetime: datetime object for appointment start
            end_datetime: datetime object for appointment end (including buffer)
            exclude_appointment_id: Optional appointment ID to exclude from conflict check
        
        Returns:
            List of conflicting appointments
        """
        conflicts = cls.objects.filter(
            dentist=dentist,
            schedule__date=start_datetime.date(),
            status__in=cls.BLOCKING_STATUSES
        ).select_related('schedule', 'service')
        
        if exclude_appointment_id:
            conflicts = conflicts.exclude(id=exclude_appointment_id)
        
        # Filter for time conflicts
        conflicting_appointments = []
        for appointment in conflicts:
            app_start = appointment.appointment_datetime
            app_end = appointment.appointment_end_datetime
            
            # Check for overlap: appointment overlaps if it starts before end_datetime and ends after start_datetime
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