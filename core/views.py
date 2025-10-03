# core/views.py - Updated for AM/PM slot system
import json
from django.shortcuts import redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.views.generic import TemplateView, ListView
from django.utils import timezone
from django.db.models import Q
from django.http import JsonResponse
from datetime import datetime
from django.db import transaction
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError
import re
import pytz

from .models import AuditLog, SystemSetting
from appointments.models import Appointment, DailySlots
from patients.models import Patient
from services.models import Service
from users.models import User

class HomeView(TemplateView):
    """Public landing page"""
    template_name = 'core/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['services'] = Service.objects.filter(is_archived=False)[:6]
        context['dentists'] = User.objects.filter(is_active_dentist=True)
        return context

class BookAppointmentView(TemplateView):
    """
    PUBLIC VIEW: Simplified appointment booking using AM/PM slots (NO dentist selection)
    """
    template_name = 'core/book_appointment.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get services for booking form
        services = []
        for service in Service.objects.filter(is_archived=False).order_by('name'):
            services.append({
                'id': service.id,
                'name': service.name,
                'duration_minutes': service.duration_minutes if hasattr(service, 'duration_minutes') else 30,
                'price_range': f"₱{service.min_price:,.0f} - ₱{service.max_price:,.0f}" if hasattr(service, 'min_price') else "Contact clinic for pricing",
                'description': service.description or "Professional dental service"
            })
        
        # Get period descriptions (configurable in future)
        am_period_display = SystemSetting.get_setting('am_period_display', '8:00 AM - 12:00 PM')
        pm_period_display = SystemSetting.get_setting('pm_period_display', '1:00 PM - 6:00 PM')
        
        context.update({
            'services_json': json.dumps(services),
            'am_period_display': am_period_display,
            'pm_period_display': pm_period_display,
        })
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle appointment booking submission - UPDATED for AM/PM slots"""
        try:
            # Check if request is JSON
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                return self._handle_json_request(data)
            else:
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
        """Handle JSON appointment request - UPDATED to skip automatic audit log"""
        # Validate required fields
        required_fields = ['patient_type', 'service', 'appointment_date', 'period']
        for field in required_fields:
            if not data.get(field):
                return JsonResponse({'success': False, 'error': f'{field} is required'}, status=400)
        
        # Validate terms agreement
        if not data.get('agreed_to_terms'):
            return JsonResponse({'success': False, 'error': 'You must agree to the terms and conditions'}, status=400)
        
        try:
            with transaction.atomic():
                # Get and validate service
                try:
                    service = Service.objects.get(id=data['service'], is_archived=False)
                except Service.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Invalid service selected'}, status=400)
                
                # Parse and validate appointment date
                try:
                    appointment_date = datetime.strptime(data['appointment_date'], '%Y-%m-%d').date()
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid date format'}, status=400)
                
                # Validate period
                period = data.get('period')
                if period not in ['AM', 'PM']:
                    return JsonResponse({'success': False, 'error': 'Invalid period. Must be AM or PM'}, status=400)
                
                # Validate appointment date/period constraints
                validation_error = self._validate_appointment_datetime(appointment_date, period)
                if validation_error:
                    return JsonResponse({'success': False, 'error': validation_error}, status=400)
                
                # Check slot availability
                can_book, availability_message = Appointment.can_book_appointment(appointment_date, period)
                if not can_book:
                    return JsonResponse({'success': False, 'error': availability_message}, status=400)
                
                # Handle patient data - UPDATED to store in temp fields
                patient_data, patient_type = self._prepare_patient_data(data)
                if isinstance(patient_data, JsonResponse):  # Error response
                    return patient_data
                
                # Create appointment with temp patient data
                appointment = Appointment.objects.create(
                    patient=patient_data.get('existing_patient'),
                    service=service,
                    appointment_date=appointment_date,
                    period=period,
                    patient_type=patient_type,
                    reason=data.get('reason', '').strip(),
                    status='pending',
                    temp_first_name=patient_data.get('first_name', ''),
                    temp_last_name=patient_data.get('last_name', ''),
                    temp_email=patient_data.get('email', ''),
                    temp_contact_number=patient_data.get('contact_number', ''),
                    temp_address=patient_data.get('address', ''),
                )
                
                # Skip automatic audit log for public bookings
                # (We don't want anonymous bookings cluttering the audit log)
                # Staff will see it in the "Pending Requests" page
                # When they approve it, that action will be logged
                
                # Generate reference number
                reference_number = f'APT-{appointment.id:06d}'
                
                return JsonResponse({
                    'success': True,
                    'reference_number': reference_number,
                    'appointment_id': appointment.id,
                    'appointment_date': appointment_date.strftime('%Y-%m-%d'),
                    'period': period,
                    'period_display': 'Morning' if period == 'AM' else 'Afternoon',
                    'patient_name': appointment.patient_name
                })
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Error in _handle_json_request: {str(e)}', exc_info=True)
            
            return JsonResponse({
                'success': False, 
                'error': 'An error occurred while processing your request. Please try again.'
            }, status=500)
        
    def _prepare_patient_data(self, data):
        """Prepare patient data for temp storage - UPDATED logic"""
        patient_type_raw = data['patient_type']
        
        if patient_type_raw == 'new':
            return self._prepare_new_patient_data(data)
        elif patient_type_raw == 'existing':
            return self._prepare_existing_patient_data(data)
        else:
            return JsonResponse({'success': False, 'error': 'Invalid patient type'}, status=400), None

    def _prepare_new_patient_data(self, data):
        """Prepare new patient data for temp storage"""
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
        try:
            validate_email(email)
        except DjangoValidationError:
            return JsonResponse({
                'success': False,
                'error': 'Please enter a valid email address'
            }, status=400), None
        
        # Validate contact number if provided
        if contact_number:
            phone_pattern = re.compile(r'^(\+63|0)?9\d{9}$')
            clean_contact = contact_number.replace(' ', '').replace('-', '')
            if not phone_pattern.match(clean_contact):
                return JsonResponse({
                    'success': False,
                    'error': 'Please enter a valid Philippine mobile number (e.g., +639123456789)'
                }, status=400), None
            contact_number = clean_contact
        
        return {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'contact_number': contact_number,
            'address': address,
            'existing_patient': None  # No existing patient to link
        }, 'new'

    def _prepare_existing_patient_data(self, data):
        """Prepare existing patient data - find and link existing patient"""
        identifier = data.get('patient_identifier', '').strip()
        if not identifier:
            return JsonResponse({'success': False, 'error': 'Patient identifier is required'}, status=400), None
        
        # Search logic
        query = Q(is_active=True)
        if '@' in identifier:
            query &= Q(email__iexact=identifier)
        else:
            clean_identifier = identifier.replace(' ', '').replace('-', '')
            query &= (Q(contact_number=identifier) | Q(contact_number=clean_identifier))
        
        patient = Patient.objects.filter(query).first()
        
        if not patient:
            return JsonResponse({
                'success': False, 
                'error': 'No patient found with the provided information. Please check your details or register as a new patient.'
            }, status=400), None
        
        # For existing patients, we still store temp data in case there are updates
        # but we also link to the existing patient record
        return {
            'first_name': patient.first_name,
            'last_name': patient.last_name,
            'email': patient.email,
            'contact_number': patient.contact_number,
            'address': patient.address,
            'existing_patient': patient  # Link to existing patient
        }, 'returning'
    
    def _validate_appointment_datetime(self, appointment_date, period):
        """Validate appointment date and period constraints - SIMPLIFIED (removed holiday check)"""
        # Check past dates
        if appointment_date <= timezone.now().date():
            return 'Appointment date must be in the future'
        
        # Check Sundays
        if appointment_date.weekday() == 6:  # Sunday
            return 'Appointments are not available on Sundays'
        
        # Basic period validation
        if period not in ['AM', 'PM']:
            return 'Invalid period selected'
        
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
        try:
            validate_email(email)
        except DjangoValidationError:
            return JsonResponse({
                'success': False,
                'error': 'Please enter a valid email address'
            }, status=400), None
        
        # Validate contact number if provided
        if contact_number:
            phone_pattern = re.compile(r'^(\+63|0)?9\d{9}$')
            clean_contact = contact_number.replace(' ', '').replace('-', '')
            if not phone_pattern.match(clean_contact):
                return JsonResponse({
                    'success': False,
                    'error': 'Please enter a valid Philippine mobile number (e.g., +639123456789)'
                }, status=400), None
            contact_number = clean_contact
        
        # Check for existing patient
        existing_query = Q()
        if email:
            existing_query |= Q(email__iexact=email, is_active=True)
        if contact_number:
            existing_query |= Q(contact_number=contact_number, is_active=True)
        
        if existing_query:
            existing = Patient.objects.filter(existing_query).first()
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
            contact_number=contact_number or '',
            address=address,
        )
        
        return patient, 'new'
    
    def _find_existing_patient(self, data):
        """Find existing patient with validation"""
        identifier = data.get('patient_identifier', '').strip()
        if not identifier:
            return JsonResponse({'success': False, 'error': 'Patient identifier is required'}, status=400), None
        
        # Search logic
        query = Q(is_active=True)
        if '@' in identifier:
            query &= Q(email__iexact=identifier)
        else:
            clean_identifier = identifier.replace(' ', '').replace('-', '')
            query &= (Q(contact_number=identifier) | Q(contact_number=clean_identifier))
        
        patient = Patient.objects.filter(query).first()
        
        if not patient:
            return JsonResponse({
                'success': False, 
                'error': 'No patient found with the provided information. Please check your details or register as a new patient.'
            }, status=400), None
        
        return patient, 'returning'
    
    def _handle_form_request(self, request):
        """Handle regular form submission (fallback)"""
        messages.info(request, 'Please use the appointment booking form.')
        return redirect('core:book_appointment')


# Add new API endpoints for AM/PM slot availability
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt


@require_http_methods(["GET"])
def get_slot_availability_api(request):
    """
    API ENDPOINT: Get AM/PM slot availability for date range
    Used by the booking calendar
    """
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date', start_date_str)  # Default to same date if not provided
    
    if not start_date_str:
        return JsonResponse({'error': 'start_date is required'}, status=400)
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
    
    # Validate date range
    today = timezone.now().date()
    if start_date <= today:
        return JsonResponse({'error': 'Start date must be in the future'}, status=400)
    
    if end_date < start_date:
        return JsonResponse({'error': 'End date must be after start date'}, status=400)
    
    # Limit range to prevent excessive queries
    if (end_date - start_date).days > 90:
        return JsonResponse({'error': 'Date range too large. Maximum 90 days.'}, status=400)
    
    # Get availability for date range
    availability = DailySlots.get_availability_for_range(start_date, end_date)
    
    # Format for frontend
    formatted_availability = {}
    for date_obj, slots in availability.items():
        date_str = date_obj.strftime('%Y-%m-%d')
        
        # Skip Sundays and past dates
        if date_obj.weekday() == 6 or date_obj <= today:
            continue
        
        formatted_availability[date_str] = {
            'date': date_str,
            'weekday': date_obj.strftime('%A'),
            'am_slots': {
                'available': slots['am_available'],
                'total': slots['am_total'],
                'is_available': slots['am_available'] > 0
            },
            'pm_slots': {
                'available': slots['pm_available'],
                'total': slots['pm_total'],
                'is_available': slots['pm_available'] > 0
            },
            'has_availability': (slots['am_available'] > 0 or slots['pm_available'] > 0)
        }
    
    return JsonResponse({
        'availability': formatted_availability,
        'date_range': {
            'start': start_date_str,
            'end': end_date_str
        }
    })


@require_http_methods(["GET"])
def find_patient_api(request):
    """
    API ENDPOINT: Find existing patient by email or contact number
    """
    identifier = request.GET.get('identifier', '').strip()
    if not identifier or len(identifier) < 3:
        return JsonResponse({'found': False})
    
    # Search logic
    query = Q(is_active=True)
    
    if '@' in identifier:
        query &= Q(email__iexact=identifier)
    else:
        # Handle contact number with flexible formatting
        clean_identifier = identifier.replace(' ', '').replace('-', '').replace('+', '')
        query &= (
            Q(contact_number=identifier) | 
            Q(contact_number=clean_identifier) |
            (Q(contact_number__endswith=clean_identifier[-10:]) if len(clean_identifier) >= 10 else Q())
        )
    
    patient = Patient.objects.filter(query).first()
    
    if patient:
        return JsonResponse({
            'found': True,
            'patient': {
                'id': patient.id,
                'name': patient.full_name,
                'email': patient.email or '',
                'contact_number': patient.contact_number or ''
            }
        })
    else:
        return JsonResponse({'found': False})

class DashboardView(LoginRequiredMixin, TemplateView):
    """Main dashboard for authenticated users - UPDATED for AM/PM system with Manila timezone"""
    template_name = 'core/dashboard.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get today's date in Manila timezone
        manila_tz = pytz.timezone('Asia/Manila')
        manila_now = timezone.now().astimezone(manila_tz)
        today = manila_now.date()
        
        # Today's appointments - Use BLOCKING_STATUSES for consistency
        todays_appointments = Appointment.objects.filter(
            appointment_date=today,
            status__in=Appointment.BLOCKING_STATUSES
        ).select_related('patient', 'assigned_dentist', 'service').order_by('period', 'requested_at')
        
        context['todays_appointments'] = todays_appointments
        
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
            'todays_appointments_count': todays_appointments.count(),
            'pending_requests_count': context['pending_requests'],
            'active_dentists': User.objects.filter(is_active_dentist=True).count(),
        }
        
        # Today's slot availability summary with percentage calculations
        try:
            daily_slots = DailySlots.objects.get(date=today)
            
            # Calculate availability
            am_available = daily_slots.get_available_am_slots()
            am_total = daily_slots.am_slots
            pm_available = daily_slots.get_available_pm_slots()
            pm_total = daily_slots.pm_slots
            
            # Calculate percentages
            am_percentage = (am_available / am_total * 100) if am_total > 0 else 0
            pm_percentage = (pm_available / pm_total * 100) if pm_total > 0 else 0
            
            context['todays_slot_summary'] = {
                'am_available': am_available,
                'am_total': am_total,
                'am_percentage': round(am_percentage, 1),
                'pm_available': pm_available,
                'pm_total': pm_total,
                'pm_percentage': round(pm_percentage, 1),
            }
            
        except DailySlots.DoesNotExist:
            # Try to create default slots for today
            daily_slots, created = DailySlots.get_or_create_for_date(today)
            if daily_slots:
                am_available = daily_slots.get_available_am_slots()
                am_total = daily_slots.am_slots
                pm_available = daily_slots.get_available_pm_slots()
                pm_total = daily_slots.pm_slots
                
                am_percentage = (am_available / am_total * 100) if am_total > 0 else 0
                pm_percentage = (pm_available / pm_total * 100) if pm_total > 0 else 0
                
                context['todays_slot_summary'] = {
                    'am_available': am_available,
                    'am_total': am_total,
                    'am_percentage': round(am_percentage, 1),
                    'pm_available': pm_available,
                    'pm_total': pm_total,
                    'pm_percentage': round(pm_percentage, 1),
                }
            else:
                context['todays_slot_summary'] = {
                    'am_available': 0,
                    'am_total': 0,
                    'am_percentage': 0,
                    'pm_available': 0,
                    'pm_total': 0,
                    'pm_percentage': 0,
                }
        
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
                {'name': 'System Settings', 'url': 'core:system_settings', 'icon': 'settings'},
            ])
        
        return actions

class AuditLogListView(LoginRequiredMixin, ListView):
    """Enhanced view for audit logs with comprehensive filtering"""
    model = AuditLog
    template_name = 'core/audit_log_list.html'
    context_object_name = 'logs'
    paginate_by = 50
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = AuditLog.objects.select_related('user').order_by('-timestamp')
        
        # Build active filters list for display
        self.active_filters = []
        
        # Filter by user
        user_filter = self.request.GET.get('user')
        if user_filter:
            try:
                user_id = int(user_filter)
                queryset = queryset.filter(user_id=user_id)
                user = User.objects.get(id=user_id)
                self.active_filters.append(f"User: {user.get_full_name()}")
            except (ValueError, User.DoesNotExist):
                pass
        
        # Filter by action
        action_filter = self.request.GET.get('action')
        if action_filter:
            queryset = queryset.filter(action=action_filter)
            action_display = dict(AuditLog.ACTION_CHOICES).get(action_filter, action_filter)
            self.active_filters.append(f"Action: {action_display}")
        
        # Filter by model name
        model_filter = self.request.GET.get('model_name')
        if model_filter:
            queryset = queryset.filter(model_name=model_filter)
            self.active_filters.append(f"Module: {model_filter.title()}")
        
        # Filter by date range
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__gte=date_from_obj)
                self.active_filters.append(f"From: {date_from_obj.strftime('%b %d, %Y')}")
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__date__lte=date_to_obj)
                self.active_filters.append(f"To: {date_to_obj.strftime('%b %d, %Y')}")
            except ValueError:
                pass
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get all users for filter dropdown
        context['users'] = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
        
        # Action choices
        context['action_choices'] = AuditLog.ACTION_CHOICES
        
        # Get unique model names for filter
        context['model_choices'] = AuditLog.objects.values_list('model_name', flat=True).distinct().order_by('model_name')
        
        # Current filters
        context['filters'] = {
            'user': self.request.GET.get('user', ''),
            'action': self.request.GET.get('action', ''),
            'model_name': self.request.GET.get('model_name', ''),
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }
        
        # Active filters for display
        context['active_filters'] = getattr(self, 'active_filters', [])
        
        # Total count
        context['total_count'] = self.get_queryset().count()
        
        return context

class MaintenanceHubView(LoginRequiredMixin, TemplateView):
    """Maintenance hub for admin functions"""
    template_name = 'core/maintenance_hub.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['stats'] = {
            'users_count': User.objects.count(),
            'services_count': Service.objects.count(),
            'patients_count': Patient.objects.count(),
            'appointments_count': Appointment.objects.count(),
        }
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