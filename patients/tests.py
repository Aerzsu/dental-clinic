# patients/tests.py
from django.test import TestCase
from datetime import date, timedelta
from .forms import PatientForm, FindPatientForm
from .models import Patient


class PatientFormTests(TestCase):
    """Test cases for PatientForm"""

    def setUp(self):
        """Set up test data"""
        self.valid_form_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john.doe@example.com',
            'contact_number': '09123456789',
            'address': '123 Test Street, Test City',
            'date_of_birth': '1990-01-01',
            'emergency_contact_name': 'Jane Doe',
            'emergency_contact_phone': '09123456788',
            'medical_notes': 'No known allergies'
        }

    def test_valid_form_submission(self):
        """Test form with all valid data"""
        form = PatientForm(data=self.valid_form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_required_fields(self):
        """Test that required fields are enforced"""
        # Test missing required fields
        incomplete_data = {}
        form = PatientForm(data=incomplete_data)
        self.assertFalse(form.is_valid())
        self.assertIn('first_name', form.errors)
        self.assertIn('last_name', form.errors)
        self.assertIn('email', form.errors)

    def test_emergency_contact_phone_empty_string(self):
        """Test emergency contact phone with empty string"""
        data = self.valid_form_data.copy()
        data['emergency_contact_phone'] = ''
        form = PatientForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        self.assertEqual(form.cleaned_data['emergency_contact_phone'], '')

    def test_emergency_contact_phone_whitespace_only(self):
        """Test emergency contact phone with whitespace only"""
        data = self.valid_form_data.copy()
        data['emergency_contact_phone'] = '   '
        form = PatientForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        self.assertEqual(form.cleaned_data['emergency_contact_phone'], '')

    def test_emergency_contact_phone_none_handling(self):
        """Test emergency contact phone handling None values"""
        # This simulates what happens when field is not provided at all
        data = self.valid_form_data.copy()
        del data['emergency_contact_phone']
        form = PatientForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_contact_number_empty_string(self):
        """Test contact number with empty string"""
        data = self.valid_form_data.copy()
        data['contact_number'] = ''
        form = PatientForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_contact_number_whitespace_only(self):
        """Test contact number with whitespace only"""
        data = self.valid_form_data.copy()
        data['contact_number'] = '   '
        form = PatientForm(data=data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_phone_number_format_conversion(self):
        """Test phone number format conversion"""
        test_cases = [
            ('09123456789', '+639123456789'),  # Local to international
            ('9123456789', '+639123456789'),   # 10-digit to international
            ('+639123456789', '+639123456789'), # Already international
            ('09-123-456-789', '+639123456789'), # With dashes
            ('0912 345 6789', '+639123456789'),  # With spaces
        ]
        
        for input_phone, expected_output in test_cases:
            data = self.valid_form_data.copy()
            data['contact_number'] = input_phone
            form = PatientForm(data=data)
            self.assertTrue(form.is_valid(), f"Form should be valid for {input_phone}. Errors: {form.errors}")
            self.assertEqual(form.cleaned_data['contact_number'], expected_output)

    def test_emergency_phone_format_conversion(self):
        """Test emergency phone number format conversion"""
        test_cases = [
            ('09123456789', '+639123456789'),
            ('9123456789', '+639123456789'),
            ('+639123456789', '+639123456789'),
        ]
        
        for input_phone, expected_output in test_cases:
            data = self.valid_form_data.copy()
            data['emergency_contact_phone'] = input_phone
            form = PatientForm(data=data)
            self.assertTrue(form.is_valid(), f"Form should be valid for {input_phone}")
            self.assertEqual(form.cleaned_data['emergency_contact_phone'], expected_output)

    def test_invalid_phone_numbers(self):
        """Test invalid phone number formats"""
        invalid_phones = [
            '123',  # Too short
            '09123456789012345',  # Too long
            'abc123456789',  # Contains letters
            '1234567890',  # Wrong format
        ]
        
        for invalid_phone in invalid_phones:
            data = self.valid_form_data.copy()
            data['contact_number'] = invalid_phone
            form = PatientForm(data=data)
            self.assertFalse(form.is_valid(), f"Form should be invalid for {invalid_phone}")

    def test_email_uniqueness(self):
        """Test email uniqueness validation"""
        # Create a patient first
        Patient.objects.create(
            first_name='Jane',
            last_name='Smith',
            email='jane@example.com'
        )
        
        # Try to create another patient with same email
        data = self.valid_form_data.copy()
        data['email'] = 'jane@example.com'
        form = PatientForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_email_uniqueness_case_insensitive(self):
        """Test email uniqueness is case insensitive"""
        Patient.objects.create(
            first_name='Jane',
            last_name='Smith',
            email='jane@example.com'
        )
        
        data = self.valid_form_data.copy()
        data['email'] = 'JANE@EXAMPLE.COM'
        form = PatientForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_date_of_birth_future_date(self):
        """Test date of birth cannot be in the future"""
        future_date = date.today() + timedelta(days=1)
        data = self.valid_form_data.copy()
        data['date_of_birth'] = future_date.strftime('%Y-%m-%d')
        form = PatientForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('date_of_birth', form.errors)

    def test_date_of_birth_too_old(self):
        """Test date of birth cannot be too old (over 120 years)"""
        old_date = date.today() - timedelta(days=365 * 121)  # 121 years ago
        data = self.valid_form_data.copy()
        data['date_of_birth'] = old_date.strftime('%Y-%m-%d')
        form = PatientForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('date_of_birth', form.errors)

    def test_contact_method_required(self):
        """Test that at least one contact method is required"""
        data = self.valid_form_data.copy()
        data['email'] = ''
        data['contact_number'] = ''
        form = PatientForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)

    def test_update_form_excludes_own_email(self):
        """Test that update form excludes own email from uniqueness check"""
        # Create a patient
        patient = Patient.objects.create(
            first_name='John',
            last_name='Doe',
            email='john@example.com'
        )
        
        # Update the same patient with same email should be valid
        data = self.valid_form_data.copy()
        data['email'] = 'john@example.com'
        form = PatientForm(data=data, instance=patient)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")


class FindPatientFormTests(TestCase):
    """Test cases for FindPatientForm"""

    def test_valid_email_identifier(self):
        """Test valid email as identifier"""
        form = FindPatientForm(data={'identifier': 'test@example.com'})
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_valid_phone_identifier(self):
        """Test valid phone as identifier"""
        form = FindPatientForm(data={'identifier': '09123456789'})
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")

    def test_empty_identifier(self):
        """Test empty identifier"""
        form = FindPatientForm(data={'identifier': ''})
        self.assertFalse(form.is_valid())
        self.assertIn('identifier', form.errors)

    def test_whitespace_only_identifier(self):
        """Test whitespace only identifier"""
        form = FindPatientForm(data={'identifier': '   '})
        self.assertFalse(form.is_valid())
        self.assertIn('identifier', form.errors)

    def test_invalid_email_identifier(self):
        """Test invalid email as identifier"""
        form = FindPatientForm(data={'identifier': 'invalid-email'})
        self.assertFalse(form.is_valid())
        self.assertIn('identifier', form.errors)

    def test_invalid_phone_identifier(self):
        """Test invalid phone as identifier"""
        form = FindPatientForm(data={'identifier': '123'})
        self.assertFalse(form.is_valid())
        self.assertIn('identifier', form.errors)


class PatientModelTests(TestCase):
    """Test cases for Patient model"""

    def setUp(self):
        self.patient = Patient.objects.create(
            first_name='John',
            last_name='Doe',
            email='john@example.com',
            contact_number='+639123456789',
            date_of_birth=date(1990, 1, 1)  # Use proper date object
        )

    def test_full_name_property(self):
        """Test full_name property"""
        self.assertEqual(self.patient.full_name, 'John Doe')

    def test_age_property(self):
        """Test age calculation"""
        # Calculate expected age more accurately
        today = date.today()
        birth_date = date(1990, 1, 1)
        expected_age = today.year - birth_date.year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            expected_age -= 1
        self.assertEqual(self.patient.age, expected_age)

    def test_is_minor_property(self):
        """Test is_minor property"""
        # Test with adult
        self.assertFalse(self.patient.is_minor)
        
        # Test with minor
        minor_patient = Patient.objects.create(
            first_name='Jane',
            last_name='Young',
            email='jane@example.com',
            date_of_birth=date.today() - timedelta(days=365 * 10)  # 10 years old
        )
        self.assertTrue(minor_patient.is_minor)

    def test_contact_info_property(self):
        """Test contact_info property"""
        expected = 'john@example.com | +639123456789'
        self.assertEqual(self.patient.contact_info, expected)

    def test_can_be_found_by_method(self):
        """Test can_be_found_by method"""
        self.assertTrue(self.patient.can_be_found_by('john@example.com'))
        self.assertTrue(self.patient.can_be_found_by('JOHN@EXAMPLE.COM'))
        self.assertTrue(self.patient.can_be_found_by('+639123456789'))
        self.assertFalse(self.patient.can_be_found_by('wrong@email.com'))

    def test_str_representation(self):
        """Test string representation"""
        self.assertEqual(str(self.patient), 'Doe, John')