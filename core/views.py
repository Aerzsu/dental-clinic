# core/views.py
import json
from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.utils import timezone
from django.db.models import Q
from django.http import JsonResponse
from datetime import datetime, timedelta, date, time
from django import forms
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError
import re

from .models import AuditLog, Holiday, SystemSetting
from appointments.models import Appointment, Schedule
from patients.models import Patient
from services.models import Service
from users.models import User
from appointments.forms import AppointmentRequestForm
from appointments.views import create_appointment_atomic

class HolidayForm(forms.ModelForm):
    """Form for creating and updating holidays"""
    
    class Meta:
        model = Holiday
        fields = ['name', 'date', 'is_recurring']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
        }
        help_texts = {
            'is_recurring': 'Check if this holiday occurs every year on the same date',
        }
    
    def clean_date(self):
        date = self.cleaned_data['date']
        if date < timezone.now().date():
            raise forms.ValidationError('Holiday date cannot be in the past.')
        return date

class HomeView(TemplateView):
    """Public landing page"""
    template_name = 'core/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['services'] = Service.objects.filter(is_archived=False)[:6]
        context['dentists'] = User.objects.filter(is_active_dentist=True)
        return context

    
class BookAppointmentView(TemplateView):
    """Public appointment booking form with race condition prevention"""
    template_name = 'core/book_appointment.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Format services data
        services = []
        for service in Service.objects.filter(is_archived=False):
            services.append({
                'id': service.id,
                'name': service.name,
                'duration': f"{service.duration_minutes} minutes",
                'duration_minutes': service.duration_minutes,  # Add this for JS calculations
                'price_range': f"₱{service.min_price:,.0f} - ₱{service.max_price:,.0f}",
                'description': service.description or "Professional dental service"
            })
        
        # Format dentists data  
        dentists = []
        for dentist in User.objects.filter(is_active_dentist=True):
            dentists.append({
                'id': dentist.id,
                'name': f"Dr. {dentist.first_name} {dentist.last_name}",
                'initials': f"{dentist.first_name[0]}{dentist.last_name[0]}",
                'specialization': getattr(dentist, 'specialization', 'General Dentist')
            })
        
        context.update({
            'services_json': json.dumps(services),
            'dentists_json': json.dumps(dentists),
        })
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle appointment request submission with enhanced validation and race condition prevention"""
        try:
            # Check if request is JSON
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                return self._handle_json_request(data)
            else:
                # Handle regular form submission (fallback)
                return self._handle_form_request(request)
                
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Error in BookAppointmentView: {str(e)}', exc_info=True)
            
            return JsonResponse({
                'success': False, 
                'error': 'An unexpected error occurred. Please try again.'
            }, status=500)
    
    def _handle_json_request(self, data):
        """Handle JSON appointment request with atomic transactions"""
        # Validate required fields
        required_fields = ['patient_type', 'service', 'dentist', 'selected_date', 'selected_time']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'success': False, 'error': f'{field} is required'}, status=400)
        
        # Validate terms agreement
        if not data.get('agreed_to_terms'):
            return JsonResponse({'success': False, 'error': 'You must agree to the terms and conditions'}, status=400)
        
        try:
            # Use atomic transaction with database locking to prevent race conditions
            with transaction.atomic():
                # Get and validate service and dentist with locking
                try:
                    service = Service.objects.select_for_update().get(id=data['service'], is_archived=False)
                    dentist = User.objects.select_for_update().get(id=data['dentist'], is_active_dentist=True)
                except (Service.DoesNotExist, User.DoesNotExist):
                    return JsonResponse({'success': False, 'error': 'Invalid service or dentist'}, status=400)
                
                # Parse and validate date/time
                try:
                    appointment_date = datetime.strptime(data['selected_date'], '%Y-%m-%d').date()
                    appointment_time = datetime.strptime(data['selected_time'], '%H:%M').time()
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid date or time format'}, status=400)
                
                # Validate appointment date/time constraints
                validation_error = self._validate_appointment_datetime(appointment_date, appointment_time, service)
                if validation_error:
                    return JsonResponse({'success': False, 'error': validation_error}, status=400)
                
                # Handle patient creation/finding
                patient, patient_type = self._handle_patient_data(data)
                if isinstance(patient, JsonResponse):  # Error response
                    return patient
                
                # Get buffer time
                buffer_minutes = self._get_buffer_time()
                
                # Create appointment atomically with conflict checking
                try:
                    appointment = create_appointment_atomic(
                        patient=patient,
                        dentist=dentist,
                        service=service,
                        appointment_date=appointment_date,
                        appointment_time=appointment_time,
                        patient_type=patient_type,
                        reason=data.get('reason', '').strip(),
                        buffer_minutes=buffer_minutes
                    )[0]
                    
                    # Generate reference number
                    reference_number = f'APT-{appointment.id:06d}'
                    
                    return JsonResponse({
                        'success': True,
                        'reference_number': reference_number,
                        'appointment_id': appointment.id
                    })
                    
                except ValidationError as e:
                    return JsonResponse({'success': False, 'error': str(e)}, status=400)
                except IntegrityError:
                    return JsonResponse({
                        'success': False, 
                        'error': 'This time slot has been booked by another patient. Please select a different time.'
                    }, status=400)
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Error in _handle_json_request: {str(e)}', exc_info=True)
            
            return JsonResponse({
                'success': False, 
                'error': 'An error occurred while processing your request. Please try again.'
            }, status=500)
    
    def _validate_appointment_datetime(self, appointment_date, appointment_time, service):
        """Validate appointment date and time constraints"""
        # Check past dates
        if appointment_date <= timezone.now().date():
            return 'Appointment date must be in the future'
        
        # Check Sundays
        if appointment_date.weekday() == 6:  # Sunday
            return 'Appointments are not available on Sundays'
        
        # Check holidays
        holiday = Holiday.objects.filter(date=appointment_date, is_active=True).first()
        if holiday:
            return f'Appointments are not available on this date ({holiday.name})'
        
        # Check clinic hours
        clinic_start = time(10, 0)  # 10:00 AM
        clinic_end = time(18, 0)    # 6:00 PM
        lunch_start = time(12, 0)   # 12:00 PM
        lunch_end = time(13, 0)     # 1:00 PM
        
        if appointment_time < clinic_start or appointment_time >= clinic_end:
            return 'Appointments are available Monday to Saturday, 10:00 AM to 6:00 PM'
        
        # Check if appointment would extend past clinic hours or into lunch
        start_datetime = datetime.combine(appointment_date, appointment_time)
        service_end = start_datetime + timedelta(minutes=service.duration_minutes)
        service_end_time = service_end.time()
        
        if service_end_time > clinic_end:
            return f'Selected time is too late. Service duration is {service.duration_minutes} minutes and clinic closes at 6:00 PM'
        
        # Check lunch break conflict
        lunch_start_datetime = datetime.combine(appointment_date, lunch_start)
        lunch_end_datetime = datetime.combine(appointment_date, lunch_end)
        
        if not (service_end <= lunch_start_datetime or start_datetime >= lunch_end_datetime):
            return 'Appointment cannot be scheduled during lunch break (12:00 PM - 1:00 PM)'
        
        return None  # No validation errors
    
    def _handle_patient_data(self, data):
        """Handle patient creation or finding with validation"""
        patient_type_raw = data['patient_type']
        
        if patient_type_raw == 'new':
            return self._create_new_patient(data)
        elif patient_type_raw == 'existing':
            return self._find_existing_patient(data)
        else:
            return JsonResponse({'success': False, 'error': 'Invalid patient type'}, status=400), None
    
    def _create_new_patient(self, data):
        """Create new patient with validation"""
        required_new_fields = ['first_name', 'last_name', 'email']
        for field in required_new_fields:
            if not data.get(field, '').strip():
                field_label = field.replace('_', ' ').title()
                return JsonResponse({
                    'success': False, 
                    'error': f'{field_label} is required for new patients'
                }, status=400), None
        
        # Extract and validate data
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        email = data.get('email', '').strip()
        contact_number = data.get('contact_number', '').strip()
        address = data.get('address', '').strip()
        
        # Validate name fields
        name_pattern = re.compile(r'^[a-zA-Z\s\-\']+$')
        
        if not name_pattern.match(first_name):
            return JsonResponse({
                'success': False,
                'error': 'First name should only contain letters, spaces, hyphens, and apostrophes'
            }, status=400), None
        
        if not name_pattern.match(last_name):
            return JsonResponse({
                'success': False,
                'error': 'Last name should only contain letters, spaces, hyphens, and apostrophes'
            }, status=400), None
        
        # Validate email format
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError
        
        try:
            validate_email(email)
        except DjangoValidationError:
            return JsonResponse({
                'success': False,
                'error': 'Please enter a valid email address'
            }, status=400), None
        
        # Validate contact number if provided (optional)
        if contact_number:
            phone_pattern = re.compile(r'^(\+63|0)?9\d{9}$')
            clean_contact = contact_number.replace(' ', '').replace('-', '')
            if not phone_pattern.match(clean_contact):
                return JsonResponse({
                    'success': False,
                    'error': 'Please enter a valid Philippine mobile number (e.g., +639123456789)'
                }, status=400), None
            contact_number = clean_contact  # Use cleaned version
        
        # Check for existing patient - using select_for_update to prevent race conditions
        existing_query = Q()
        if email:
            existing_query |= Q(email__iexact=email, is_active=True)
        if contact_number:
            existing_query |= Q(contact_number=contact_number, is_active=True)
        
        if existing_query:
            existing = Patient.objects.select_for_update().filter(existing_query).first()
            
            if existing:
                return JsonResponse({
                    'success': False, 
                    'error': 'A patient with this email or contact number already exists. Please use "Existing Patient" option.'
                }, status=400), None
        
        # Create new patient
        patient = Patient.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            contact_number=contact_number or '',  # Allow empty string
            address=address,
        )
        
        return patient, 'new'
    
    def _find_existing_patient(self, data):
        """Find existing patient with validation"""
        identifier = data.get('patient_identifier', '').strip()
        if not identifier:
            return JsonResponse({'success': False, 'error': 'Patient identifier is required'}, status=400), None
        
        # Search with select_for_update to prevent race conditions
        query = Q(is_active=True)
        if '@' in identifier:
            query &= Q(email__iexact=identifier)
        else:
            clean_identifier = identifier.replace(' ', '').replace('-', '')
            query &= (Q(contact_number=identifier) | Q(contact_number=clean_identifier))
        
        patient = Patient.objects.select_for_update().filter(query).first()
        
        if not patient:
            return JsonResponse({
                'success': False, 
                'error': 'No patient found with the provided information. Please check your details or register as a new patient.'
            }, status=400), None
        
        return patient, 'returning'
    
    def _get_buffer_time(self):
        """Get buffer time from system settings or default"""
        try:
            buffer_setting = SystemSetting.objects.get(key='appointment_buffer_minutes')
            return int(buffer_setting.value)
        except (SystemSetting.DoesNotExist, ValueError):
            return 15  # Default 15 minutes
    
    def _handle_form_request(self, request):
        """Handle regular form submission (fallback)"""
        form = AppointmentRequestForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    appointment = form.save()
                    messages.success(
                        request,
                        'Your appointment request has been submitted successfully! '
                        'We will contact you soon to confirm your appointment.'
                    )
                    return redirect('core:home')
            except ValidationError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, 'An error occurred while submitting your request. Please try again.')
        
        context = self.get_context_data()
        context['form'] = form
        return render(request, self.template_name, context)

class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard for authenticated users"""
    template_name = 'core/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.now().date()
        
        # Today's appointments - we'll filter in Python to avoid field lookup issues
        all_appointments = Appointment.objects.filter(
            status__in=['approved', 'pending']
        ).select_related('patient', 'dentist', 'service', 'schedule')
        
        # Filter for today's appointments
        context['todays_appointments'] = [
            apt for apt in all_appointments if apt.schedule.date == today
        ]
        
        # Pending appointment requests
        context['pending_requests'] = Appointment.objects.filter(
            status='pending'
        ).count()
        
        # Recent patients
        context['recent_patients'] = Patient.objects.filter(
            is_active=True
        ).order_by('-created_at')[:5]
        
        # Statistics
        context['stats'] = {
            'total_patients': Patient.objects.filter(is_active=True).count(),
            'todays_appointments_count': len(context['todays_appointments']),
            'pending_requests_count': context['pending_requests'],
            'active_dentists': User.objects.filter(is_active_dentist=True).count(),
        }
        
        # Quick actions based on user role
        context['quick_actions'] = self.get_quick_actions()
        
        return context
    
    def get_quick_actions(self):
        """Get quick actions based on user permissions"""
        actions = []
        user = self.request.user
        
        if user.has_permission('appointments'):
            actions.extend([
                {'name': 'New Appointment', 'url': 'appointments:appointment_create', 'icon': 'calendar'},
                {'name': 'View Calendar', 'url': 'appointments:appointment_calendar', 'icon': 'calendar-view'},
            ])
        
        if user.has_permission('patients'):
            actions.extend([
                {'name': 'Add Patient', 'url': 'patients:patient_create', 'icon': 'user-plus'},
                {'name': 'Find Patient', 'url': 'patients:find_patient', 'icon': 'search'},
            ])
        
        if user.has_permission('maintenance'):
            actions.extend([
                {'name': 'Manage Users', 'url': 'users:user_list', 'icon': 'users'},
                {'name': 'System Settings', 'url': 'core:holiday_list', 'icon': 'settings'},
            ])
        
        return actions

class HolidayListView(LoginRequiredMixin, ListView):
    """Manage holidays that affect appointment availability"""
    model = Holiday
    template_name = 'core/holiday_list.html'
    context_object_name = 'holidays'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return Holiday.objects.filter(is_active=True).order_by('date')

class HolidayCreateView(LoginRequiredMixin, CreateView):
    """Create new holiday"""
    model = Holiday
    form_class = HolidayForm
    template_name = 'core/holiday_form.html'
    success_url = reverse_lazy('core:holiday_list')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, 'Holiday created successfully.')
        return super().form_valid(form)

class HolidayUpdateView(LoginRequiredMixin, UpdateView):
    """Update holiday"""
    model = Holiday
    form_class = HolidayForm
    template_name = 'core/holiday_form.html'
    success_url = reverse_lazy('core:holiday_list')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, 'Holiday updated successfully.')
        return super().form_valid(form)

class HolidayDeleteView(LoginRequiredMixin, DeleteView):
    """Delete holiday"""
    model = Holiday
    template_name = 'core/holiday_confirm_delete.html'
    success_url = reverse_lazy('core:holiday_list')
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Soft delete by setting is_active to False
        self.object.is_active = False
        self.object.save()
        messages.success(request, f'Holiday "{self.object.name}" deleted successfully.')
        return redirect(self.success_url)

class AuditLogListView(LoginRequiredMixin, ListView):
    """View audit logs for system activities"""
    model = AuditLog
    template_name = 'core/audit_logs.html'
    context_object_name = 'logs'
    paginate_by = 50
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = AuditLog.objects.select_related('user')
        
        # Filter by user if specified
        user_filter = self.request.GET.get('user')
        if user_filter:
            queryset = queryset.filter(user_id=user_filter)
        
        # Filter by action if specified
        action_filter = self.request.GET.get('action')
        if action_filter:
            queryset = queryset.filter(action=action_filter)
        
        # Filter by date range
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__gte=date_from)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__lte=date_to)
            except ValueError:
                pass
        
        return queryset.order_by('-timestamp')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.filter(is_active=True)
        context['actions'] = AuditLog.ACTION_CHOICES if hasattr(AuditLog, 'ACTION_CHOICES') else []
        context['filters'] = {
            'user': self.request.GET.get('user', ''),
            'action': self.request.GET.get('action', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }
        return context

class MaintenanceHubView(TemplateView):
    template_name = 'core/maintenance_hub.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Optional: Add counts for the stats section
        # context['users_count'] = User.objects.count()
        # context['services_count'] = Service.objects.count()
        # etc.
        return context

class SystemSettingsView(LoginRequiredMixin, TemplateView):
    """System settings management"""
    template_name = 'core/system_settings.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Get all system settings
        settings = {}
        for setting in SystemSetting.objects.all():
            settings[setting.key] = setting.value
        
        context['settings'] = settings
        context['stats'] = {
            'total_appointments': Appointment.objects.count(),
            'total_patients': Patient.objects.count(),
            'total_services': Service.objects.count(),
            'total_users': User.objects.count(),
        }
        return context