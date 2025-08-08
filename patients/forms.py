# patients/forms.py
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date
from .models import Patient

class PatientForm(forms.ModelForm):
    """Form for creating and updating patient information"""
    
    class Meta:
        model = Patient
        fields = [
            'first_name', 'last_name', 'email', 'contact_number', 'address',
            'date_of_birth', 'emergency_contact_name', 'emergency_contact_phone', 
            'medical_notes'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'placeholder': 'Enter last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'placeholder': 'patient@example.com'
            }),
            'contact_number': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'placeholder': '+639123456789 or 09123456789'
            }),
            'address': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'rows': 3,
                'placeholder': 'Complete address including street, city, and postal code'
            }),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'type': 'date',
                'max': date.today().strftime('%Y-%m-%d')
            }),
            'emergency_contact_name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'placeholder': 'Emergency contact full name'
            }),
            'emergency_contact_phone': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'placeholder': '+639123456789'
            }),
            'medical_notes': forms.Textarea(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
                'rows': 4,
                'placeholder': 'Include any allergies, medical conditions, medications, or special instructions'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set required fields
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['email'].required = True
        
        # Set field labels with required indicators
        self.fields['first_name'].label = 'First Name'
        self.fields['last_name'].label = 'Last Name'
        self.fields['email'].label = 'Email Address'
        self.fields['contact_number'].label = 'Contact Number'
        self.fields['address'].label = 'Address'
        self.fields['date_of_birth'].label = 'Date of Birth'
        self.fields['emergency_contact_name'].label = 'Emergency Contact Name'
        self.fields['emergency_contact_phone'].label = 'Emergency Contact Phone'
        self.fields['medical_notes'].label = 'Medical Notes'
    
    def clean_email(self):
        """Validate email uniqueness"""
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower().strip()
            queryset = Patient.objects.filter(email__iexact=email)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise ValidationError('A patient with this email address already exists.')
        return email
    
    def clean_contact_number(self):
        """Clean and validate contact number"""
        contact_number = self.cleaned_data.get('contact_number', '').strip()
        if contact_number:
            # Remove spaces and dashes
            contact_number = contact_number.replace(' ', '').replace('-', '')
            
            # Convert local format to international
            if contact_number.startswith('09'):
                contact_number = '+63' + contact_number[1:]
            elif contact_number.startswith('9') and len(contact_number) == 10:
                contact_number = '+63' + contact_number
            
            # Validate format
            if not contact_number.startswith('+63') or len(contact_number) != 13:
                if not (contact_number.startswith('09') and len(contact_number) == 11):
                    raise ValidationError('Please enter a valid Philippine phone number (e.g., +639123456789 or 09123456789)')
        
        return contact_number
    
    def clean_date_of_birth(self):
        """Validate date of birth"""
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            if dob > date.today():
                raise ValidationError('Date of birth cannot be in the future.')
            
            # Check if too old (e.g., over 120 years)
            age = date.today().year - dob.year
            if age > 120:
                raise ValidationError('Please enter a valid date of birth.')
        
        return dob
    
    def clean_emergency_contact_phone(self):
        """Clean emergency contact phone"""
        phone = self.cleaned_data.get('emergency_contact_phone', '').strip()
        if phone:
            # Same validation as contact_number
            phone = phone.replace(' ', '').replace('-', '')
            
            if phone.startswith('09'):
                phone = '+63' + phone[1:]
            elif phone.startswith('9') and len(phone) == 10:
                phone = '+63' + phone
            
            if not phone.startswith('+63') or len(phone) != 13:
                if not (phone.startswith('09') and len(phone) == 11):
                    raise ValidationError('Please enter a valid Philippine phone number for emergency contact.')
        
        return phone
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        contact_number = cleaned_data.get('contact_number')
        
        # Ensure at least one contact method is provided
        if not email and not contact_number:
            raise ValidationError('Please provide at least an email address or contact number.')
        
        return cleaned_data


class PatientSearchForm(forms.Form):
    """Form for searching patients"""
    SEARCH_TYPE_CHOICES = [
        ('all', 'All Fields'),
        ('name', 'Name Only'),
        ('email', 'Email Only'),
        ('phone', 'Phone Only'),
    ]
    
    query = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'Search patients...'
        }),
        label='Search Query'
    )
    
    search_type = forms.ChoiceField(
        choices=SEARCH_TYPE_CHOICES,
        initial='all',
        widget=forms.Select(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'
        }),
        label='Search In'
    )


class FindPatientForm(forms.Form):
    """Form for finding patient by email or phone for appointment booking"""
    
    identifier = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500',
            'placeholder': 'Enter email address or phone number'
        }),
        label='Email or Phone Number',
        help_text='Enter the patient\'s email address or phone number to find their record'
    )
    
    def clean_identifier(self):
        """Clean and validate identifier"""
        identifier = self.cleaned_data.get('identifier', '').strip()
        if not identifier:
            raise ValidationError('Please enter an email address or phone number.')
        
        # Basic validation - check if it looks like email or phone
        if '@' in identifier:
            # Looks like email
            if not forms.EmailField().clean(identifier):
                raise ValidationError('Please enter a valid email address.')
        else:
            # Assume it's a phone number
            phone = identifier.replace(' ', '').replace('-', '')
            if phone.startswith('09'):
                phone = '+63' + phone[1:]
            elif phone.startswith('9') and len(phone) == 10:
                phone = '+63' + phone
            
            if not (phone.startswith('+63') and len(phone) == 13) and not (phone.startswith('09') and len(phone) == 11):
                raise ValidationError('Please enter a valid phone number or email address.')
        
        return identifier