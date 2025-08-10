#appointments/views.py
# Standard library imports
import json
from datetime import datetime, date, timedelta, time

# Django core imports
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db.models import Q, Count
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView

# Local app imports
from .models import Appointment, Schedule
from .forms import AppointmentForm, ScheduleForm, AppointmentRequestForm
from patients.models import Patient
from services.models import Service
from users.models import User
from core.models import Holiday, SystemSetting

class AppointmentCalendarView(LoginRequiredMixin, TemplateView):
    """Calendar view for appointments"""
    template_name = 'appointments/appointment_calendar.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get current month or requested month
        today = timezone.now().date()
        month = int(self.request.GET.get('month', today.month))
        year = int(self.request.GET.get('year', today.year))
        
        # Get appointments for the month
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)
        
        appointments = Appointment.objects.filter(
            schedule__date__gte=start_date,
            schedule__date__lt=end_date,
            status__in=['approved', 'pending', 'completed']
        ).select_related('patient', 'dentist', 'service', 'schedule').order_by('schedule__date', 'schedule__start_time')
        
        # Group appointments by date
        appointments_by_date = {}
        for appointment in appointments:
            date_key = appointment.schedule.date.strftime('%Y-%m-%d')
            if date_key not in appointments_by_date:
                appointments_by_date[date_key] = []
            appointments_by_date[date_key].append(appointment)
        
        # get pending appointment count for notification badge
        pending_count = Appointment.objects.filter(status='pending').count()

        context.update({
            'current_month': month,
            'current_year': year,
            'appointments_by_date': json.dumps(appointments_by_date, default=str),
            'dentists': User.objects.filter(is_active_dentist=True),
            'today': today.strftime('%Y-%m-%d'),
            'pending_count': pending_count,
        })
        
        return context


    
class AppointmentRequestsView(LoginRequiredMixin, ListView):
    """View appointment requests with enhanced filtering and bulk actions"""
    model = Appointment
    template_name = 'appointments/appointment_requests.html'
    context_object_name = 'appointments'
    paginate_by = 15
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Appointment.objects.filter(
            status='pending'
        ).select_related('patient', 'dentist', 'service', 'schedule').order_by('-requested_at')
        
        # Filter by patient type
        patient_type = self.request.GET.get('patient_type')
        if patient_type:
            queryset = queryset.filter(patient_type=patient_type)
        
        # Filter by dentist
        dentist = self.request.GET.get('dentist')
        if dentist:
            queryset = queryset.filter(dentist_id=dentist)
        
        # Filter by date range
        date_from = self.request.GET.get('date_from')
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(schedule__date__gte=date_from)
            except ValueError:
                pass
        
        date_to = self.request.GET.get('date_to')
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(schedule__date__lte=date_to)
            except ValueError:
                pass
        
        # Search by patient name
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__email__icontains=search) |
                Q(patient__contact_number__icontains=search)
            )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'pending_count': self.get_queryset().count(),
            'patient_types': [
                ('new', 'New Patients'),
                ('returning', 'Returning Patients')
            ],
            'dentists': User.objects.filter(is_active_dentist=True),
            'filters': {
                'patient_type': self.request.GET.get('patient_type', ''),
                'dentist': self.request.GET.get('dentist', ''),
                'date_from': self.request.GET.get('date_from', ''),
                'date_to': self.request.GET.get('date_to', ''),
                'search': self.request.GET.get('search', ''),
            }
        })
        return context

class AppointmentListView(LoginRequiredMixin, ListView):
    """List all appointments with filtering"""
    model = Appointment
    template_name = 'appointments/appointment_list.html'
    context_object_name = 'appointments'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Appointment.objects.select_related(
            'patient', 'dentist', 'service', 'schedule'
        )
        
        # Filter by status
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Filter by dentist
        dentist = self.request.GET.get('dentist')
        if dentist:
            queryset = queryset.filter(dentist_id=dentist)
        
        # Filter by date range
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(schedule__date__gte=date_from)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(schedule__date__lte=date_to)
            except ValueError:
                pass
        
        # Search by patient name
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search)
            )
        
        return queryset.order_by('-schedule__date', '-schedule__start_time')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'status_choices': Appointment.STATUS_CHOICES,
            'dentists': User.objects.filter(is_active_dentist=True),
            'filters': {
                'status': self.request.GET.get('status', ''),
                'dentist': self.request.GET.get('dentist', ''),
                'date_from': self.request.GET.get('date_from', ''),
                'date_to': self.request.GET.get('date_to', ''),
                'search': self.request.GET.get('search', ''),
            }
        })
        return context

class AppointmentCreateView(LoginRequiredMixin, CreateView):
    """Create new appointment"""
    model = Appointment
    form_class = AppointmentForm
    template_name = 'appointments/appointment_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        # Auto-approve if user has permission and it's a staff booking
        if self.request.user.has_permission('appointments'):
            form.instance.status = 'approved'
            form.instance.approved_at = timezone.now()
            form.instance.approved_by = self.request.user
        
        messages.success(
            self.request, 
            f'Appointment for {form.instance.patient.full_name} created successfully.'
        )
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('appointments:appointment_list')

class AppointmentDetailView(LoginRequiredMixin, DetailView):
    """View appointment details"""
    model = Appointment
    template_name = 'appointments/appointment_detail.html'
    context_object_name = 'appointment'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)

class AppointmentUpdateView(LoginRequiredMixin, UpdateView):
    """Update appointment"""
    model = Appointment
    form_class = AppointmentForm
    template_name = 'appointments/appointment_form.html'
    context_object_name = 'appointment'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs
    
    def form_valid(self, form):
        messages.success(
            self.request,
            f'Appointment for {form.instance.patient.full_name} updated successfully.'
        )
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('appointments:appointment_detail', kwargs={'pk': self.object.pk})

@login_required
def approve_appointment(request, pk):
    """Approve an appointment request"""
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    appointment = get_object_or_404(Appointment, pk=pk)
    
    if appointment.status != 'pending':
        messages.error(request, 'Only pending appointments can be approved.')
        return redirect('appointments:appointment_detail', pk=pk)
    
    appointment.approve(request.user)
    messages.success(request, f'Appointment for {appointment.patient.full_name} has been approved.')
    
    return redirect('appointments:appointment_detail', pk=pk)

@login_required
def reject_appointment(request, pk):
    """Reject an appointment request"""
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    appointment = get_object_or_404(Appointment, pk=pk)
    
    if appointment.status != 'pending':
        messages.error(request, 'Only pending appointments can be rejected.')
        return redirect('appointments:appointment_detail', pk=pk)
    
    appointment.reject()
    messages.success(request, f'Appointment for {appointment.patient.full_name} has been rejected.')
    
    return redirect('appointments:appointment_requests')

@login_required
def cancel_appointment(request, pk):
    """Cancel an appointment"""
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    appointment = get_object_or_404(Appointment, pk=pk)
    
    if not appointment.can_be_cancelled:
        messages.error(request, 'This appointment cannot be cancelled.')
        return redirect('appointments:appointment_detail', pk=pk)
    
    appointment.cancel()
    messages.success(request, f'Appointment for {appointment.patient.full_name} has been cancelled.')
    
    return redirect('appointments:appointment_detail', pk=pk)

@login_required
def complete_appointment(request, pk):
    """Mark appointment as completed"""
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    appointment = get_object_or_404(Appointment, pk=pk)
    
    if appointment.status != 'approved':
        messages.error(request, 'Only approved appointments can be marked as completed.')
        return redirect('appointments:appointment_detail', pk=pk)
    
    appointment.complete()
    messages.success(request, f'Appointment for {appointment.patient.full_name} has been marked as completed.')
    
    return redirect('appointments:appointment_detail', pk=pk)

# Schedule Management Views
class ScheduleListView(LoginRequiredMixin, ListView):
    """List dentist schedules"""
    model = Schedule
    template_name = 'appointments/schedule_list.html'
    context_object_name = 'schedules'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Schedule.objects.select_related('dentist')
        
        # Filter by dentist
        dentist = self.request.GET.get('dentist')
        if dentist:
            queryset = queryset.filter(dentist_id=dentist)
        
        # Filter by date range
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(date__gte=date_from)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(date__lte=date_to)
            except ValueError:
                pass
        
        return queryset.order_by('-date', 'start_time')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'dentists': User.objects.filter(is_active_dentist=True),
            'filters': {
                'dentist': self.request.GET.get('dentist', ''),
                'date_from': self.request.GET.get('date_from', ''),
                'date_to': self.request.GET.get('date_to', ''),
            }
        })
        return context

class ScheduleCreateView(LoginRequiredMixin, CreateView):
    """Create new schedule"""
    model = Schedule
    form_class = ScheduleForm
    template_name = 'appointments/schedule_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, 'Schedule created successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('appointments:schedule_list')

# AJAX endpoints for appointment booking
@login_required
def get_available_dates(request):
    """Get available dates for appointment booking"""
    dentist_id = request.GET.get('dentist_id')
    service_id = request.GET.get('service_id')
    
    if not dentist_id or not service_id:
        return JsonResponse({'error': 'Missing required parameters'}, status=400)
    
    try:
        dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
        service = Service.objects.get(id=service_id, is_archived=False)
    except (User.DoesNotExist, Service.DoesNotExist):
        return JsonResponse({'error': 'Invalid dentist or service'}, status=400)
    
    # Get available dates (next 30 days, excluding Sundays and holidays)
    available_dates = []
    start_date = timezone.now().date() + timedelta(days=1)  # Start from tomorrow
    
    for i in range(30):
        check_date = start_date + timedelta(days=i)
        
        # Skip Sundays (weekday 6)
        if check_date.weekday() == 6:
            continue
        
        # Skip holidays
        if Holiday.objects.filter(date=check_date, is_active=True).exists():
            continue
        
        # Check if dentist has availability
        schedules = Schedule.objects.filter(
            dentist=dentist,
            date=check_date,
            is_available=True
        )
        
        if schedules.exists():
            available_dates.append(check_date.strftime('%Y-%m-%d'))
    
    return JsonResponse({'available_dates': available_dates})

@login_required
def get_available_times(request):
    """Get available times for a specific date and dentist"""
    dentist_id = request.GET.get('dentist_id')
    date_str = request.GET.get('date')
    service_id = request.GET.get('service_id')
    
    if not all([dentist_id, date_str, service_id]):
        return JsonResponse({'error': 'Missing required parameters'}, status=400)
    
    try:
        dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
        service = Service.objects.get(id=service_id, is_archived=False)
        appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (User.DoesNotExist, Service.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    
    # Get dentist's schedule for the date
    schedules = Schedule.objects.filter(
        dentist=dentist,
        date=appointment_date,
        is_available=True
    ).order_by('start_time')
    
    if not schedules.exists():
        return JsonResponse({'available_times': []})
    
    # Get existing appointments for the date
    existing_appointments = Appointment.objects.filter(
        dentist=dentist,
        schedule__date=appointment_date,
        status__in=['approved', 'pending']
    ).values_list('schedule__start_time', 'schedule__end_time')
    
    available_times = []
    service_duration = timedelta(minutes=service.duration_minutes)
    
    for schedule in schedules:
        # Generate time slots within the schedule
        current_time = datetime.combine(appointment_date, schedule.start_time)
        end_time = datetime.combine(appointment_date, schedule.end_time)
        
        while current_time + service_duration <= end_time:
            slot_start = current_time.time()
            slot_end = (current_time + service_duration).time()
            
            # Check if this time slot conflicts with existing appointments
            conflicts = any(
                slot_start < apt_end and slot_end > apt_start
                for apt_start, apt_end in existing_appointments
            )
            
            if not conflicts:
                available_times.append(slot_start.strftime('%H:%M'))
            
            # Move to next 30-minute slot
            current_time += timedelta(minutes=30)
    
    return JsonResponse({'available_times': available_times})

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
                    # Create new patient
                    if not all([data.get('first_name'), data.get('last_name'), data.get('contact_number')]):
                        return JsonResponse({
                            'success': False, 
                            'error': 'First name, last name, and contact number are required for new patients'
                        }, status=400)
                    
                    # Check for existing patient
                    existing = Patient.objects.filter(
                        Q(email__iexact=data.get('email', '')) | Q(contact_number=data.get('contact_number', '')),
                        is_active=True
                    ).first()
                    
                    if existing:
                        return JsonResponse({
                            'success': False, 
                            'error': 'A patient with this email or contact number already exists'
                        }, status=400)
                    
                    patient = Patient.objects.create(
                        first_name=data.get('first_name', ''),
                        last_name=data.get('last_name', ''),
                        email=data.get('email', ''),
                        contact_number=data.get('contact_number', ''),
                        address=data.get('address', ''),
                    )
                    patient_type = 'new'
                    
                else:  # existing patient
                    identifier = data.get('patient_identifier', '')
                    if not identifier:
                        return JsonResponse({'success': False, 'error': 'Patient identifier is required'}, status=400)
                    
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
                
                # Parse date and time
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

# API endpoints for AJAX calls
def get_available_dates_api(request):
    """API endpoint to get available dates for appointment booking"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    dentist_id = request.GET.get('dentist_id')
    service_id = request.GET.get('service_id')
    
    if not dentist_id or not service_id:
        return JsonResponse({'error': 'dentist_id and service_id are required'}, status=400)
    
    try:
        dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
        service = Service.objects.get(id=service_id, is_archived=False)
    except (User.DoesNotExist, Service.DoesNotExist):
        return JsonResponse({'error': 'Invalid dentist or service'}, status=400)
    
    # Get available dates for the next 60 days
    available_dates = []
    start_date = timezone.now().date() + timedelta(days=1)  # Start from tomorrow
    
    # Get holidays
    holidays = set(Holiday.objects.filter(
        date__gte=start_date,
        date__lt=start_date + timedelta(days=60),
        is_active=True
    ).values_list('date', flat=True))
    
    # Get existing schedules for the dentist
    existing_schedules = set(Schedule.objects.filter(
        dentist=dentist,
        date__gte=start_date,
        date__lt=start_date + timedelta(days=60),
        is_available=True
    ).values_list('date', flat=True))
    
    for i in range(60):  # Next 60 days
        check_date = start_date + timedelta(days=i)
        
        # Skip Sundays (weekday 6)
        if check_date.weekday() == 6:
            continue
        
        # Skip holidays
        if check_date in holidays:
            continue
        
        # For now, include all weekdays (Monday-Saturday) as potentially available
        # In a real system, you'd check dentist's actual schedule/availability
        available_dates.append(check_date.strftime('%Y-%m-%d'))
    
    return JsonResponse({'available_dates': available_dates})

def get_available_times_api(request):
    """API endpoint to get available times for a specific date and dentist"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    dentist_id = request.GET.get('dentist_id')
    date_str = request.GET.get('date')
    service_id = request.GET.get('service_id')
    
    if not all([dentist_id, date_str, service_id]):
        return JsonResponse({'error': 'dentist_id, date, and service_id are required'}, status=400)
    
    try:
        dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
        service = Service.objects.get(id=service_id, is_archived=False)
        appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (User.DoesNotExist, Service.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    
    # Get clinic operating hours (can be made configurable via SystemSetting)
    clinic_start = time(10, 0)  # 10:00 AM
    clinic_end = time(18, 0)    # 6:00 PM
    lunch_start = time(12, 0)   # 12:00 PM
    lunch_end = time(13, 0)     # 1:00 PM
    
    # Get existing appointments for the date
    existing_appointments = Appointment.objects.filter(
        dentist=dentist,
        schedule__date=appointment_date,
        status__in=['approved', 'pending']
    ).select_related('schedule').values('schedule__start_time', 'schedule__end_time')
    
    # Generate available time slots
    available_times = []
    service_duration = timedelta(minutes=service.duration_minutes)
    slot_duration = timedelta(minutes=30)  # 30-minute slots
    
    # Start from clinic opening time
    current_time = datetime.combine(appointment_date, clinic_start)
    end_of_day = datetime.combine(appointment_date, clinic_end)
    
    while current_time + service_duration <= end_of_day:
        slot_start_time = current_time.time()
        slot_end_time = (current_time + service_duration).time()
        
        # Skip lunch break
        if not (slot_end_time <= lunch_start or slot_start_time >= lunch_end):
            current_time += slot_duration
            continue
        
        # Check for conflicts with existing appointments
        conflicts = any(
            slot_start_time < apt['schedule__end_time'] and slot_end_time > apt['schedule__start_time']
            for apt in existing_appointments
        )
        
        if not conflicts:
            available_times.append(slot_start_time.strftime('%H:%M'))
        
        current_time += slot_duration
    
    return JsonResponse({'available_times': available_times})

def find_patient_api(request):
    """API endpoint to find existing patient by identifier"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    identifier = request.GET.get('identifier', '').strip()
    if not identifier:
        return JsonResponse({'error': 'Identifier is required'}, status=400)
    
    # Search for patient by email or contact number
    # Fix: Handle cases where fields might be empty
    query = Q()
    
    # Only add email filter if patient has an email
    query |= Q(email__iexact=identifier, email__isnull=False) & ~Q(email='')
    
    # Only add contact filter if patient has a contact number  
    query |= Q(contact_number=identifier, contact_number__isnull=False) & ~Q(contact_number='')
    
    patient = Patient.objects.filter(query, is_active=True).first()
    
    if patient:
        return JsonResponse({
            'found': True,
            'patient': {
                'id': patient.id,
                'name': patient.full_name,
                'email': patient.email,
                'contact_number': patient.contact_number
            }
        })
    else:
        return JsonResponse({'found': False})

# Enhanced schedule management
class ScheduleBulkCreateView(LoginRequiredMixin, TemplateView):
    """Bulk create schedules for dentists"""
    template_name = 'appointments/schedule_bulk_create.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['dentists'] = User.objects.filter(is_active_dentist=True)
        return context
    
    def post(self, request, *args, **kwargs):
        try:
            data = request.POST
            dentist_id = data.get('dentist')
            start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
            
            # Get selected days of week (0=Monday, 6=Sunday)
            selected_days = [int(day) for day in data.getlist('days_of_week')]
            
            # Get time slots
            morning_start = data.get('morning_start')
            morning_end = data.get('morning_end')
            afternoon_start = data.get('afternoon_start')
            afternoon_end = data.get('afternoon_end')
            
            dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
            
            created_count = 0
            current_date = start_date
            
            while current_date <= end_date:
                # Check if this day of week is selected
                if current_date.weekday() in selected_days:
                    # Check if it's not a holiday
                    if not Holiday.objects.filter(date=current_date, is_active=True).exists():
                        # Create morning schedule if specified
                        if morning_start and morning_end:
                            schedule, created = Schedule.objects.get_or_create(
                                dentist=dentist,
                                date=current_date,
                                start_time=datetime.strptime(morning_start, '%H:%M').time(),
                                defaults={
                                    'end_time': datetime.strptime(morning_end, '%H:%M').time(),
                                    'is_available': True,
                                    'notes': 'Bulk created morning schedule'
                                }
                            )
                            if created:
                                created_count += 1
                        
                        # Create afternoon schedule if specified
                        if afternoon_start and afternoon_end:
                            schedule, created = Schedule.objects.get_or_create(
                                dentist=dentist,
                                date=current_date,
                                start_time=datetime.strptime(afternoon_start, '%H:%M').time(),
                                defaults={
                                    'end_time': datetime.strptime(afternoon_end, '%H:%M').time(),
                                    'is_available': True,
                                    'notes': 'Bulk created afternoon schedule'
                                }
                            )
                            if created:
                                created_count += 1
                
                current_date += timedelta(days=1)
            
            messages.success(request, f'Successfully created {created_count} schedule(s).')
            return redirect('appointments:schedule_list')
            
        except Exception as e:
            messages.error(request, f'Error creating schedules: {str(e)}')
            return self.get(request, *args, **kwargs)


# Updated core/views.py - Add this to your existing core views
class BookAppointmentPublicView(TemplateView):
    """Public-facing appointment booking page"""
    template_name = 'core/book_appointment_public.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get active services with pricing info
        services = []
        for service in Service.objects.filter(is_archived=False):
            services.append({
                'id': service.id,
                'name': service.name,
                'duration': f"{service.duration_minutes} minutes",
                'price_range': f"₱{service.min_price:,.0f} - ₱{service.max_price:,.0f}" if hasattr(service, 'min_price') else "Contact clinic for pricing",
                'description': service.description or "Professional dental service"
            })
        
        # Get active dentists
        dentists = []
        for dentist in User.objects.filter(is_active_dentist=True):
            dentists.append({
                'id': dentist.id,
                'name': f"Dr. {dentist.first_name} {dentist.last_name}",
                'initials': f"{dentist.first_name[0]}{dentist.last_name[0]}" if dentist.first_name and dentist.last_name else "DR",
                'specialization': getattr(dentist, 'specialization', 'General Dentist')
            })
        
        context.update({
            'services_json': json.dumps(services),
            'dentists_json': json.dumps(dentists),
            'clinic_info': {
                'name': 'Dental Clinic',
                'hours': 'Monday to Saturday, 10:00 AM to 6:00 PM',
                'phone': '+63 912 345 6789',
                'email': 'info@dentalclinic.com'
            }
        })
        
        return context