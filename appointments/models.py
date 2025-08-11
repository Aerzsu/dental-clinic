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
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['date', 'start_time']
        unique_together = ['dentist', 'date', 'start_time']
    
    def __str__(self):
        return f"{self.dentist.full_name} - {self.date} {self.start_time}-{self.end_time}"
    
    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError('End time must be after start time.')
        
        # Check for overlapping schedules for the same dentist
        overlapping = Schedule.objects.filter(
            dentist=self.dentist,
            date=self.date,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).exclude(pk=self.pk)
        
        if overlapping.exists():
            raise ValidationError('This schedule overlaps with existing schedule.')

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
        ]
    
    def __str__(self):
        return f"{self.patient.full_name} - {self.schedule.date} {self.schedule.start_time}"
    
    @property
    def appointment_datetime(self):
        """Returns timezone-aware datetime for appointment"""
        naive_dt = datetime.combine(self.schedule.date, self.schedule.start_time)
        # Make it timezone-aware using the current timezone
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
        
        # Compare timezone-aware datetimes
        current_time = timezone.now()
        appointment_time = self.appointment_datetime
        cutoff_time = current_time + timedelta(hours=24)
        
        return appointment_time > cutoff_time
    
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