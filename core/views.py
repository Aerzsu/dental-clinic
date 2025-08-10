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

from .models import AuditLog, Holiday, SystemSetting
from appointments.models import Appointment, Schedule
from patients.models import Patient
from services.models import Service
from users.models import User
from appointments.forms import AppointmentRequestForm

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
    """Public appointment booking form"""
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
        """Handle appointment request submission"""
        try:
            # Check if request is JSON
            if request.content_type == 'application/json':
                data = json.loads(request.body)
                
                # Validate required fields
                required_fields = ['patient_type', 'service', 'dentist', 'selected_date', 'selected_time']
                for field in required_fields:
                    if not data.get(field):
                        return JsonResponse({'success': False, 'error': f'{field} is required'}, status=400)
                
                # Handle patient creation/finding
                if data['patient_type'] == 'new':
                    # Updated validation: email required, contact_number optional
                    if not all([data.get('first_name'), data.get('last_name'), data.get('email')]):
                        return JsonResponse({
                            'success': False, 
                            'error': 'First name, last name, and email are required for new patients'
                        }, status=400)
                    
                    # Check for existing patient - fix validation logic
                    email = data.get('email', '').strip()
                    contact_number = data.get('contact_number', '').strip()
                    
                    # Build query for existing patient check
                    existing_query = Q()
                    if email:
                        existing_query |= Q(email__iexact=email)
                    if contact_number:
                        existing_query |= Q(contact_number=contact_number)
                    
                    if existing_query:  # Only check if we have something to search for
                        existing = Patient.objects.filter(existing_query, is_active=True).first()
                        
                        if existing:
                            return JsonResponse({
                                'success': False, 
                                'error': 'A patient with this email or contact number already exists. Please use "Existing Patient" option.'
                            }, status=400)
                    
                    # Create new patient
                    patient = Patient.objects.create(
                        first_name=data.get('first_name', ''),
                        last_name=data.get('last_name', ''),
                        email=email,
                        contact_number=contact_number,
                        address=data.get('address', ''),
                    )
                    patient_type = 'new'
                    
                else:  # existing patient
                    identifier = data.get('patient_identifier', '').strip()
                    if not identifier:
                        return JsonResponse({'success': False, 'error': 'Patient identifier is required'}, status=400)
                    
                    # Find existing patient - fix search logic
                    patient = Patient.objects.filter(
                        Q(email__iexact=identifier) | Q(contact_number=identifier),
                        is_active=True
                    ).first()
                    
                    if not patient:
                        return JsonResponse({
                            'success': False, 
                            'error': 'No patient found with the provided information'
                        }, status=400)
                    
                    patient_type = 'returning'
                
                # Get service and dentist
                try:
                    service = Service.objects.get(id=data['service'], is_archived=False)
                    dentist = User.objects.get(id=data['dentist'], is_active_dentist=True)
                except (Service.DoesNotExist, User.DoesNotExist):
                    return JsonResponse({'success': False, 'error': 'Invalid service or dentist'}, status=400)
                
                # Parse date and time - fix timezone handling
                try:
                    appointment_date = datetime.strptime(data['selected_date'], '%Y-%m-%d').date()
                    appointment_time = datetime.strptime(data['selected_time'], '%H:%M').time()
                except ValueError:
                    return JsonResponse({'success': False, 'error': 'Invalid date or time format'}, status=400)
                
                # Validate appointment date
                if appointment_date <= timezone.now().date():
                    return JsonResponse({'success': False, 'error': 'Appointment date must be in the future'}, status=400)
                
                if appointment_date.weekday() == 6:  # Sunday
                    return JsonResponse({'success': False, 'error': 'Appointments are not available on Sundays'}, status=400)
                
                # Calculate end time based on service duration
                start_datetime = datetime.combine(appointment_date, appointment_time)
                end_time = (start_datetime + timedelta(minutes=service.duration_minutes)).time()
                
                # Create or get schedule
                schedule, created = Schedule.objects.get_or_create(
                    dentist=dentist,
                    date=appointment_date,
                    start_time=appointment_time,
                    defaults={
                        'end_time': end_time,
                        'is_available': True,
                        'notes': 'Auto-created for online appointment request'
                    }
                )
                
                # Check for conflicts
                existing_appointment = Appointment.objects.filter(
                    schedule=schedule,
                    status__in=['approved', 'pending']
                ).first()
                
                if existing_appointment:
                    return JsonResponse({'success': False, 'error': 'This time slot is already booked'}, status=400)
                
                # Create appointment
                appointment = Appointment.objects.create(
                    patient=patient,
                    dentist=dentist,
                    service=service,
                    schedule=schedule,
                    patient_type=patient_type,
                    reason=data.get('reason', ''),
                    status='pending'
                )
                
                # Generate reference number
                reference_number = f'APT-{appointment.id:06d}'
                
                return JsonResponse({
                    'success': True,
                    'reference_number': reference_number,
                    'appointment_id': appointment.id
                })
                
            else:
                # Handle regular form submission (fallback)
                form = AppointmentRequestForm(request.POST)
                if form.is_valid():
                    appointment = form.save()
                    messages.success(
                        request,
                        'Your appointment request has been submitted successfully! '
                        'We will contact you soon to confirm your appointment.'
                    )
                    return redirect('core:home')
                else:
                    context = self.get_context_data(**kwargs)
                    context['form'] = form
                    return render(request, self.template_name, context)
                    
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