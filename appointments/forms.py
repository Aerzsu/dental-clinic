#appointments/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, datetime, time, timedelta
from django.db.models import Q
from .models import Appointment, AppointmentSlot, DentistScheduleSettings, TimeBlock
from patients.models import Patient
from services.models import Service
from users.models import User
from core.models import Holiday
import re
from django.core.validators import validate_email

class AppointmentForm(forms.ModelForm):
    """Form for creating/editing appointments"""
    
    class Meta:
        model = Appointment
        fields = ['patient', 'dentist', 'service', 'appointment_slot', 'patient_type', 'reason']
        widgets = {
            'patient': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'required': True
            }),
            'dentist': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'required': True
            }),
            'service': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'required': True
            }),
            'appointment_slot': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'required': True
            }),
            'patient_type': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'rows': 3,
                'placeholder': 'Optional appointment reason or notes...'
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter active entities
        self.fields['patient'].queryset = Patient.objects.filter(is_active=True).order_by('first_name', 'last_name')
        self.fields['dentist'].queryset = User.objects.filter(is_active_dentist=True).order_by('first_name', 'last_name')
        self.fields['service'].queryset = Service.objects.filter(is_archived=False).order_by('name')
        
        # Filter available appointment slots
        today = timezone.now().date()
        self.fields['appointment_slot'].queryset = AppointmentSlot.objects.filter(
            date__gte=today,
            is_available=True
        ).select_related('dentist').order_by('date', 'start_time')
    
    def clean(self):
        cleaned_data = super().clean()
        appointment_slot = cleaned_data.get('appointment_slot')
        service = cleaned_data.get('service')
        
        if appointment_slot and service:
            # Check if slot can accommodate service duration
            slot_duration = datetime.combine(date.today(), appointment_slot.end_time) - \
                          datetime.combine(date.today(), appointment_slot.start_time)
            
            if slot_duration.total_seconds() < service.duration_minutes * 60:
                raise ValidationError('Selected time slot is too short for this service.')
        
        return cleaned_data

class ScheduleForm(forms.ModelForm):
    """Form for creating dentist schedules"""
    
    class Meta:
        model = AppointmentSlot
        fields = ['dentist', 'date', 'start_time', 'end_time', 'notes']
        widgets = {
            'dentist': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'notes': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['dentist'].queryset = User.objects.filter(is_active_dentist=True).order_by('first_name', 'last_name')
        
        # Set minimum date to today
        self.fields['date'].widget.attrs['min'] = timezone.now().date().strftime('%Y-%m-%d')
    
    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('date')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if date:
            # Don't allow past dates
            if date < timezone.now().date():
                raise ValidationError('Schedule date cannot be in the past.')
            
            # Don't allow Sundays
            if date.weekday() == 6:
                raise ValidationError('Appointments are not available on Sundays.')
            
            # Check for holidays
            if Holiday.objects.filter(date=date, is_active=True).exists():
                holiday = Holiday.objects.filter(date=date, is_active=True).first()
                raise ValidationError(f'Cannot schedule appointments on {holiday.name}.')
        
        if start_time and end_time:
            if end_time <= start_time:
                raise ValidationError('End time must be after start time.')
            
            # Validate clinic hours (10 AM to 6 PM)
            clinic_start = time(10, 0)  # 10:00 AM
            clinic_end = time(18, 0)    # 6:00 PM
            
            if start_time < clinic_start or end_time > clinic_end:
                raise ValidationError('Appointments are available Monday to Saturday 10:00 AM to 6:00 PM.')
        
        return cleaned_data

# FOR APPOINTMENT BOOKING PAGE
class AppointmentRequestForm(forms.ModelForm):
    """Form for public appointment requests with enhanced validation"""
    
    patient_type = forms.ChoiceField(
        choices=[('new', 'New Patient'), ('existing', 'Existing Patient')],
        widget=forms.RadioSelect(attrs={'class': 'focus:ring-primary-500 h-4 w-4 text-primary-600 border-gray-300'})
    )
    
    # Patient identification fields (for existing patients)
    patient_identifier = forms.CharField(
        max_length=200,
        required=False,
        label='Email or Phone Number',
        help_text='Enter your email address or contact number',
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'patient@example.com or +639123456789'
        })
    )
    
    # New patient fields - Email required, contact optional
    first_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'})
    )
    last_name = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'})
    )
    email = forms.EmailField(
        required=False,  # Will be conditionally required in clean()
        widget=forms.EmailInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'})
    )
    contact_number = forms.CharField(
        max_length=20,
        required=False,  # Optional for new patients
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': '+639123456789'
        })
    )
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'rows': 3
        })
    )
    
    # Appointment fields
    preferred_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        })
    )
    preferred_time = forms.TimeField(
        widget=forms.TimeInput(attrs={
            'type': 'time',
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        })
    )
    
    class Meta:
        model = Appointment
        fields = ['service', 'dentist', 'reason']
        widgets = {
            'service': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'dentist': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'reason': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'rows': 3,
                'placeholder': 'Optional: Please describe your symptoms or reason for visit'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Filter querysets for active items only
        self.fields['service'].queryset = Service.objects.filter(is_archived=False).order_by('name')
        self.fields['dentist'].queryset = User.objects.filter(is_active_dentist=True).order_by('first_name', 'last_name')
        
        # Set minimum date to tomorrow
        tomorrow = (timezone.now() + timedelta(days=1)).date()
        self.fields['preferred_date'].widget.attrs['min'] = tomorrow.strftime('%Y-%m-%d')
        
        # Make reason optional
        self.fields['reason'].required = False
    
    def clean_first_name(self):
        """Validate first name contains only valid characters"""
        first_name = self.cleaned_data.get('first_name', '').strip()
        if first_name:
            name_pattern = re.compile(r'^[a-zA-Z\s\-\']+$')
            if not name_pattern.match(first_name):
                raise ValidationError('First name should only contain letters, spaces, hyphens, and apostrophes.')
        return first_name
    
    def clean_last_name(self):
        """Validate last name contains only valid characters"""
        last_name = self.cleaned_data.get('last_name', '').strip()
        if last_name:
            name_pattern = re.compile(r'^[a-zA-Z\s\-\']+$')
            if not name_pattern.match(last_name):
                raise ValidationError('Last name should only contain letters, spaces, hyphens, and apostrophes.')
        return last_name
    
    def clean_email(self):
        """Validate email format"""
        email = self.cleaned_data.get('email', '').strip()
        if email:
            try:
                validate_email(email)
            except ValidationError:
                raise ValidationError('Please enter a valid email address.')
        return email
    
    def clean_contact_number(self):
        """Validate contact number format if provided"""
        contact_number = self.cleaned_data.get('contact_number', '').strip()
        if not contact_number:
            return None
        
        # Philippine mobile number pattern
        phone_pattern = re.compile(r'^(\+63|0)?[9]\d{9}$')
        clean_contact = contact_number.replace(' ', '')
        if not phone_pattern.match(clean_contact):
            raise ValidationError('Please enter a valid Philippine mobile number (e.g., +639123456789).')
        
        return contact_number
    
    def clean(self):
        cleaned_data = super().clean()
        patient_type = cleaned_data.get('patient_type')
        
        if patient_type == 'existing':
            # Validate existing patient identification
            patient_identifier = cleaned_data.get('patient_identifier', '').strip()
            if not patient_identifier:
                raise ValidationError('Please provide your email or phone number to find your record.')
            
            # Try to find the patient
            patient = Patient.objects.filter(
                Q(email__iexact=patient_identifier) | Q(contact_number=patient_identifier),
                is_active=True
            ).first()
            
            if not patient:
                raise ValidationError(f'No patient record found with "{patient_identifier}". Please check your information or register as a new patient.')
            
            cleaned_data['patient'] = patient
        
        elif patient_type == 'new':
            # Validate new patient fields - email is required, contact is optional
            required_fields = ['first_name', 'last_name', 'email']
            for field in required_fields:
                value = cleaned_data.get(field, '').strip() if cleaned_data.get(field) else ''
                if not value:
                    field_label = self.fields[field].label or field.replace('_', ' ').title()
                    raise ValidationError(f'{field_label} is required for new patients.')
            
            # Check if patient already exists
            email = cleaned_data.get('email', '').strip()
            contact_number = cleaned_data.get('contact_number', '').strip()
            
            # Build query for existing patient check - ONLY include non-empty values
            existing_query = Q()
            
            # Always check email if provided (email is required for new patients)
            if email:
                existing_query |= Q(email__iexact=email, is_active=True)
            
            # Only check contact number if it's not empty
            if contact_number:
                existing_query |= Q(contact_number=contact_number, is_active=True)
            
            # Only run the query if we have something to search for
            if existing_query:
                existing_patient = Patient.objects.filter(existing_query).first()
                
                if existing_patient:
                    # Check which field matched
                    if existing_patient.email and email and existing_patient.email.lower() == email.lower():
                        raise ValidationError(f'A patient with email "{email}" already exists. Please use "Existing Patient" option.')
                    elif existing_patient.contact_number and contact_number and existing_patient.contact_number == contact_number:
                        raise ValidationError(f'A patient with contact number "{contact_number}" already exists. Please use "Existing Patient" option.')
        
        # Validate appointment date and time
        preferred_date = cleaned_data.get('preferred_date')
        preferred_time = cleaned_data.get('preferred_time')
        
        if preferred_date:
            # Don't allow past dates
            if preferred_date <= timezone.now().date():
                raise ValidationError('Appointment date must be in the future.')
            
            # Don't allow Sundays
            if preferred_date.weekday() == 6:
                raise ValidationError('Appointments are not available on Sundays.')
            
            # Check for holidays
            holiday = Holiday.objects.filter(date=preferred_date, is_active=True).first()
            if holiday:
                raise ValidationError(f'Appointments are not available on {holiday.name}.')
        
        if preferred_time:
            # Validate clinic hours
            clinic_start = time(10, 0)  # 10:00 AM
            clinic_end = time(18, 0)    # 6:00 PM
            
            if preferred_time < clinic_start or preferred_time >= clinic_end:
                raise ValidationError('Appointments are available Monday to Saturday, 10:00 AM to 6:00 PM.')
        
        # Validate service duration doesn't extend beyond clinic hours
        if preferred_date and preferred_time and cleaned_data.get('service'):
            service = cleaned_data['service']
            start_datetime = datetime.combine(preferred_date, preferred_time)
            end_time = (start_datetime + timedelta(minutes=service.duration_minutes)).time()
            
            if end_time > time(18, 0):  # 6:00 PM
                raise ValidationError(f'Selected time is too late. Service duration is {service.duration_minutes} minutes and clinic closes at 6:00 PM.')
        
        return cleaned_data
    
    def save(self, commit=True):
        appointment = super().save(commit=False)
        
        # Handle patient creation/assignment
        patient_type = self.cleaned_data['patient_type']
        
        if patient_type == 'new':
            # Create new patient
            patient = Patient.objects.create(
                first_name=self.cleaned_data['first_name'].strip(),
                last_name=self.cleaned_data['last_name'].strip(),
                email=self.cleaned_data.get('email', '').strip(),
                contact_number=self.cleaned_data.get('contact_number', '').strip(),
                address=self.cleaned_data.get('address', '').strip(),
            )
            appointment.patient = patient
            appointment.patient_type = 'new'
        else:
            # Use existing patient
            appointment.patient = self.cleaned_data['patient']
            appointment.patient_type = 'returning'
        
        # Create or find appropriate schedule
        preferred_date = self.cleaned_data['preferred_date']
        preferred_time = self.cleaned_data['preferred_time']
        dentist = self.cleaned_data['dentist']
        service = self.cleaned_data['service']
        
        # Calculate end time based on service duration
        start_datetime = datetime.combine(preferred_date, preferred_time)
        end_time = (start_datetime + timedelta(minutes=service.duration_minutes)).time()
        
        # Try to find existing schedule or create new one
        schedule, created = AppointmentSlot.objects.get_or_create(
            dentist=dentist,
            date=preferred_date,
            start_time=preferred_time,
            defaults={
                'end_time': end_time,
                'is_available': True,
                'notes': f'Auto-created for appointment request'
            }
        )
        
        appointment.schedule = schedule
        appointment.status = 'pending'  # All public requests start as pending
        
        if commit:
            appointment.save()
        
        return appointment

# Import models for the clean method
from django.db import models

#SCHEDULE MANAGEMENT FOR DENTISTS
class DentistScheduleSettingsForm(forms.ModelForm):
    """Form for managing individual dentist schedule settings for one weekday"""
    
    class Meta:
        model = DentistScheduleSettings
        fields = [
            'is_working', 'start_time', 'end_time', 
            'has_lunch_break', 'lunch_start', 'lunch_end',
            'default_buffer_minutes', 'slot_duration_minutes'
        ]
        widgets = {
            'is_working': forms.CheckboxInput(attrs={
                'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'x-model': 'isWorking'
            }),
            'start_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'step': '900',  # 15 minutes
                'x-show': 'isWorking'
            }),
            'end_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'step': '900',  # 15 minutes
                'x-show': 'isWorking'
            }),
            'has_lunch_break': forms.CheckboxInput(attrs={
                'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'x-model': 'hasLunchBreak',
                'x-show': 'isWorking'
            }),
            'lunch_start': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'step': '900',  # 15 minutes
                'x-show': 'isWorking && hasLunchBreak'
            }),
            'lunch_end': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'step': '900',  # 15 minutes
                'x-show': 'isWorking && hasLunchBreak'
            }),
            'default_buffer_minutes': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'min': '0',
                'max': '60',
                'x-show': 'isWorking'
            }),
            'slot_duration_minutes': forms.NumberInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'min': '15',
                'max': '120',
                'step': '15',
                'x-show': 'isWorking'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default values for new schedules
        if not self.instance.pk:
            self.fields['start_time'].initial = time(10, 0)
            self.fields['end_time'].initial = time(18, 0)
            self.fields['lunch_start'].initial = time(12, 0)
            self.fields['lunch_end'].initial = time(13, 0)
            self.fields['default_buffer_minutes'].initial = 15
            self.fields['slot_duration_minutes'].initial = 30
    
    def clean(self):
        cleaned_data = super().clean()
        is_working = cleaned_data.get('is_working')
        
        if not is_working:
            # Clear other fields if not working
            cleaned_data['has_lunch_break'] = False
            return cleaned_data
        
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        has_lunch_break = cleaned_data.get('has_lunch_break')
        lunch_start = cleaned_data.get('lunch_start')
        lunch_end = cleaned_data.get('lunch_end')
        
        # Validate working hours
        if start_time and end_time:
            if end_time <= start_time:
                raise ValidationError('End time must be after start time.')
        
        # Validate lunch break if enabled
        if has_lunch_break and lunch_start and lunch_end:
            if lunch_end <= lunch_start:
                raise ValidationError('Lunch end time must be after lunch start time.')
            
            # Check lunch is within working hours
            if start_time and end_time:
                if lunch_start < start_time or lunch_end > end_time:
                    raise ValidationError('Lunch break must be within working hours.')
            
            # Check lunch duration (max 2 hours)
            lunch_duration = datetime.combine(datetime.today(), lunch_end) - \
                           datetime.combine(datetime.today(), lunch_start)
            if lunch_duration.total_seconds() > 7200:  # 2 hours
                raise ValidationError('Lunch break cannot exceed 2 hours.')
        
        return cleaned_data


class TimeBlockForm(forms.ModelForm):
    """Form for creating time blocks (vacations, meetings, etc.)"""
    
    date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'min': timezone.now().date().strftime('%Y-%m-%d')  # Prevent past dates
        }),
        help_text="Date to block appointments"
    )
    
    is_full_day = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'x-model': 'isFullDay'
        }),
        label="Block entire day",
        help_text="Check to block the entire day, uncheck to block specific times"
    )
    
    class Meta:
        model = TimeBlock
        fields = ['dentist', 'date', 'is_full_day', 'start_time', 'end_time', 'block_type', 'reason', 'notes']
        widgets = {
            'dentist': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'required': True
            }),
            'start_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'step': '900',  # 15 minutes
                'x-show': '!isFullDay'
            }),
            'end_time': forms.TimeInput(attrs={
                'type': 'time',
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'step': '900',  # 15 minutes
                'x-show': '!isFullDay'
            }),
            'block_type': forms.Select(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
            }),
            'reason': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'placeholder': 'Brief reason for blocking this time (e.g., Vacation, Meeting)',
                'maxlength': 255
            }),
            'notes': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'rows': 3,
                'placeholder': 'Additional notes or details...'
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Filter dentists
        self.fields['dentist'].queryset = User.objects.filter(is_active_dentist=True).order_by('first_name', 'last_name')
        
        # Set current user as default if they're a dentist
        if self.user and self.user.is_active_dentist and not self.instance.pk:
            self.fields['dentist'].initial = self.user
    
    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('date')
        is_full_day = cleaned_data.get('is_full_day')
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        # Validate date is not in the past
        if date and date < timezone.now().date():
            raise ValidationError('Cannot create time blocks for past dates.')
        
        if is_full_day:
            # Clear time fields for full day blocks
            cleaned_data['start_time'] = None
            cleaned_data['end_time'] = None
        else:
            # Validate time fields for partial blocks
            if not start_time:
                raise ValidationError('Start time is required for partial day blocks.')
            if not end_time:
                raise ValidationError('End time is required for partial day blocks.')
            
            if start_time and end_time and end_time <= start_time:
                raise ValidationError('End time must be after start time.')
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set created_by if user is available
        if self.user and not instance.created_by_id:
            instance.created_by = self.user
        
        if commit:
            instance.save()
        
        return instance


class BulkTimeBlockForm(forms.Form):
    """Form for creating multiple time blocks (e.g., vacation period)"""
    
    dentist = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active_dentist=True),
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'required': True
        })
    )
    
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'min': timezone.now().date().strftime('%Y-%m-%d')
        })
    )
    
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'min': timezone.now().date().strftime('%Y-%m-%d')
        })
    )
    
    block_type = forms.ChoiceField(
        choices=TimeBlock.BLOCK_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        })
    )
    
    reason = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'Reason for blocking (e.g., Summer Vacation)'
        })
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'rows': 3,
            'placeholder': 'Additional notes...'
        })
    )
    
    include_weekends = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        help_text="Include Saturdays and Sundays in the date range"
    )
    
    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if end_date < start_date:
                raise ValidationError('End date must be after start date.')
            
            # Check for reasonable date range (max 6 months)
            date_diff = end_date - start_date
            if date_diff.days > 180:
                raise ValidationError('Date range cannot exceed 6 months.')
        
        return cleaned_data
    
    def create_blocks(self, user):
        """Create time blocks for each day in the date range"""
        cleaned_data = self.cleaned_data
        dentist = cleaned_data['dentist']
        start_date = cleaned_data['start_date']
        end_date = cleaned_data['end_date']
        include_weekends = cleaned_data['include_weekends']
        
        blocks_created = []
        current_date = start_date
        
        while current_date <= end_date:
            # Skip weekends if not included
            if not include_weekends and current_date.weekday() >= 5:  # Saturday=5, Sunday=6
                current_date += timedelta(days=1)
                continue
            
            # Check if block already exists
            existing_block = TimeBlock.objects.filter(
                dentist=dentist,
                date=current_date
            ).first()
            
            if not existing_block:
                block = TimeBlock.objects.create(
                    dentist=dentist,
                    date=current_date,
                    block_type=cleaned_data['block_type'],
                    reason=cleaned_data['reason'],
                    notes=cleaned_data['notes'],
                    created_by=user
                )
                blocks_created.append(block)
            
            current_date += timedelta(days=1)
        
        return blocks_created


class QuickTimeBlockForm(forms.Form):
    """Simplified form for quick time blocking from calendar view"""
    
    date = forms.DateField(widget=forms.HiddenInput())
    start_time = forms.TimeField(widget=forms.HiddenInput())
    end_time = forms.TimeField(widget=forms.HiddenInput())
    dentist = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active_dentist=True),
        widget=forms.HiddenInput()
    )
    
    reason = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'Quick reason (e.g., Emergency, Meeting)',
            'autofocus': True
        })
    )
    
    block_type = forms.ChoiceField(
        choices=[
            ('meeting', 'Meeting'),
            ('personal', 'Personal'),
            ('other', 'Other')
        ],
        initial='other',
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get('date')
        
        if date and date < timezone.now().date():
            raise ValidationError('Cannot create blocks for past dates.')
        
        return cleaned_data