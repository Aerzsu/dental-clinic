#appointments/views.py
# Standard library imports
import json
import re
from datetime import datetime, date, timedelta, time
from decimal import Decimal

# Django core imports
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction, IntegrityError
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
            status__in=Appointment.BLOCKING_STATUSES  # Use the new constant
        ).select_related('patient', 'dentist', 'service', 'schedule').order_by('schedule__date', 'schedule__start_time')
        
        # Group appointments by date and serialize properly
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
        
        # Get pending appointment count for notification badge
        pending_count = Appointment.objects.filter(status='pending').count()
        
        # Calculate navigation months properly
        if month == 1:
            prev_month, prev_year = 12, year - 1
        else:
            prev_month, prev_year = month - 1, year
            
        if month == 12:
            next_month, next_year = 1, year + 1
        else:
            next_month, next_year = month + 1, year
        
        # Get month name
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
        
        # Filter logic remains the same...
        patient_type = self.request.GET.get('patient_type')
        if patient_type:
            queryset = queryset.filter(patient_type=patient_type)
        
        dentist = self.request.GET.get('dentist')
        if dentist:
            queryset = queryset.filter(dentist_id=dentist)
        
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

# CRITICAL FIX: Updated time availability API with proper conflict detection
def get_available_times_api(request):
    """
    API endpoint to get available times with proper conflict detection.
    Now generates time slots dynamically based on clinic hours instead of requiring pre-existing schedules.
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
    
    # Validate appointment date
    today = timezone.now().date()
    if appointment_date <= today:
        return JsonResponse({'available_times': [], 'error': 'Cannot book for past dates or today'})
    
    # Check if it's Sunday
    if appointment_date.weekday() == 6:  # Sunday = 6
        return JsonResponse({'available_times': [], 'error': 'No appointments on Sundays'})
    
    # Check for holidays
    if Holiday.objects.filter(date=appointment_date, is_active=True).exists():
        return JsonResponse({'available_times': [], 'error': 'No appointments on holidays'})
    
    # Get system settings for clinic configuration
    try:
        clinic_start_setting = SystemSetting.objects.get(key='clinic_start_time')
        clinic_start = datetime.strptime(clinic_start_setting.value, '%H:%M').time()
    except (SystemSetting.DoesNotExist, ValueError):
        clinic_start = time(10, 0)  # Default 10:00 AM
    
    try:
        clinic_end_setting = SystemSetting.objects.get(key='clinic_end_time')
        clinic_end = datetime.strptime(clinic_end_setting.value, '%H:%M').time()
    except (SystemSetting.DoesNotExist, ValueError):
        clinic_end = time(18, 0)  # Default 6:00 PM
    
    try:
        lunch_start_setting = SystemSetting.objects.get(key='lunch_start_time')
        lunch_start = datetime.strptime(lunch_start_setting.value, '%H:%M').time()
    except (SystemSetting.DoesNotExist, ValueError):
        lunch_start = time(12, 0)  # Default 12:00 PM
    
    try:
        lunch_end_setting = SystemSetting.objects.get(key='lunch_end_time')
        lunch_end = datetime.strptime(lunch_end_setting.value, '%H:%M').time()
    except (SystemSetting.DoesNotExist, ValueError):
        lunch_end = time(13, 0)  # Default 1:00 PM
    
    try:
        buffer_setting = SystemSetting.objects.get(key='appointment_buffer_minutes')
        default_buffer = int(buffer_setting.value)
    except (SystemSetting.DoesNotExist, ValueError):
        default_buffer = 15  # Default 15 minutes
    
    try:
        slot_duration_setting = SystemSetting.objects.get(key='appointment_time_slot_minutes')
        slot_duration_minutes = int(slot_duration_setting.value)
    except (SystemSetting.DoesNotExist, ValueError):
        slot_duration_minutes = 30  # Default 30 minutes
    
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
    
    # Start from clinic opening time
    current_time = datetime.combine(appointment_date, clinic_start)
    end_of_day = datetime.combine(appointment_date, clinic_end)
    lunch_start_dt = datetime.combine(appointment_date, lunch_start)
    lunch_end_dt = datetime.combine(appointment_date, lunch_end)
    
    while current_time + service_duration <= end_of_day:
        slot_start_time = current_time.time()
        
        # Calculate when this service would end (including buffer)
        service_end_time = current_time + service_duration
        service_end_with_buffer = service_end_time + timedelta(minutes=default_buffer)
        
        # Skip if slot would extend past clinic hours
        if service_end_with_buffer > end_of_day:
            current_time += slot_duration
            continue
        
        # Skip lunch break - ensure entire appointment + buffer is outside lunch
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
            
            # Calculate existing appointment end time with buffer
            existing_service_end = existing_start + timedelta(minutes=appointment.service.duration_minutes)
            existing_end_with_buffer = existing_service_end + timedelta(minutes=appointment.schedule.buffer_minutes)
            
            # Check if proposed appointment overlaps with existing appointment
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


def find_patient_api(request):
    """API endpoint to find existing patient by identifier"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    identifier = request.GET.get('identifier', '').strip()
    if not identifier:
        return JsonResponse({'error': 'Identifier is required'}, status=400)
    
    # Minimum length check
    if len(identifier) < 3:
        return JsonResponse({'found': False})
    
    # Search for patient by email or contact number
    query = Q(is_active=True)
    
    # Check if identifier looks like an email
    if '@' in identifier:
        query &= Q(email__iexact=identifier)
    else:
        # Assume it's a contact number - handle different formats
        clean_identifier = identifier.replace(' ', '').replace('-', '').replace('+', '')
        # More flexible contact number matching
        query &= (
            Q(contact_number=identifier) | 
            Q(contact_number=clean_identifier) |
            Q(contact_number__endswith=clean_identifier[-10:]) if len(clean_identifier) >= 10 else Q()
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
    
# CRITICAL FIX: Enhanced appointment creation with atomic transactions
@transaction.atomic
def create_appointment_atomic(patient, dentist, service, appointment_date, appointment_time, 
                            patient_type, reason='', buffer_minutes=15):
    """
    Atomically create appointment and schedule with proper conflict checking.
    
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
    """Create new appointment with enhanced conflict detection"""
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
                # Auto-approve if user has permission and it's a staff booking
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

# Action views with enhanced error handling
@login_required
def approve_appointment(request, pk):
    """Approve an appointment request with conflict validation"""
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

# Other action views remain similar but with transaction.atomic wrapping...
@login_required  
def reject_appointment(request, pk):
    """Reject an appointment request"""
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
    """Cancel an appointment"""
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
    """Mark appointment as completed"""
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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        appointment = self.object
        
        # Add patient appointment statistics
        patient_appointments = appointment.patient.appointments.all()
        context['patient_stats'] = {
            'total_appointments': patient_appointments.count(),
            'completed_appointments': patient_appointments.filter(status='completed').count(),
            'pending_appointments': patient_appointments.filter(status='pending').count(),
            'cancelled_appointments': patient_appointments.filter(status='cancelled').count(),
        }
        
        # Add today's date for template comparisons
        context['today'] = timezone.now().date()
        
        # Add dentist schedule stats for the sidebar
        from datetime import timedelta
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


def find_patient_api(request):
    """API endpoint to find existing patient by identifier"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    identifier = request.GET.get('identifier', '').strip()
    if not identifier:
        return JsonResponse({'error': 'Identifier is required'}, status=400)
    
    # Search for patient by email or contact number
    # Improved search logic - handle empty fields properly
    query = Q(is_active=True)
    
    # Check if identifier looks like an email
    if '@' in identifier:
        query &= Q(email__iexact=identifier)
    else:
        # Assume it's a contact number
        query &= Q(contact_number=identifier)
    
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


# Additional helper function for name validation
def validate_name_field(value, field_name):
    """Helper function to validate name fields"""
    if not value or not value.strip():
        return value
    
    # Pattern allows letters, spaces, hyphens, and apostrophes
    name_pattern = re.compile(r'^[a-zA-Z\s\-\']+$')
    if not name_pattern.match(value.strip()):
        raise ValidationError(f'{field_name} should only contain letters, spaces, hyphens, and apostrophes.')
    
    return value.strip()


def validate_philippine_mobile(value):
    """Helper function to validate Philippine mobile numbers"""
    if not value or not value.strip():
        return value
    
    # Philippine mobile number pattern
    phone_pattern = re.compile(r'^(\+63|0)?[9]\d{9}$')
    clean_contact = value.replace(' ', '').replace('-', '')
    
    if not phone_pattern.match(clean_contact):
        raise ValidationError('Please enter a valid Philippine mobile number (e.g., +639123456789).')
    
    return clean_contact

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


