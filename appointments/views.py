# appointments/views.py

# Standard library imports
import json
import re
from datetime import datetime, date, timedelta, time

# Django core imports
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView

# Local app imports
from .models import Appointment, Schedule
from .forms import AppointmentForm
from patients.models import Patient
from services.models import Service
from users.models import User
from core.models import Holiday, SystemSetting


# BACKEND ADMIN/STAFF VIEWS (Login Required, Permission Checked)

class AppointmentCalendarView(LoginRequiredMixin, TemplateView):
    """
    BACKEND VIEW: Calendar view for appointments - Main scheduling interface for staff
    Displays monthly calendar with all appointments, handles navigation between months
    """
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
            status__in=Appointment.BLOCKING_STATUSES
        ).select_related('patient', 'dentist', 'service', 'schedule').order_by(
            'schedule__date', 'schedule__start_time'
        )
        
        # Group appointments by date and serialize for JSON
        appointments_by_date = {}
        for appointment in appointments:
            date_key = appointment.schedule.date.strftime('%Y-%m-%d')
            if date_key not in appointments_by_date:
                appointments_by_date[date_key] = []
            
            appointment_data = {
                'id': appointment.id,
                'patient__first_name': appointment.patient.first_name,
                'patient__last_name': appointment.patient.last_name,
                'dentist__first_name': appointment.dentist.first_name,
                'dentist__last_name': appointment.dentist.last_name,
                'service__name': appointment.service.name,
                'schedule__date': appointment.schedule.date.strftime('%Y-%m-%d'),
                'schedule__start_time': appointment.schedule.start_time.strftime('%I:%M %p'),
                'schedule__end_time': appointment.schedule.end_time.strftime('%I:%M %p'),
                'status': appointment.status,
                'reason': appointment.reason or '',
                'patient_type': appointment.patient_type,
            }
            appointments_by_date[date_key].append(appointment_data)
        
        # Calculate navigation months
        if month == 1:
            prev_month, prev_year = 12, year - 1
        else:
            prev_month, prev_year = month - 1, year
            
        if month == 12:
            next_month, next_year = 1, year + 1
        else:
            next_month, next_year = month + 1, year
        
        # Month names
        month_names = [
            '', 'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ]

        context.update({
            'current_month': month,
            'current_year': year,
            'current_month_name': month_names[month],
            'prev_month': prev_month,
            'prev_year': prev_year,
            'next_month': next_month,
            'next_year': next_year,
            'appointments_by_date': json.dumps(appointments_by_date),
            'dentists': User.objects.filter(is_active_dentist=True),
            'today': today.strftime('%Y-%m-%d'),
            'pending_count': Appointment.objects.filter(status='pending').count(),
        })
        
        return context


class AppointmentRequestsView(LoginRequiredMixin, ListView):
    """
    BACKEND VIEW: View pending appointment requests - Staff approval interface
    Handles filtering, searching, and bulk operations on pending appointments
    """
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
        
        # Apply filters
        patient_type = self.request.GET.get('patient_type')
        if patient_type:
            queryset = queryset.filter(patient_type=patient_type)
        
        dentist = self.request.GET.get('dentist')
        if dentist:
            queryset = queryset.filter(dentist_id=dentist)
        
        # Date range filtering
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
        
        # Text search
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
            'patient_types': [('new', 'New Patients'), ('returning', 'Returning Patients')],
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
    """
    BACKEND VIEW: List all appointments with comprehensive filtering
    Admin interface for viewing all appointment records with pagination
    """
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
        
        # Status filtering
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Dentist filtering
        dentist = self.request.GET.get('dentist')
        if dentist:
            queryset = queryset.filter(dentist_id=dentist)
        
        # Date range filtering
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
        
        # Patient name search
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
    """
    BACKEND VIEW: Create new appointment - Staff booking interface
    Enhanced with conflict detection and automatic approval for staff bookings
    """
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
        try:
            with transaction.atomic():
                # Auto-approve staff bookings
                if self.request.user.has_permission('appointments'):
                    form.instance.status = 'approved'
                    form.instance.approved_at = timezone.now()
                    form.instance.approved_by = self.request.user
                
                # Validate no conflicts before saving
                schedule = form.cleaned_data['schedule']
                service = form.cleaned_data['service']
                
                start_datetime = datetime.combine(schedule.date, schedule.start_time)
                end_datetime = start_datetime + timedelta(minutes=service.duration_minutes)
                end_with_buffer = end_datetime + timedelta(minutes=schedule.buffer_minutes)
                
                conflicts = Appointment.get_conflicting_appointments(
                    dentist=schedule.dentist,
                    start_datetime=start_datetime,
                    end_datetime=end_with_buffer
                )
                
                if conflicts:
                    form.add_error(None, 'This time slot conflicts with existing appointments.')
                    return self.form_invalid(form)
                
                messages.success(
                    self.request, 
                    f'Appointment for {form.instance.patient.full_name} created successfully.'
                )
                return super().form_valid(form)
                
        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f'Error creating appointment: {str(e)}')
            return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('appointments:appointment_list')


class AppointmentDetailView(LoginRequiredMixin, DetailView):
    """
    BACKEND VIEW: View detailed appointment information
    Shows comprehensive appointment data with patient statistics and actions
    """
    model = Appointment
    template_name = 'appointments/appointment_detail.html'
    context_object_name = 'appointment'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        appointment = self.object
        
        # Patient appointment statistics
        patient_appointments = appointment.patient.appointments.all()
        context['patient_stats'] = {
            'total_appointments': patient_appointments.count(),
            'completed_appointments': patient_appointments.filter(status='completed').count(),
            'pending_appointments': patient_appointments.filter(status='pending').count(),
            'cancelled_appointments': patient_appointments.filter(status='cancelled').count(),
        }
        
        # Current date for template comparisons
        context['today'] = timezone.now().date()
        
        # Dentist schedule statistics
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        context['dentist_stats'] = {
            'today_schedules': appointment.dentist.schedules.filter(date=today).count(),
            'week_schedules': appointment.dentist.schedules.filter(
                date__gte=week_start, 
                date__lte=week_end
            ).count(),
        }
        
        return context


class AppointmentUpdateView(LoginRequiredMixin, UpdateView):
    """
    BACKEND VIEW: Update existing appointment
    Staff interface for modifying appointment details with validation
    """
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


# PUBLIC/PATIENT VIEWS
class BookAppointmentPublicView(TemplateView):
    """
    PUBLIC VIEW: Patient-facing appointment booking interface
    TODO: Implement public booking form for patients
    """
    template_name = 'core/book_appointment.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'dentists': User.objects.filter(is_active_dentist=True),
            'services': Service.objects.filter(is_archived=False),
        })
        return context


# API ENDPOINTS (AJAX/JSON Responses for Frontend)

def get_available_times_api(request):
    """
    API ENDPOINT: Get available appointment time slots
    Used by frontend calendar/booking forms to show available times
    Includes comprehensive conflict detection and business rule validation
    """
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
    
    # Business rule validations
    today = timezone.now().date()
    if appointment_date <= today:
        return JsonResponse({'available_times': [], 'error': 'Cannot book for past dates or today'})
    
    if appointment_date.weekday() == 6:  # Sunday
        return JsonResponse({'available_times': [], 'error': 'No appointments on Sundays'})
    
    if Holiday.objects.filter(date=appointment_date, is_active=True).exists():
        return JsonResponse({'available_times': [], 'error': 'No appointments on holidays'})
    
    # Get system settings for clinic configuration
    clinic_start = _get_system_setting_time('clinic_start_time', time(10, 0))
    clinic_end = _get_system_setting_time('clinic_end_time', time(18, 0))
    lunch_start = _get_system_setting_time('lunch_start_time', time(12, 0))
    lunch_end = _get_system_setting_time('lunch_end_time', time(13, 0))
    default_buffer = _get_system_setting_int('appointment_buffer_minutes', 15)
    slot_duration_minutes = _get_system_setting_int('appointment_time_slot_minutes', 30)
    
    # Get existing appointments that block time slots
    existing_appointments = Appointment.objects.filter(
        dentist=dentist,
        schedule__date=appointment_date,
        status__in=['pending', 'approved', 'completed']
    ).select_related('schedule', 'service')
    
    # Generate available time slots
    available_times = []
    service_duration = timedelta(minutes=service.duration_minutes)
    slot_duration = timedelta(minutes=slot_duration_minutes)
    
    current_time = datetime.combine(appointment_date, clinic_start)
    end_of_day = datetime.combine(appointment_date, clinic_end)
    lunch_start_dt = datetime.combine(appointment_date, lunch_start)
    lunch_end_dt = datetime.combine(appointment_date, lunch_end)
    
    while current_time + service_duration <= end_of_day:
        slot_start_time = current_time.time()
        service_end_time = current_time + service_duration
        service_end_with_buffer = service_end_time + timedelta(minutes=default_buffer)
        
        # Skip if extends past clinic hours
        if service_end_with_buffer > end_of_day:
            current_time += slot_duration
            continue
        
        # Skip lunch break overlap
        appointment_overlaps_lunch = not (
            service_end_with_buffer <= lunch_start_dt or 
            current_time >= lunch_end_dt
        )
        
        if appointment_overlaps_lunch:
            current_time += slot_duration
            continue
        
        # Check for conflicts with existing appointments
        has_conflict = False
        for appointment in existing_appointments:
            existing_start = datetime.combine(appointment_date, appointment.schedule.start_time)
            existing_service_end = existing_start + timedelta(minutes=appointment.service.duration_minutes)
            existing_end_with_buffer = existing_service_end + timedelta(minutes=appointment.schedule.buffer_minutes)
            
            if current_time < existing_end_with_buffer and service_end_with_buffer > existing_start:
                has_conflict = True
                break
        
        if not has_conflict:
            available_times.append(slot_start_time.strftime('%H:%M'))
        
        current_time += slot_duration
    
    return JsonResponse({
        'available_times': available_times,
        'service_duration': service.duration_minutes,
        'buffer_minutes': default_buffer,
        'clinic_hours': {
            'start': clinic_start.strftime('%H:%M'),
            'end': clinic_end.strftime('%H:%M'),
            'lunch_start': lunch_start.strftime('%H:%M'),
            'lunch_end': lunch_end.strftime('%H:%M')
        }
    })


def get_available_dates_api(request):
    """
    API ENDPOINT: Get available dates for appointment booking
    Returns dates excluding Sundays, holidays, and past dates
    """
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
    
    # Get holidays in one query
    holidays = set(Holiday.objects.filter(
        date__gte=start_date,
        date__lt=start_date + timedelta(days=60),
        is_active=True
    ).values_list('date', flat=True))
    
    for i in range(60):  # Next 60 days
        check_date = start_date + timedelta(days=i)
        
        # Skip Sundays and holidays
        if check_date.weekday() == 6 or check_date in holidays:
            continue
        
        available_dates.append(check_date.strftime('%Y-%m-%d'))
    
    return JsonResponse({'available_dates': available_dates})


def find_patient_api(request):
    """
    API ENDPOINT: Find existing patient by email or contact number
    Used by booking forms to auto-populate patient information
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
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


# ACTION VIEWS (Individual Appointment Actions)

@login_required
def approve_appointment(request, pk):
    """
    ACTION VIEW: Approve pending appointment with conflict validation
    Atomically updates appointment status with double-checking for conflicts
    """
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    try:
        with transaction.atomic():
            appointment = get_object_or_404(Appointment.objects.select_for_update(), pk=pk)
            
            if appointment.status != 'pending':
                messages.error(request, 'Only pending appointments can be approved.')
                return redirect('appointments:appointment_detail', pk=pk)
            
            # Double-check for conflicts before approving
            start_datetime = appointment.appointment_datetime
            end_datetime = appointment.appointment_end_datetime
            
            conflicts = Appointment.get_conflicting_appointments(
                dentist=appointment.dentist,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                exclude_appointment_id=appointment.id
            )
            
            if conflicts:
                messages.error(
                    request, 
                    'Cannot approve: Time slot conflicts with other approved appointments.'
                )
                return redirect('appointments:appointment_detail', pk=pk)
            
            appointment.approve(request.user)
            messages.success(request, f'Appointment for {appointment.patient.full_name} has been approved.')
            
    except Exception as e:
        messages.error(request, f'Error approving appointment: {str(e)}')
    
    return redirect('appointments:appointment_detail', pk=pk)


@login_required  
def reject_appointment(request, pk):
    """
    ACTION VIEW: Reject pending appointment
    Changes status to rejected and frees up the time slot
    """
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    try:
        with transaction.atomic():
            appointment = get_object_or_404(Appointment.objects.select_for_update(), pk=pk)
            
            if appointment.status != 'pending':
                messages.error(request, 'Only pending appointments can be rejected.')
                return redirect('appointments:appointment_detail', pk=pk)
            
            appointment.reject()
            messages.success(request, f'Appointment for {appointment.patient.full_name} has been rejected.')
            
    except Exception as e:
        messages.error(request, f'Error rejecting appointment: {str(e)}')
    
    return redirect('appointments:appointment_requests')


@login_required
def cancel_appointment(request, pk):
    """
    ACTION VIEW: Cancel existing appointment
    Validates cancellation eligibility and updates status
    """
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    try:
        with transaction.atomic():
            appointment = get_object_or_404(Appointment.objects.select_for_update(), pk=pk)
            
            if not appointment.can_be_cancelled:
                messages.error(request, 'This appointment cannot be cancelled.')
                return redirect('appointments:appointment_detail', pk=pk)
            
            appointment.cancel()
            messages.success(request, f'Appointment for {appointment.patient.full_name} has been cancelled.')
            
    except Exception as e:
        messages.error(request, f'Error cancelling appointment: {str(e)}')
    
    return redirect('appointments:appointment_detail', pk=pk)


@login_required
def complete_appointment(request, pk):
    """
    ACTION VIEW: Mark appointment as completed
    Finalizes appointment and updates patient treatment history
    """
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    try:
        with transaction.atomic():
            appointment = get_object_or_404(Appointment.objects.select_for_update(), pk=pk)
            
            if appointment.status != 'approved':
                messages.error(request, 'Only approved appointments can be marked as completed.')
                return redirect('appointments:appointment_detail', pk=pk)
            
            appointment.complete()
            messages.success(request, f'Appointment for {appointment.patient.full_name} has been marked as completed.')
            
    except Exception as e:
        messages.error(request, f'Error completing appointment: {str(e)}')
    
    return redirect('appointments:appointment_detail', pk=pk)


# HELPER FUNCTIONS AND UTILITIES
def _get_system_setting_time(key, default):
    """
    HELPER: Get system setting as time object with fallback
    Args:
        key (str): System setting key
        default (time): Default time value if setting not found
    Returns:
        time: Parsed time object
    """
    try:
        setting = SystemSetting.objects.get(key=key)
        return datetime.strptime(setting.value, '%H:%M').time()
    except (SystemSetting.DoesNotExist, ValueError):
        return default


def _get_system_setting_int(key, default):
    """
    HELPER: Get system setting as integer with fallback
    Args:
        key (str): System setting key
        default (int): Default integer value if setting not found
    Returns:
        int: Parsed integer value
    """
    try:
        setting = SystemSetting.objects.get(key=key)
        return int(setting.value)
    except (SystemSetting.DoesNotExist, ValueError):
        return default


@transaction.atomic
def create_appointment_atomic(patient, dentist, service, appointment_date, appointment_time, 
                            patient_type, reason='', buffer_minutes=15):
    """
    HELPER: Atomically create appointment and schedule with proper conflict checking
    
    Args:
        patient: Patient instance
        dentist: User instance (dentist)
        service: Service instance
        appointment_date: date object
        appointment_time: time object
        patient_type: str ('new' or 'returning')
        reason: str (optional)
        buffer_minutes: int (buffer time after appointment)
    
    Returns:
        tuple: (appointment, created) where created is boolean
    
    Raises:
        ValidationError: If there are conflicts or validation errors
    """
    # Calculate end time based on service duration
    start_datetime = datetime.combine(appointment_date, appointment_time)
    end_datetime = start_datetime + timedelta(minutes=service.duration_minutes)
    end_time = end_datetime.time()
    
    # Calculate end time including buffer
    end_with_buffer = end_datetime + timedelta(minutes=buffer_minutes)
    
    # Use select_for_update to prevent race conditions
    dentist = User.objects.select_for_update().get(id=dentist.id, is_active_dentist=True)
    
    # Check for conflicts using the new method
    conflicts = Appointment.get_conflicting_appointments(
        dentist=dentist,
        start_datetime=start_datetime,
        end_datetime=end_with_buffer
    )
    
    if conflicts:
        conflict_times = [
            f"{c.schedule.start_time.strftime('%I:%M %p')}-{c.schedule.effective_end_time.strftime('%I:%M %p')}"
            for c in conflicts
        ]
        raise ValidationError(
            f"Time slot conflicts with existing appointments: {', '.join(conflict_times)}"
        )
    
    # Create schedule first
    try:
        schedule = Schedule.objects.create(
            dentist=dentist,
            date=appointment_date,
            start_time=appointment_time,
            end_time=end_time,
            buffer_minutes=buffer_minutes,
            is_available=True,
            notes='Created for appointment booking'
        )
    except IntegrityError:
        # Handle case where schedule already exists
        schedule = Schedule.objects.get(
            dentist=dentist,
            date=appointment_date,
            start_time=appointment_time,
            end_time=end_time
        )
        
        # Check if this schedule already has an appointment
        existing_appointment = Appointment.objects.filter(
            schedule=schedule,
            status__in=Appointment.BLOCKING_STATUSES
        ).first()
        
        if existing_appointment:
            raise ValidationError("This time slot is already booked.")
    
    # Create appointment
    appointment = Appointment.objects.create(
        patient=patient,
        dentist=dentist,
        service=service,
        schedule=schedule,
        patient_type=patient_type,
        reason=reason,
        status='pending'
    )
    
    return appointment, True


def validate_name_field(value, field_name):
    """
    HELPER: Validate name fields for proper formatting
    Args:
        value (str): Name value to validate
        field_name (str): Field name for error messages
    Returns:
        str: Cleaned name value
    Raises:
        ValidationError: If name format is invalid
    """
    if not value or not value.strip():
        return value
    
    # Pattern allows letters, spaces, hyphens, and apostrophes
    name_pattern = re.compile(r'^[a-zA-Z\s\-\']+$')
    if not name_pattern.match(value.strip()):
        raise ValidationError(f'{field_name} should only contain letters, spaces, hyphens, and apostrophes.')
    
    return value.strip()


def validate_philippine_mobile(value):
    """
    HELPER: Validate Philippine mobile number formats
    Args:
        value (str): Mobile number to validate
    Returns:
        str: Cleaned mobile number
    Raises:
        ValidationError: If mobile number format is invalid
    """
    if not value or not value.strip():
        return value
    
    # Philippine mobile number pattern
    phone_pattern = re.compile(r'^(\+63|0)?[9]\d{9}$')
    clean_contact = value.replace(' ', '').replace('-', '')
    
    if not phone_pattern.match(clean_contact):
        raise ValidationError('Please enter a valid Philippine mobile number (e.g., +639123456789).')
    
    return clean_contact