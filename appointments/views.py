from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone
from django.core.exceptions import ValidationError
from datetime import datetime, date, timedelta, time
import json

from .models import Appointment, Schedule
from .forms import AppointmentForm, ScheduleForm, AppointmentRequestForm
from patients.models import Patient
from services.models import Service
from users.models import User
from core.models import Holiday

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
        
        context.update({
            'current_month': month,
            'current_year': year,
            'appointments_by_date': json.dumps(appointments_by_date, default=str),
            'dentists': User.objects.filter(is_active_dentist=True),
            'today': today.strftime('%Y-%m-%d'),
        })
        
        return context

class AppointmentRequestsView(LoginRequiredMixin, ListView):
    """View appointment requests (pending appointments)"""
    model = Appointment
    template_name = 'appointments/appointment_requests.html'
    context_object_name = 'appointments'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return Appointment.objects.filter(
            status='pending'
        ).select_related('patient', 'dentist', 'service', 'schedule').order_by('-requested_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pending_count'] = self.get_queryset().count()
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