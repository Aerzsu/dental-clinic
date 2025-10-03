# appointments/views.py - Cleaned for AM/PM slot system

import json
from datetime import datetime, date, timedelta

from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import ListView, DetailView, CreateView, UpdateView, TemplateView

from .models import Appointment, DailySlots
from .forms import AppointmentForm, DailySlotsForm, AppointmentNoteFieldForm
from patients.models import Patient
from users.models import User
from core.models import AuditLog
from django.views.decorators.http import require_POST


# BACKEND ADMIN/STAFF VIEWS

class AppointmentCalendarView(LoginRequiredMixin, TemplateView):
    """BACKEND VIEW: Calendar view for AM/PM appointments"""
    template_name = 'appointments/appointment_calendar.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get current month or requested month with validation
        today = timezone.now().date()
        
        try:
            month = int(self.request.GET.get('month', today.month))
            year = int(self.request.GET.get('year', today.year))
            
            # Validate month and year ranges
            if not (1 <= month <= 12):
                raise ValueError("Invalid month")
            if not (2020 <= year <= 2030):  # Reasonable range
                raise ValueError("Invalid year")
                
        except (ValueError, TypeError) as e:
            # Fallback to current date if invalid parameters
            month = today.month
            year = today.year
        
        # Calculate date range with validation
        try:
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year + 1, 1, 1)
            else:
                end_date = date(year, month + 1, 1)
        except ValueError as e:
            # Fallback if date creation fails
            start_date = date(today.year, today.month, 1)
            if today.month == 12:
                end_date = date(today.year + 1, 1, 1)
            else:
                end_date = date(today.year, today.month + 1, 1)
            month = today.month
            year = today.year
        
        # Get appointments for the month
        appointments = Appointment.objects.filter(
            appointment_date__gte=start_date,
            appointment_date__lt=end_date,
            status__in=Appointment.BLOCKING_STATUSES,
            patient__isnull=False
        ).select_related('patient', 'assigned_dentist', 'service').order_by(
            'appointment_date', 'period'
        )
        
        # FIXED: Group appointments by date with proper formatting and validation
        appointments_by_date = {}
        for appointment in appointments:
            # Ensure consistent date formatting (YYYY-MM-DD)
            date_key = appointment.appointment_date.strftime('%Y-%m-%d')
            
            # Validate the appointment has required fields
            if not appointment.patient or not appointment.service:
                continue  # Skip malformed appointments
            
            if date_key not in appointments_by_date:
                appointments_by_date[date_key] = {'AM': [], 'PM': []}
            
            # Validate period
            period = appointment.period
            if period not in ['AM', 'PM']:
                period = 'AM'  # Default fallback
            
            appointment_data = {
                'id': appointment.id,
                'patient_name': appointment.patient.full_name or 'Unknown Patient',
                'dentist_name': appointment.assigned_dentist.full_name if appointment.assigned_dentist else None,  # FIXED: Use None instead of 'Unassigned'
                'service_name': appointment.service.name or 'Unknown Service',
                'status': appointment.status,
                'reason': appointment.reason or '',
                'patient_type': appointment.patient_type,
                'period': period,  # Add period to the data
                'appointment_date': date_key,  # Add formatted date
            }
            appointments_by_date[date_key][period].append(appointment_data)
        
        # Get daily slots with validation
        daily_slots = DailySlots.objects.filter(
            date__gte=start_date,
            date__lt=end_date
        )
        
        slots_by_date = {}
        for slot in daily_slots:
            date_key = slot.date.strftime('%Y-%m-%d')
            pending_counts = slot.get_pending_counts()
            slots_by_date[date_key] = {
                'am_available': max(0, slot.get_available_am_slots(include_pending=False)),  # Backend view
                'pm_available': max(0, slot.get_available_pm_slots(include_pending=False)),  # Backend view
                'am_total': max(0, slot.am_slots),
                'pm_total': max(0, slot.pm_slots),
                'am_pending': pending_counts['am_pending'],  # Show pending separately
                'pm_pending': pending_counts['pm_pending']   # Show pending separately
            }
        
        # Calculate navigation months with validation
        try:
            if month == 1:
                prev_month, prev_year = 12, year - 1
            else:
                prev_month, prev_year = month - 1, year
                
            if month == 12:
                next_month, next_year = 1, year + 1
            else:
                next_month, next_year = month + 1, year
        except:
            # Fallback navigation
            prev_month, prev_year = today.month, today.year
            next_month, next_year = today.month, today.year
        
        # FIXED: Add debugging and validation
        context.update({
            'current_month': month,
            'current_year': year,
            'current_month_name': date(year, month, 1).strftime('%B'),
            'prev_month': prev_month,
            'prev_year': prev_year,
            'next_month': next_month,
            'next_year': next_year,
            'appointments_by_date': json.dumps(appointments_by_date, default=str),  # Handle any date serialization issues
            'slots_by_date': json.dumps(slots_by_date, default=str),
            'dentists': User.objects.filter(is_active_dentist=True),
            'today': today.strftime('%Y-%m-%d'),
            'pending_count': Appointment.objects.filter(status='pending').count(),
        })

        context['can_accept_appointments'] = self.request.user.is_active_dentist
        
        return context



class AppointmentRequestsView(LoginRequiredMixin, ListView):
    """BACKEND VIEW: View pending appointment requests"""
    model = Appointment
    template_name = 'appointments/appointment_requests.html'
    context_object_name = 'appointments'
    paginate_by = 15
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')

        # Check if user can accept appointments
        if not request.user.is_active_dentist:
            messages.error(request, 'Only users who can accept appointments may view pending requests.')
            return redirect('core:dashboard')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Appointment.objects.filter(
            status='pending'
        ).select_related('patient', 'assigned_dentist', 'service').order_by('-requested_at')
        
        # Apply filters
        patient_type = self.request.GET.get('patient_type')
        if patient_type:
            queryset = queryset.filter(patient_type=patient_type)
        
        assigned_dentist = self.request.GET.get('assigned_dentist')
        if assigned_dentist:
            queryset = queryset.filter(assigned_dentist_id=assigned_dentist)
        
        # Date range filtering
        date_from = self.request.GET.get('date_from')
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(appointment_date__gte=date_from)
            except ValueError:
                pass
        
        date_to = self.request.GET.get('date_to')
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(appointment_date__lte=date_to)
            except ValueError:
                pass
        
        # Period filter
        period = self.request.GET.get('period')
        if period and period in ['AM', 'PM']:
            queryset = queryset.filter(period=period)
        
        # FIXED: Text search - handle both patient records and temp data
        search = self.request.GET.get('search')
        if search:
            # Create search conditions for both patient records and temp data
            search_conditions = Q()
            
            # Search in linked patient records
            search_conditions |= (
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search) |
                Q(patient__email__icontains=search) |
                Q(patient__contact_number__icontains=search)
            )
            
            # Search in temporary data (for pending appointments)
            search_conditions |= (
                Q(temp_first_name__icontains=search) |
                Q(temp_last_name__icontains=search) |
                Q(temp_email__icontains=search) |
                Q(temp_contact_number__icontains=search)
            )
            
            queryset = queryset.filter(search_conditions)
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'pending_count': self.get_queryset().count(),
            'patient_types': [('new', 'New Patients'), ('returning', 'Returning Patients')],
            'periods': [('AM', 'Morning'), ('PM', 'Afternoon')],
            'dentists': User.objects.filter(is_active_dentist=True),
            'filters': {
                'patient_type': self.request.GET.get('patient_type', ''),
                'assigned_dentist': self.request.GET.get('assigned_dentist', ''),
                'period': self.request.GET.get('period', ''),
                'date_from': self.request.GET.get('date_from', ''),
                'date_to': self.request.GET.get('date_to', ''),
                'search': self.request.GET.get('search', ''),
            }
        })
        return context


class AppointmentListView(LoginRequiredMixin, ListView):
    """BACKEND VIEW: List all appointments with comprehensive filtering"""
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
            'patient', 'assigned_dentist', 'service'
        )
        
        # Status filtering
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # Assigned dentist filtering
        assigned_dentist = self.request.GET.get('assigned_dentist')
        if assigned_dentist:
            queryset = queryset.filter(assigned_dentist_id=assigned_dentist)
        
        # Period filtering
        period = self.request.GET.get('period')
        if period and period in ['AM', 'PM']:
            queryset = queryset.filter(period=period)
        
        # Date range filtering
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(appointment_date__gte=date_from)
            except ValueError:
                pass
        
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(appointment_date__lte=date_to)
            except ValueError:
                pass
        
        # Patient name search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(patient__first_name__icontains=search) |
                Q(patient__last_name__icontains=search)
            )
        
        return queryset.order_by('-appointment_date', '-period')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'status_choices': Appointment.STATUS_CHOICES,
            'period_choices': [('AM', 'Morning'), ('PM', 'Afternoon')],
            'dentists': User.objects.filter(is_active_dentist=True),
            'filters': {
                'status': self.request.GET.get('status', ''),
                'assigned_dentist': self.request.GET.get('assigned_dentist', ''),
                'period': self.request.GET.get('period', ''),
                'date_from': self.request.GET.get('date_from', ''),
                'date_to': self.request.GET.get('date_to', ''),
                'search': self.request.GET.get('search', ''),
            }
        })
        return context

class AppointmentCreateView(LoginRequiredMixin, CreateView):
    """BACKEND VIEW: Create new appointment - UPDATED for AM/PM"""
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
                    form.instance.status = 'confirmed'
                    form.instance.approved_at = timezone.now()
                    form.instance.approved_by = self.request.user
                    
                    # Auto-assign dentist if not specified
                    if not form.instance.assigned_dentist:
                        available_dentist = User.objects.filter(is_active_dentist=True).first()
                        if available_dentist:
                            form.instance.assigned_dentist = available_dentist
                
                response = super().form_valid(form)
                
                # Log the action
                AuditLog.log_action(
                    user=self.request.user,
                    action='create',
                    model_instance=form.instance,
                    changes={'status': form.instance.status},
                    request=self.request
                )
                
                messages.success(
                    self.request, 
                    f'Appointment for {form.instance.patient.full_name} created successfully.'
                )
                return response
                
        except ValidationError as e:
            form.add_error(None, str(e))
            return self.form_invalid(form)
        except Exception as e:
            messages.error(self.request, f'Error creating appointment: {str(e)}')
            return self.form_invalid(form)
    
    def get_success_url(self):
        return reverse_lazy('appointments:appointment_list')


class AppointmentDetailView(LoginRequiredMixin, DetailView):
    """BACKEND VIEW: View detailed appointment information"""
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
        
        # Patient appointment statistics - FIXED: Handle None patient
        if appointment.patient:
            patient_appointments = appointment.patient.appointments.all()
            context['patient_stats'] = {
                'total_appointments': patient_appointments.count(),
                'completed_appointments': patient_appointments.filter(status='completed').count(),
                'pending_appointments': patient_appointments.filter(status='pending').count(),
                'cancelled_appointments': patient_appointments.filter(status='cancelled').count(),
            }
        else:
            # Handle case where appointment has no linked patient (pending appointments)
            context['patient_stats'] = {
                'total_appointments': 0,
                'completed_appointments': 0,
                'pending_appointments': 1,  # This appointment itself
                'cancelled_appointments': 0,
            }
        
        # Current date for template comparisons
        context['today'] = timezone.now().date()
        
        # Slot availability for the appointment date
        if appointment.appointment_date:
            daily_slots, _ = DailySlots.get_or_create_for_date(appointment.appointment_date)
            if daily_slots:
                context['slot_info'] = {
                    'am_available': daily_slots.get_available_am_slots(),
                    'pm_available': daily_slots.get_available_pm_slots(),
                    'am_total': daily_slots.am_slots,
                    'pm_total': daily_slots.pm_slots,
                }
        
        # Available dentists for assignment
        context['available_dentists'] = User.objects.filter(is_active_dentist=True)
        
        return context


class AppointmentUpdateView(LoginRequiredMixin, UpdateView):
    """BACKEND VIEW: Update existing appointment"""
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
        # Log the changes
        AuditLog.log_action(
            user=self.request.user,
            action='update',
            model_instance=form.instance,
            request=self.request
        )
        
        messages.success(
            self.request,
            f'Appointment for {form.instance.patient.full_name} updated successfully.'
        )
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('appointments:appointment_detail', kwargs={'pk': self.object.pk})


@login_required
@require_POST
def update_appointment_note(request, appointment_pk):
    """Update individual clinical note field via AJAX"""
    if not request.user.has_permission('patients'):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    appointment = get_object_or_404(Appointment, pk=appointment_pk)
    
    # Ensure user can edit this appointment's notes
    # Only allow editing for confirmed appointments or appointments with linked patients
    if not appointment.patient:
        return JsonResponse({'error': 'Cannot edit notes for unconfirmed appointments'}, status=400)
    
    try:
        data = json.loads(request.body)
        field_name = data.get('field_name')
        field_value = data.get('field_value', '').strip()
        
        # Validate field name
        valid_fields = ['symptoms', 'procedures', 'diagnosis']
        if field_name not in valid_fields:
            return JsonResponse({'error': 'Invalid field name'}, status=400)
        
        # Update the field
        setattr(appointment, field_name, field_value)
        appointment.save(update_fields=[field_name, 'updated_at'])
        
        return JsonResponse({
            'success': True,
            'message': f'{field_name.title()} updated successfully',
            'field_name': field_name,
            'field_value': field_value
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_appointment_notes(request, appointment_pk):
    """Get appointment clinical notes via AJAX"""
    if not request.user.has_permission('patients'):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    appointment = get_object_or_404(Appointment, pk=appointment_pk)
    
    return JsonResponse({
        'appointment_id': appointment.pk,
        'symptoms': appointment.symptoms,
        'procedures': appointment.procedures,
        'diagnosis': appointment.diagnosis,
        'patient_name': appointment.patient_name,
        'service_name': appointment.service.name,
        'appointment_date': appointment.appointment_date.strftime('%Y-%m-%d'),
        'period': appointment.get_period_display(),
    })


# DAILY SLOTS MANAGEMENT VIEWS (NEW for AM/PM system)
class DailySlotsManagementView(LoginRequiredMixin, ListView):
    """BACKEND VIEW: Manage daily slot allocations"""
    model = DailySlots
    template_name = 'appointments/daily_slots_list.html'
    context_object_name = 'daily_slots'
    paginate_by = 30
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = DailySlots.objects.all()
        
        # Date range filtering
        date_from = self.request.GET.get('date_from')
        date_to = self.request.GET.get('date_to')
        
        if not date_from and not date_to:
            # Default to next 60 days
            today = timezone.now().date()
            queryset = queryset.filter(
                date__gte=today,
                date__lte=today + timedelta(days=60)
            )
        else:
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
        
        return queryset.order_by('date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # FIXED: Add admin context slot data for each daily_slot
        enhanced_slots = []
        for slot in context['daily_slots']:
            # Calculate admin context availability (exclude pending)
            slot.admin_am_available = slot.get_available_am_slots(include_pending=False)
            slot.admin_pm_available = slot.get_available_pm_slots(include_pending=False)
            
            # Get pending counts
            pending_counts = slot.get_pending_counts()
            slot.am_pending = pending_counts['am_pending']
            slot.pm_pending = pending_counts['pm_pending']
            
            enhanced_slots.append(slot)
        
        context['daily_slots'] = enhanced_slots
        context['filters'] = {
            'date_from': self.request.GET.get('date_from', ''),
            'date_to': self.request.GET.get('date_to', ''),
        }
        return context


class DailySlotsCreateView(LoginRequiredMixin, CreateView):
    """
    BACKEND VIEW: Create/edit daily slots
    """
    model = DailySlots
    form_class = DailySlotsForm
    template_name = 'appointments/daily_slots_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        
        # Log the action
        AuditLog.log_action(
            user=self.request.user,
            action='create',
            model_instance=form.instance,
            request=self.request
        )
        
        messages.success(
            self.request,
            f'Daily slots for {form.instance.date} created successfully.'
        )
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('appointments:daily_slots_list')


class DailySlotsUpdateView(LoginRequiredMixin, UpdateView):
    """
    BACKEND VIEW: Update daily slots
    """
    model = DailySlots
    form_class = DailySlotsForm
    template_name = 'appointments/daily_slots_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        # Log the action
        AuditLog.log_action(
            user=self.request.user,
            action='update',
            model_instance=form.instance,
            request=self.request
        )
        
        messages.success(
            self.request,
            f'Daily slots for {form.instance.date} updated successfully.'
        )
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('appointments:daily_slots_list')


# API ENDPOINTS

def get_slot_availability_api(request):
    """
    API ENDPOINT: Get AM/PM slot availability for date range
    FIXED to handle past dates properly
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if not start_date_str or not end_date_str:
        return JsonResponse({'error': 'start_date and end_date are required'}, status=400)
    
    try:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
    
    # Validate date range
    today = timezone.now().date()
    
    # FIXED: Don't reject if start_date is in the past, just adjust it
    if start_date < today:
        start_date = today
    
    if end_date < start_date:
        return JsonResponse({'error': 'End date must be after or equal to start date'}, status=400)
    
    # Limit range to prevent excessive queries
    if (end_date - start_date).days > 90:
        return JsonResponse({'error': 'Date range too large. Maximum 90 days.'}, status=400)
    
    # Get availability for date range
    availability = DailySlots.get_availability_for_range(start_date, end_date)
    
    # Format for frontend
    formatted_availability = {}
    for date_obj, slots in availability.items():
        date_str = date_obj.strftime('%Y-%m-%d')
        
        # Skip Sundays and past dates (but include today)
        if date_obj.weekday() == 6 or date_obj < today:
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
            'has_availability': slots['am_available'] > 0 or slots['pm_available'] > 0
        }
    
    return JsonResponse({
        'availability': formatted_availability,
        'date_range': {
            'start': start_date_str,
            'end': end_date_str,
            'adjusted_start': start_date.strftime('%Y-%m-%d') if start_date.strftime('%Y-%m-%d') != start_date_str else None
        }
    })


def find_patient_api(request):
    """
    API ENDPOINT: Find existing patient by name, email, or contact number
    Supports both exact matching and autocomplete search
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    identifier = request.GET.get('identifier', '').strip()
    search_type = request.GET.get('type', 'exact')  # 'exact' or 'autocomplete'
    
    if not identifier or len(identifier) < 2:
        return JsonResponse({'found': False, 'patients': []})
    
    # AUTOCOMPLETE MODE: Return list of matching patients
    if search_type == 'autocomplete':
        patients = Patient.objects.filter(
            is_active=True
        ).filter(
            Q(first_name__icontains=identifier) |
            Q(last_name__icontains=identifier)
        ).select_related().order_by('last_name', 'first_name')[:10]
        
        patient_list = [{
            'id': p.id,
            'name': p.full_name,
            'email': p.email or 'No email',
            'contact_number': p.contact_number or 'No phone'
        } for p in patients]
        
        return JsonResponse({
            'patients': patient_list,
            'count': len(patient_list)
        })
    
    # EXACT MODE: Original functionality for booking form
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


# ACTION VIEWS
@login_required
def approve_appointment(request, pk):
    """ACTION VIEW: Approve pending appointment and create/update patient record"""
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    try:
        with transaction.atomic():
            appointment = get_object_or_404(Appointment.objects.select_for_update(), pk=pk)
            
            if appointment.status != 'pending':
                messages.error(request, 'Only pending appointments can be approved.')
                return redirect('appointments:appointment_detail', pk=pk)
            
            # Check slot availability
            can_book, message = Appointment.can_book_appointment(
                appointment_date=appointment.appointment_date,
                period=appointment.period,
                exclude_appointment_id=appointment.id
            )
            
            if not can_book:
                messages.error(request, f'Cannot approve: {message}')
                return redirect('appointments:appointment_detail', pk=pk)
            
            # Get dentist to assign
            assigned_dentist_id = request.POST.get('assigned_dentist')
            if assigned_dentist_id:
                try:
                    assigned_dentist = User.objects.get(id=assigned_dentist_id, is_active_dentist=True)
                except User.DoesNotExist:
                    assigned_dentist = None
            else:
                assigned_dentist = User.objects.filter(is_active_dentist=True).first()
            
            # Store info for logging before approval changes it
            patient_name = appointment.patient_name
            was_new_patient = appointment.patient_type == 'new'
            
            # Approve appointment (automatic logging is disabled inside this method)
            appointment.approve(request.user, assigned_dentist)
            
            # Create a single comprehensive audit log entry
            changes = {
                'status': {'old': 'pending', 'new': 'confirmed', 'label': 'Status'},
                'assigned_dentist': {
                    'old': None, 
                    'new': assigned_dentist.full_name if assigned_dentist else 'Unassigned',
                    'label': 'Assigned Dentist'
                }
            }
            
            if was_new_patient:
                changes['patient_created'] = {
                    'old': None,
                    'new': f'Created patient record for {patient_name}',
                    'label': 'Patient Record'
                }
            
            description = f"Approved appointment for {patient_name}"
            if was_new_patient:
                description += " (new patient)"
            if assigned_dentist:
                description += f" and assigned to Dr. {assigned_dentist.get_full_name()}"
            
            AuditLog.log_action(
                user=request.user,
                action='approve',
                model_instance=appointment,
                changes=changes,
                description=description,
                request=request
            )
            
            messages.success(request, f'Appointment for {patient_name} has been approved.')
            
    except Exception as e:
        messages.error(request, f'Error approving appointment: {str(e)}')
    
    return redirect('appointments:appointment_detail', pk=pk)


@login_required  
def reject_appointment(request, pk):
    """ACTION VIEW: Reject pending appointment"""
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    try:
        with transaction.atomic():
            appointment = get_object_or_404(Appointment.objects.select_for_update(), pk=pk)
            
            if appointment.status != 'pending':
                messages.error(request, 'Only pending appointments can be rejected.')
                return redirect('appointments:appointment_detail', pk=pk)
            
            # Store info before rejection
            patient_name = appointment.patient_name
            old_status = appointment.status
            
            # Disable automatic logging
            appointment._skip_audit_log = True
            appointment.reject()
            
            # Create single audit log entry
            AuditLog.log_action(
                user=request.user,
                action='reject',
                model_instance=appointment,
                changes={
                    'status': {'old': old_status, 'new': 'rejected', 'label': 'Status'}
                },
                description=f"Rejected appointment request from {patient_name}",
                request=request
            )
            
            messages.success(request, f'Appointment for {patient_name} has been rejected.')
            
    except Exception as e:
        messages.error(request, f'Error rejecting appointment: {str(e)}')
    
    return redirect('appointments:appointment_requests')

@login_required
@require_POST
def update_appointment_status(request, pk):
    """ACTION VIEW: Update appointment status via dropdown"""
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    try:
        with transaction.atomic():
            appointment = get_object_or_404(Appointment.objects.select_for_update(), pk=pk)
            new_status = request.POST.get('status')
            
            # Status validation rules
            valid_transitions = {
                'confirmed': ['cancelled', 'completed', 'did_not_arrive'],
                'cancelled': ['confirmed'],  # Allow reactivation if needed
                'completed': [],  # Final status
                'did_not_arrive': ['confirmed'],  # Allow reactivation if patient shows up later
            }
            
            current_status = appointment.status
            
            # Check if transition is allowed
            if new_status not in valid_transitions.get(current_status, []):
                messages.error(
                    request, 
                    f'Cannot change status from {appointment.get_status_display()} to {dict(Appointment.STATUS_CHOICES).get(new_status, new_status)}'
                )
                return redirect('appointments:appointment_detail', pk=pk)
            
            # Additional validation for cancellation
            if new_status == 'cancelled' and not appointment.can_be_cancelled:
                messages.error(request, 'This appointment cannot be cancelled.')
                return redirect('appointments:appointment_detail', pk=pk)
            
            # Store old status and patient name for logging
            old_status = appointment.status
            patient_name = appointment.patient_name
            
            # Update status
            appointment.status = new_status
            appointment.save(update_fields=['status'])
            
            # Log the action
            AuditLog.log_action(
                user=request.user,
                action='status_change',
                model_instance=appointment,
                changes={
                    'old_status': old_status,
                    'new_status': new_status
                },
                request=request
            )
            
            # Success message
            status_display = appointment.get_status_display()
            messages.success(
                request, 
                f'Appointment for {patient_name} has been marked as {status_display.lower()}.'
            )
            
    except Exception as e:
        messages.error(request, f'Error updating appointment status: {str(e)}')
    
    return redirect('appointments:appointment_detail', pk=pk)

@login_required
def bulk_create_daily_slots(request):
    """
    UTILITY VIEW: Bulk create daily slots for a date range
    """
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    if request.method == 'POST':
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        am_slots = int(request.POST.get('am_slots', 6))
        pm_slots = int(request.POST.get('pm_slots', 8))
        
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            
            created_count = 0
            current_date = start_date
            
            with transaction.atomic():
                while current_date <= end_date:
                    # Skip Sundays
                    if current_date.weekday() != 6:
                        daily_slots, created = DailySlots.objects.get_or_create(
                            date=current_date,
                            defaults={
                                'am_slots': am_slots,
                                'pm_slots': pm_slots,
                                'created_by': request.user
                            }
                        )
                        
                        if created:
                            created_count += 1
                    
                    current_date += timedelta(days=1)
            
            messages.success(request, f'Successfully created slots for {created_count} days.')
            
        except ValueError:
            messages.error(request, 'Invalid date format.')
        except Exception as e:
            messages.error(request, f'Error creating slots: {str(e)}')
    
    return redirect('appointments:daily_slots_list')