# appointments/schedule_views.py

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
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from datetime import datetime, date, timedelta, time

from .models import DentistScheduleSettings, TimeBlock, Appointment, AppointmentSlot
from .forms import (
    DentistScheduleSettingsForm, TimeBlockForm, BulkTimeBlockForm, QuickTimeBlockForm
)
from users.models import User


class DentistScheduleSettingsView(LoginRequiredMixin, TemplateView):
    """
    MAIN VIEW: Comprehensive schedule settings management for dentists
    Handles working hours, buffer times, and basic schedule configuration
    """
    template_name = 'appointments/schedule_settings.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get dentist from URL or default to current user if they're a dentist
        dentist_id = self.request.GET.get('dentist')
        if dentist_id:
            dentist = get_object_or_404(User, id=dentist_id, is_active_dentist=True)
        elif self.request.user.is_active_dentist:
            dentist = self.request.user
        else:
            # Default to first available dentist for admin users
            dentist = User.objects.filter(is_active_dentist=True).first()
            if not dentist:
                messages.warning(self.request, 'No active dentists found.')
                return redirect('core:dashboard')
        
        # Get or create schedule settings for all weekdays
        weekday_settings = []
        weekdays = [
            (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
            (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')
        ]
        
        for weekday_num, weekday_name in weekdays:
            setting, created = DentistScheduleSettings.objects.get_or_create(
                dentist=dentist,
                weekday=weekday_num,
                defaults={
                    'is_working': weekday_num < 5,  # Mon-Fri default
                    'start_time': time(10, 0),
                    'end_time': time(18, 0) if weekday_num < 5 else time(14, 0),  # Shorter Sat
                    'has_lunch_break': weekday_num < 5,  # No lunch on Saturday
                    'lunch_start': time(12, 0),
                    'lunch_end': time(13, 0),
                    'default_buffer_minutes': 15,
                    'slot_duration_minutes': 30,
                }
            )
            
            weekday_settings.append({
                'weekday_num': weekday_num,
                'weekday_name': weekday_name,
                'setting': setting,
                'form': DentistScheduleSettingsForm(instance=setting, prefix=f'day_{weekday_num}')
            })
        
        # Get upcoming time blocks
        today = timezone.now().date()
        upcoming_blocks = TimeBlock.objects.filter(
            dentist=dentist,
            date__gte=today
        ).order_by('date', 'start_time')[:10]
        
        # Get statistics
        context.update({
            'selected_dentist': dentist,
            'dentists': User.objects.filter(is_active_dentist=True).order_by('first_name', 'last_name'),
            'weekday_settings': weekday_settings,
            'upcoming_blocks': upcoming_blocks,
            'bulk_block_form': BulkTimeBlockForm(initial={'dentist': dentist}),
            'quick_block_form': QuickTimeBlockForm(),
            'stats': {
                'total_blocks': TimeBlock.objects.filter(dentist=dentist, date__gte=today).count(),
                'this_week_blocks': TimeBlock.objects.filter(
                    dentist=dentist,
                    date__gte=today,
                    date__lt=today + timedelta(days=7)
                ).count(),
            }
        })
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle form submissions for schedule settings"""
        action = request.POST.get('action')
        dentist_id = request.POST.get('dentist_id')
        dentist = get_object_or_404(User, id=dentist_id, is_active_dentist=True)
        
        if action == 'update_schedule':
            return self._handle_schedule_update(request, dentist)
        elif action == 'bulk_block':
            return self._handle_bulk_block(request, dentist)
        elif action == 'quick_block':
            return self._handle_quick_block(request, dentist)
        
        messages.error(request, 'Invalid action.')
        return redirect(f'{reverse_lazy("appointments:schedule_settings")}?dentist={dentist.id}')
    
    def _handle_schedule_update(self, request, dentist):
        """Handle updating weekly schedule settings"""
        all_forms_valid = True
        updated_days = []
        
        with transaction.atomic():
            for weekday_num in range(7):
                setting = get_object_or_404(DentistScheduleSettings, dentist=dentist, weekday=weekday_num)
                form = DentistScheduleSettingsForm(
                    request.POST, 
                    instance=setting, 
                    prefix=f'day_{weekday_num}'
                )
                
                if form.is_valid():
                    form.save()
                    weekday_name = setting.get_weekday_display()
                    updated_days.append(weekday_name)
                else:
                    all_forms_valid = False
                    for field, errors in form.errors.items():
                        for error in errors:
                            messages.error(request, f'{setting.get_weekday_display()} - {field}: {error}')
        
        if all_forms_valid:
            messages.success(request, f'Schedule updated for: {", ".join(updated_days)}')
        else:
            messages.error(request, 'Some settings could not be updated. Please check the errors.')
        
        return redirect(f'{reverse_lazy("appointments:schedule_settings")}?dentist={dentist.id}')
    
    def _handle_bulk_block(self, request, dentist):
        """Handle creating bulk time blocks"""
        form = BulkTimeBlockForm(request.POST)
        
        if form.is_valid():
            try:
                blocks_created = form.create_blocks(request.user)
                if blocks_created:
                    messages.success(
                        request, 
                        f'Created {len(blocks_created)} time blocks from {form.cleaned_data["start_date"]} to {form.cleaned_data["end_date"]}'
                    )
                else:
                    messages.warning(request, 'No new blocks were created (blocks may already exist for these dates)')
            except Exception as e:
                messages.error(request, f'Error creating bulk blocks: {str(e)}')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Bulk Block - {field}: {error}')
        
        return redirect(f'{reverse_lazy("appointments:schedule_settings")}?dentist={dentist.id}')
    
    def _handle_quick_block(self, request, dentist):
        """Handle creating quick time block"""
        form = QuickTimeBlockForm(request.POST)
        
        if form.is_valid():
            try:
                TimeBlock.objects.create(
                    dentist=form.cleaned_data['dentist'],
                    date=form.cleaned_data['date'],
                    start_time=form.cleaned_data['start_time'],
                    end_time=form.cleaned_data['end_time'],
                    block_type=form.cleaned_data['block_type'],
                    reason=form.cleaned_data['reason'],
                    created_by=request.user
                )
                messages.success(request, 'Quick time block created successfully')
            except Exception as e:
                messages.error(request, f'Error creating quick block: {str(e)}')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'Quick Block - {field}: {error}')
        
        return redirect(f'{reverse_lazy("appointments:schedule_settings")}?dentist={dentist.id}')


class TimeBlockListView(LoginRequiredMixin, ListView):
    """
    VIEW: List and manage time blocks with filtering and search
    """
    model = TimeBlock
    template_name = 'appointments/time_block_list.html'
    context_object_name = 'time_blocks'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = TimeBlock.objects.select_related('dentist', 'created_by')
        
        # Filter by dentist
        dentist_id = self.request.GET.get('dentist')
        if dentist_id:
            queryset = queryset.filter(dentist_id=dentist_id)
        
        # Filter by block type
        block_type = self.request.GET.get('block_type')
        if block_type:
            queryset = queryset.filter(block_type=block_type)
        
        # Filter by date range
        date_from = self.request.GET.get('date_from')
        if date_from:
            try:
                date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
                queryset = queryset.filter(date__gte=date_from)
            except ValueError:
                pass
        
        date_to = self.request.GET.get('date_to')
        if date_to:
            try:
                date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
                queryset = queryset.filter(date__lte=date_to)
            except ValueError:
                pass
        
        # Default to future blocks only
        show_past = self.request.GET.get('show_past')
        if not show_past:
            queryset = queryset.filter(date__gte=timezone.now().date())
        
        # Search
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(reason__icontains=search) |
                Q(notes__icontains=search) |
                Q(dentist__first_name__icontains=search) |
                Q(dentist__last_name__icontains=search)
            )
        
        return queryset.order_by('-date', '-start_time')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        context.update({
            'dentists': User.objects.filter(is_active_dentist=True).order_by('first_name'),
            'block_types': TimeBlock.BLOCK_TYPE_CHOICES,
            'filters': {
                'dentist': self.request.GET.get('dentist', ''),
                'block_type': self.request.GET.get('block_type', ''),
                'date_from': self.request.GET.get('date_from', ''),
                'date_to': self.request.GET.get('date_to', ''),
                'show_past': self.request.GET.get('show_past', ''),
                'search': self.request.GET.get('search', ''),
            }
        })
        
        return context


class TimeBlockCreateView(LoginRequiredMixin, CreateView):
    """
    VIEW: Create individual time block
    """
    model = TimeBlock
    form_class = TimeBlockForm
    template_name = 'appointments/time_block_form.html'
    
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
        # Check for existing appointments in this time slot
        time_block = form.instance
        conflicting_appointments = self._check_appointment_conflicts(time_block)
        
        if conflicting_appointments:
            conflict_list = ', '.join([
                f"{apt.patient.full_name} at {apt.appointment_slot.start_time.strftime('%I:%M %p')}"
                for apt in conflicting_appointments
            ])
            
            messages.warning(
                self.request,
                f'Warning: This time block conflicts with existing appointments: {conflict_list}. '
                f'Please review and handle these appointments manually.'
            )
        
        messages.success(self.request, 'Time block created successfully.')
        return super().form_valid(form)
    
    def _check_appointment_conflicts(self, time_block):
        """Check for appointments that conflict with the time block"""
        if time_block.is_full_day:
            return Appointment.objects.filter(
                dentist=time_block.dentist,
                appointment_slot__date=time_block.date,
                status__in=Appointment.BLOCKING_STATUSES
            )
        else:
            conflicts = []
            appointments = Appointment.objects.filter(
                dentist=time_block.dentist,
                appointment_slot__date=time_block.date,
                status__in=Appointment.BLOCKING_STATUSES
            ).select_related('appointment_slot', 'patient')
            
            for appointment in appointments:
                apt_start = appointment.appointment_slot.start_time
                apt_end = appointment.appointment_slot.effective_end_time
                
                # Check for overlap
                if apt_start < time_block.end_time and apt_end > time_block.start_time:
                    conflicts.append(appointment)
            
            return conflicts
    
    def get_success_url(self):
        return reverse_lazy('appointments:time_block_list')


class TimeBlockUpdateView(LoginRequiredMixin, UpdateView):
    """
    VIEW: Update existing time block
    """
    model = TimeBlock
    form_class = TimeBlockForm
    template_name = 'appointments/time_block_form.html'
    
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
        messages.success(self.request, 'Time block updated successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('appointments:time_block_list')


class TimeBlockDeleteView(LoginRequiredMixin, DeleteView):
    """
    VIEW: Delete time block
    """
    model = TimeBlock
    template_name = 'appointments/time_block_confirm_delete.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def delete(self, request, *args, **kwargs):
        messages.success(request, 'Time block deleted successfully.')
        return super().delete(request, *args, **kwargs)
    
    def get_success_url(self):
        return reverse_lazy('appointments:time_block_list')


# API ENDPOINTS FOR FRONTEND INTEGRATION

@login_required
def get_dentist_template_api(request):
    """
    API ENDPOINT: Get dentist's default schedule settings
    Used by frontend to populate forms with dentist's typical working hours
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    dentist_id = request.GET.get('dentist_id')
    if not dentist_id:
        return JsonResponse({'error': 'dentist_id is required'}, status=400)
    
    try:
        dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
    except User.DoesNotExist:
        return JsonResponse({'error': 'Invalid dentist'}, status=400)
    
    # Get schedule settings for all weekdays
    settings = DentistScheduleSettings.objects.filter(dentist=dentist).order_by('weekday')
    
    template_data = {
        'dentist_id': dentist.id,
        'dentist_name': dentist.full_name,
        'weekdays': []
    }
    
    for setting in settings:
        weekday_data = {
            'weekday': setting.weekday,
            'weekday_name': setting.get_weekday_display(),
            'is_working': setting.is_working,
            'start_time': setting.start_time.strftime('%H:%M') if setting.is_working else None,
            'end_time': setting.end_time.strftime('%H:%M') if setting.is_working else None,
            'has_lunch_break': setting.has_lunch_break if setting.is_working else False,
            'lunch_start': setting.lunch_start.strftime('%H:%M') if setting.is_working and setting.has_lunch_break else None,
            'lunch_end': setting.lunch_end.strftime('%H:%M') if setting.is_working and setting.has_lunch_break else None,
            'default_buffer_minutes': setting.default_buffer_minutes if setting.is_working else 15,
            'slot_duration_minutes': setting.slot_duration_minutes if setting.is_working else 30,
        }
        template_data['weekdays'].append(weekday_data)
    
    return JsonResponse(template_data)


@login_required
def get_time_blocks_api(request):
    """
    API ENDPOINT: Get time blocks for calendar display
    Used by frontend calendar to show blocked time slots
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    dentist_id = request.GET.get('dentist_id')
    date_from = request.GET.get('date_from')  # YYYY-MM-DD format
    date_to = request.GET.get('date_to')      # YYYY-MM-DD format
    
    if not all([dentist_id, date_from, date_to]):
        return JsonResponse({'error': 'dentist_id, date_from, and date_to are required'}, status=400)
    
    try:
        dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
        date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    except (User.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Invalid parameters'}, status=400)
    
    # Get time blocks in date range
    blocks = TimeBlock.objects.filter(
        dentist=dentist,
        date__gte=date_from,
        date__lte=date_to
    ).order_by('date', 'start_time')
    
    blocks_data = []
    for block in blocks:
        block_data = {
            'id': block.id,
            'date': block.date.strftime('%Y-%m-%d'),
            'is_full_day': block.is_full_day,
            'start_time': block.start_time.strftime('%H:%M') if block.start_time else None,
            'end_time': block.end_time.strftime('%H:%M') if block.end_time else None,
            'block_type': block.block_type,
            'block_type_display': block.get_block_type_display(),
            'reason': block.reason,
            'notes': block.notes,
        }
        blocks_data.append(block_data)
    
    return JsonResponse({
        'blocks': blocks_data,
        'dentist': {
            'id': dentist.id,
            'name': dentist.full_name
        }
    })


@login_required
def check_schedule_conflicts_api(request):
    """
    API ENDPOINT: Check for conflicts when creating/updating schedule settings
    Used to warn about existing appointments that would conflict with new settings
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        data = json.loads(request.body)
        
        dentist_id = data.get('dentist_id')
        weekday = data.get('weekday')
        new_start_time = data.get('start_time')  # HH:MM format
        new_end_time = data.get('end_time')      # HH:MM format
        has_lunch_break = data.get('has_lunch_break', False)
        lunch_start = data.get('lunch_start')    # HH:MM format
        lunch_end = data.get('lunch_end')        # HH:MM format
        
        if not all([dentist_id, weekday is not None, new_start_time, new_end_time]):
            return JsonResponse({'error': 'Missing required parameters'}, status=400)
        
        dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
        
        # Parse times
        start_time = datetime.strptime(new_start_time, '%H:%M').time()
        end_time = datetime.strptime(new_end_time, '%H:%M').time()
        
        if has_lunch_break and lunch_start and lunch_end:
            lunch_start_time = datetime.strptime(lunch_start, '%H:%M').time()
            lunch_end_time = datetime.strptime(lunch_end, '%H:%M').time()
        else:
            lunch_start_time = lunch_end_time = None
        
        # Check for existing appointments on this weekday that would conflict
        conflicts = []
        
        # Get next 4 weeks of this weekday to check
        today = timezone.now().date()
        check_dates = []
        current_date = today
        
        # Find next occurrence of this weekday
        days_ahead = weekday - current_date.weekday()
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7
        current_date += timedelta(days=days_ahead)
        
        # Check next 8 weeks
        for _ in range(8):
            check_dates.append(current_date)
            current_date += timedelta(days=7)
        
        for check_date in check_dates:
            appointments = Appointment.objects.filter(
                dentist=dentist,
                appointment_slot__date=check_date,
                status__in=Appointment.BLOCKING_STATUSES
            ).select_related('appointment_slot', 'patient')
            
            for appointment in appointments:
                apt_start = appointment.appointment_slot.start_time
                apt_end = appointment.appointment_slot.effective_end_time
                
                # Check if appointment is outside new working hours
                is_conflict = False
                conflict_reason = ''
                
                if apt_start < start_time or apt_end > end_time:
                    is_conflict = True
                    conflict_reason = 'Outside working hours'
                elif has_lunch_break and lunch_start_time and lunch_end_time:
                    # Check if appointment overlaps with lunch break
                    if apt_start < lunch_end_time and apt_end > lunch_start_time:
                        is_conflict = True
                        conflict_reason = 'During lunch break'
                
                if is_conflict:
                    conflicts.append({
                        'appointment_id': appointment.id,
                        'date': check_date.strftime('%Y-%m-%d'),
                        'start_time': apt_start.strftime('%I:%M %p'),
                        'end_time': apt_end.strftime('%I:%M %p'),
                        'patient_name': appointment.patient.full_name,
                        'service_name': appointment.service.name,
                        'reason': conflict_reason
                    })
        
        return JsonResponse({
            'has_conflicts': len(conflicts) > 0,
            'conflicts': conflicts,
            'conflict_count': len(conflicts)
        })
        
    except (User.DoesNotExist, ValueError, json.JSONDecodeError) as e:
        return JsonResponse({'error': f'Invalid request: {str(e)}'}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)


@login_required 
def create_default_schedule(request, dentist_id):
    """
    ACTION VIEW: Create default schedule settings for a dentist
    Creates Mon-Fri 10AM-6PM, Saturday 10AM-2PM, Sunday off
    """
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    dentist = get_object_or_404(User, id=dentist_id, is_active_dentist=True)
    
    try:
        schedules = DentistScheduleSettings.create_default_schedule(dentist)
        messages.success(
            request, 
            f'Default schedule created for Dr. {dentist.full_name} (Mon-Fri: 10AM-6PM, Sat: 10AM-2PM, Sun: Off)'
        )
    except Exception as e:
        messages.error(request, f'Error creating default schedule: {str(e)}')
    
    return redirect(f'{reverse_lazy("appointments:schedule_settings")}?dentist={dentist.id}')


@login_required
def reset_dentist_schedule(request, dentist_id):
    """
    ACTION VIEW: Reset dentist schedule to defaults (with confirmation)
    This will delete all existing settings and recreate defaults
    """
    if not request.user.has_permission('appointments'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    dentist = get_object_or_404(User, id=dentist_id, is_active_dentist=True)
    
    if request.method == 'POST' and request.POST.get('confirm') == 'yes':
        try:
            with transaction.atomic():
                # Delete existing settings
                DentistScheduleSettings.objects.filter(dentist=dentist).delete()
                
                # Create new defaults
                schedules = DentistScheduleSettings.create_default_schedule(dentist)
                
                messages.success(
                    request, 
                    f'Schedule reset to defaults for Dr. {dentist.full_name}'
                )
        except Exception as e:
            messages.error(request, f'Error resetting schedule: {str(e)}')
    
    return redirect(f'{reverse_lazy("appointments:schedule_settings")}?dentist={dentist.id}')


# HELPER FUNCTIONS

def get_available_time_slots_for_date(dentist, date, service=None):
    """
    HELPER: Get available appointment slots for a dentist on a specific date
    Considers working hours, lunch breaks, time blocks, and existing appointments
    
    Args:
        dentist: User object (dentist)
        date: Date object
        service: Service object (optional, for duration-based filtering)
    
    Returns:
        List of available time slots as (start_time, end_time) tuples
    """
    # Get dentist's schedule settings for this weekday
    weekday = date.weekday()
    try:
        settings = DentistScheduleSettings.objects.get(
            dentist=dentist, 
            weekday=weekday, 
            is_working=True
        )
    except DentistScheduleSettings.DoesNotExist:
        return []  # Dentist not working this day
    
    # Check if date is blocked
    if TimeBlock.objects.filter(dentist=dentist, date=date).exists():
        time_blocks = TimeBlock.objects.filter(dentist=dentist, date=date)
        # If any full-day block exists, no slots available
        if time_blocks.filter(start_time__isnull=True, end_time__isnull=True).exists():
            return []
    
    # Generate time slots based on settings
    available_slots = []
    slot_duration = timedelta(minutes=settings.slot_duration_minutes)
    service_duration = timedelta(minutes=service.duration_minutes) if service else slot_duration
    
    # Start from clinic opening
    current_time = datetime.combine(date, settings.start_time)
    clinic_end = datetime.combine(date, settings.end_time)
    
    while current_time + service_duration <= clinic_end:
        slot_start = current_time.time()
        slot_end = (current_time + service_duration).time()
        
        # Check if slot conflicts with lunch break
        if settings.has_lunch_break:
            lunch_start = datetime.combine(date, settings.lunch_start)
            lunch_end = datetime.combine(date, settings.lunch_end)
            
            # Skip if slot overlaps with lunch
            if current_time < lunch_end and (current_time + service_duration) > lunch_start:
                current_time += slot_duration
                continue
        
        # Check if slot is blocked by time blocks
        is_blocked = False
        time_blocks = TimeBlock.objects.filter(
            dentist=dentist, 
            date=date,
            start_time__isnull=False,
            end_time__isnull=False
        )
        
        for block in time_blocks:
            block_start = datetime.combine(date, block.start_time)
            block_end = datetime.combine(date, block.end_time)
            
            if current_time < block_end and (current_time + service_duration) > block_start:
                is_blocked = True
                break
        
        if is_blocked:
            current_time += slot_duration
            continue
        
        # Check if slot conflicts with existing appointments
        conflicts = Appointment.objects.filter(
            dentist=dentist,
            appointment_slot__date=date,
            appointment_slot__start_time__lt=slot_end,
            appointment_slot__end_time__gt=slot_start,
            status__in=Appointment.BLOCKING_STATUSES
        )
        
        if not conflicts.exists():
            available_slots.append((slot_start, slot_end))
        
        current_time += slot_duration
    
    return available_slots


def validate_schedule_change_impact(dentist, weekday, new_settings):
    """
    HELPER: Validate the impact of schedule changes on existing appointments
    
    Args:
        dentist: User object (dentist)
        weekday: Integer (0=Monday, 6=Sunday)  
        new_settings: Dict with new schedule settings
    
    Returns:
        Dict with validation results and conflicts
    """
    conflicts = []
    warnings = []
    
    # Check upcoming appointments for this weekday
    today = timezone.now().date()
    
    # Find dates for this weekday in next 8 weeks
    check_dates = []
    current_date = today
    days_ahead = weekday - current_date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    current_date += timedelta(days=days_ahead)
    
    for _ in range(8):  # Check next 8 weeks
        check_dates.append(current_date)
        current_date += timedelta(days=7)
    
    for check_date in check_dates:
        appointments = Appointment.objects.filter(
            dentist=dentist,
            appointment_slot__date=check_date,
            status__in=Appointment.BLOCKING_STATUSES
        ).select_related('appointment_slot', 'patient', 'service')
        
        for appointment in appointments:
            apt_start = appointment.appointment_slot.start_time
            apt_end = appointment.appointment_slot.effective_end_time
            
            # Check various conflict scenarios
            conflict_reasons = []
            
            # Outside new working hours
            if new_settings.get('is_working', True):
                new_start = new_settings.get('start_time')
                new_end = new_settings.get('end_time')
                
                if new_start and apt_start < new_start:
                    conflict_reasons.append('starts before new opening time')
                if new_end and apt_end > new_end:
                    conflict_reasons.append('ends after new closing time')
                
                # Lunch break conflicts
                if new_settings.get('has_lunch_break', False):
                    lunch_start = new_settings.get('lunch_start')
                    lunch_end = new_settings.get('lunch_end')
                    
                    if lunch_start and lunch_end:
                        if apt_start < lunch_end and apt_end > lunch_start:
                            conflict_reasons.append('overlaps with new lunch break')
            else:
                # Dentist no longer working this day
                conflict_reasons.append('dentist no longer working this day')
            
            if conflict_reasons:
                conflicts.append({
                    'appointment': appointment,
                    'date': check_date,
                    'reasons': conflict_reasons,
                    'severity': 'high' if 'no longer working' in ' '.join(conflict_reasons) else 'medium'
                })
    
    return {
        'is_valid': len(conflicts) == 0,
        'conflicts': conflicts,
        'warnings': warnings,
        'conflict_count': len(conflicts)
    }