# patients/models.py
from django.db import models
from django.urls import reverse
from django.core.validators import RegexValidator

class Patient(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    contact_number = models.CharField(validators=[phone_regex], max_length=17, blank=True, null=True)
    address = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    
    # System fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['contact_number']),
            models.Index(fields=['last_name', 'first_name']),
        ]
    
    def __str__(self):
        return f"{self.last_name}, {self.first_name}"
    
    def get_absolute_url(self):
        return reverse('patients:detail', kwargs={'pk': self.pk})
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self):
        """Calculate and return patient's age"""
        if not self.date_of_birth:
            return None
        
        from datetime import date
        today = date.today()
        age = today.year - self.date_of_birth.year
        
        # Adjust if birthday hasn't occurred this year yet
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            age -= 1
        
        return age

    @property
    def is_minor(self):
        """Check if patient is under 18"""
        if not self.date_of_birth:
            return False
        from datetime import date
        today = date.today()
        age = today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
        return age < 18
    
    @property
    def contact_info(self):
        """Return available contact information"""
        contacts = []
        if self.email:
            contacts.append(self.email)
        if self.contact_number:
            contacts.append(self.contact_number)
        return " | ".join(contacts)
    
    def can_be_found_by(self, identifier):
        """Check if patient can be found by email or phone"""
        return (
            (self.email and self.email.lower() == identifier.lower()) or
            (self.contact_number and self.contact_number == identifier)
        )

class TreatmentNote(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='treatment_notes')
    tooth_number = models.CharField(max_length=10, blank=True)
    notes = models.TextField()
    date_recorded = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey('users.User', on_delete=models.PROTECT)
    uploaded_file = models.FileField(upload_to='treatment_files/', blank=True)
    
    class Meta:
        ordering = ['-date_recorded']
    
    def __str__(self):
        return f"{self.patient.full_name} - {self.date_recorded.strftime('%Y-%m-%d')}"