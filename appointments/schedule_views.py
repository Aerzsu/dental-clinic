# appointments/schedule_views.py - Enhanced version with template context

"""
Schedule Management Views for Dental Clinic

This module handles all schedule-related functionality:
- Individual schedule CRUD operations
- Bulk schedule creation with template integration
- Dentist personal schedule management
- Schedule overview for administrators
"""

# Standard library imports
from datetime import datetime, timedelta, time
import json

# Django core imports
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, TemplateView
from django.http import JsonResponse
from django.utils import timezone

# Local app imports
from .models import Schedule, DentistSchedule
from .forms import ScheduleForm, DentistScheduleForm
from users.models import User
from core.models import Holiday


class ScheduleListView(LoginRequiredMixin, ListView):
    """
    BACKEND VIEW: List all dentist schedules with filtering
    Administrative interface for viewing schedule overview
    """
    model = Schedule
    template_name = 'appointments/schedule_list.html'
    context_object_name = 'schedules'
    paginate_by = 15  # Following your 15 items per page rule
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Schedule.objects.select_related('dentist').prefetch_related('appointments')
        
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
        
        # Only show future and recent schedules by default (last 30 days to future)
        if not date_from and not date_to:
            cutoff_date = timezone.now().date() - timedelta(days=30)
            queryset = queryset.filter(date__gte=cutoff_date)
        
        return queryset.order_by('-date', 'start_time')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'dentists': User.objects.filter(is_active_dentist=True).order_by('first_name', 'last_name'),
            'filters': {
                'dentist': self.request.GET.get('dentist', ''),
                'date_from': self.request.GET.get('date_from', ''),
                'date_to': self.request.GET.get('date_to', ''),
            },
            'today': timezone.now().date(),
        })
        return context


class ScheduleCreateView(LoginRequiredMixin, CreateView):
    """
    BACKEND VIEW: Create individual schedule entries
    Manual schedule creation for specific dates/times
    """
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


class ScheduleBulkCreateView(LoginRequiredMixin, TemplateView):
    """
    BACKEND VIEW: Bulk create schedules for multiple dates
    Administrative tool for creating recurring schedule patterns with template integration
    """
    template_name = 'appointments/schedule_bulk_create.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'dentists': User.objects.filter(is_active_dentist=True).order_by('first_name', 'last_name'),
            'days_of_week': [
                (0, 'Monday'),
                (1, 'Tuesday'), 
                (2, 'Wednesday'),
                (3, 'Thursday'),
                (4, 'Friday'),
                (5, 'Saturday'),
                (6, 'Sunday'),
            ],
            'today': timezone.now().date(),
        })
        return context
    
    def post(self, request, *args, **kwargs):
        try:
            data = request.POST
            dentist_id = data.get('dentist')
            start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
            end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
            
            # Validate date range
            if end_date < start_date:
                messages.error(request, 'End date must be after start date.')
                return self.get(request, *args, **kwargs)
            
            if start_date <= timezone.now().date():
                messages.error(request, 'Start date must be in the future.')
                return self.get(request, *args, **kwargs)
            
            # Limit bulk creation to reasonable range (e.g., 6 months)
            max_date_range = start_date + timedelta(days=180)
            if end_date > max_date_range:
                messages.error(request, 'Date range is too large. Maximum 6 months allowed.')
                return self.get(request, *args, **kwargs)
            
            # Get selected days of week (0=Monday, 6=Sunday)
            selected_days = [int(day) for day in data.getlist('days_of_week')]
            if not selected_days:
                messages.error(request, 'Please select at least one day of the week.')
                return self.get(request, *args, **kwargs)
            
            # Get time slots
            enable_morning = data.get('enable_morning') == 'on'
            enable_afternoon = data.get('enable_afternoon') == 'on'
            
            if not enable_morning and not enable_afternoon:
                messages.error(request, 'Please enable at least one time session.')
                return self.get(request, *args, **kwargs)
            
            morning_start = data.get('morning_start') if enable_morning else None
            morning_end = data.get('morning_end') if enable_morning else None
            afternoon_start = data.get('afternoon_start') if enable_afternoon else None
            afternoon_end = data.get('afternoon_end') if enable_afternoon else None
            
            # Additional options
            skip_holidays = data.get('skip_holidays') == '1'
            skip_existing = data.get('skip_existing') == '1'
            
            dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
            
            created_count = 0
            skipped_count = 0
            error_count = 0
            current_date = start_date
            
            # Get holidays in advance if skip_holidays is enabled
            holidays_set = set()
            if skip_holidays:
                holidays = Holiday.objects.filter(
                    date__gte=start_date,
                    date__lte=end_date,
                    is_active=True
                ).values_list('date', flat=True)
                holidays_set = set(holidays)
            
            with transaction.atomic():
                while current_date <= end_date:
                    # Check if this day of week is selected
                    if current_date.weekday() in selected_days:
                        # Skip holidays
                        if skip_holidays and current_date in holidays_set:
                            skipped_count += 1
                            current_date += timedelta(days=1)
                            continue
                        
                        # Skip Sundays (business rule)
                        if current_date.weekday() == 6:
                            skipped_count += 1
                            current_date += timedelta(days=1)
                            continue
                        
                        # Create morning schedule if specified
                        if morning_start and morning_end:
                            success = self._create_single_schedule(
                                dentist=dentist,
                                date=current_date,
                                start_time=datetime.strptime(morning_start, '%H:%M').time(),
                                end_time=datetime.strptime(morning_end, '%H:%M').time(),
                                notes='Bulk created morning schedule',
                                skip_existing=skip_existing
                            )
                            if success == 'created':
                                created_count += 1
                            elif success == 'skipped':
                                skipped_count += 1
                            else:
                                error_count += 1
                        
                        # Create afternoon schedule if specified
                        if afternoon_start and afternoon_end:
                            success = self._create_single_schedule(
                                dentist=dentist,
                                date=current_date,
                                start_time=datetime.strptime(afternoon_start, '%H:%M').time(),
                                end_time=datetime.strptime(afternoon_end, '%H:%M').time(),
                                notes='Bulk created afternoon schedule',
                                skip_existing=skip_existing
                            )
                            if success == 'created':
                                created_count += 1
                            elif success == 'skipped':
                                skipped_count += 1
                            else:
                                error_count += 1
                    
                    current_date += timedelta(days=1)
            
            # Build success message
            message_parts = []
            if created_count > 0:
                message_parts.append(f'{created_count} schedule(s) created')
            if skipped_count > 0:
                message_parts.append(f'{skipped_count} skipped')
            if error_count > 0:
                message_parts.append(f'{error_count} errors')
            
            if created_count > 0:
                messages.success(request, f'Bulk creation completed: {", ".join(message_parts)}.')
            else:
                messages.warning(request, f'No schedules were created: {", ".join(message_parts)}.')
                
            return redirect('appointments:schedule_list')
            
        except Exception as e:
            messages.error(request, f'Error creating schedules: {str(e)}')
            return self.get(request, *args, **kwargs)
    
    def _create_single_schedule(self, dentist, date, start_time, end_time, notes, skip_existing):
        """
        Helper method to create a single schedule entry
        Returns 'created', 'skipped', or 'error'
        """
        try:
            # Check for existing schedules if skip_existing is enabled
            if skip_existing:
                existing = Schedule.objects.filter(
                    dentist=dentist,
                    date=date,
                    start_time=start_time,
                    end_time=end_time
                ).exists()
                
                if existing:
                    return 'skipped'
            
            # Create or get the schedule
            schedule, created = Schedule.objects.get_or_create(
                dentist=dentist,
                date=date,
                start_time=start_time,
                end_time=end_time,
                defaults={
                    'is_available': True,
                    'buffer_minutes': 15,  # Default buffer
                    'notes': notes
                }
            )
            
            return 'created' if created else 'skipped'
            
        except Exception as e:
            # Log the error in production
            print(f"Error creating schedule for {dentist} on {date}: {str(e)}")
            return 'error'


class DentistScheduleManageView(LoginRequiredMixin, TemplateView):
    """
    BACKEND VIEW: Dentist's personal weekly schedule management
    Individual dentist interface for setting working hours and availability
    """
    template_name = 'appointments/dentist_schedule.html'
    
    def dispatch(self, request, *args, **kwargs):
        # Only dentists can access this view
        if not request.user.has_permission('appointments') or not request.user.is_active_dentist:
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get or create schedule for each weekday
        weekday_schedules = []
        for weekday in range(7):  # 0=Monday to 6=Sunday
            schedule, created = DentistSchedule.objects.get_or_create(
                dentist=self.request.user,
                weekday=weekday,
                defaults={
                    'is_working': weekday < 5,  # Monday to Friday by default
                    'start_time': time(10, 0),
                    'end_time': time(18, 0),
                    'lunch_start': time(12, 0),
                    'lunch_end': time(13, 0),
                    'has_lunch_break': True,
                }
            )
            
            form = DentistScheduleForm(
                instance=schedule,
                prefix=f'day_{weekday}'
            )
            
            weekday_schedules.append({
                'weekday': weekday,
                'weekday_name': schedule.get_weekday_display(),
                'schedule': schedule,
                'form': form,
                'is_weekend': weekday >= 5,  # Saturday and Sunday
            })
        
        context['weekday_schedules'] = weekday_schedules
        context['dentist'] = self.request.user
        
        return context
    
    def post(self, request, *args, **kwargs):
        """Handle schedule updates for all weekdays"""
        try:
            with transaction.atomic():
                all_valid = True
                forms_data = []
                
                # Process all 7 days
                for weekday in range(7):
                    schedule = get_object_or_404(
                        DentistSchedule, 
                        dentist=request.user, 
                        weekday=weekday
                    )
                    
                    form = DentistScheduleForm(
                        request.POST,
                        instance=schedule,
                        prefix=f'day_{weekday}'
                    )
                    
                    forms_data.append({
                        'weekday': weekday,
                        'form': form,
                        'schedule': schedule,
                    })
                    
                    if not form.is_valid():
                        all_valid = False
                
                if all_valid:
                    # Save all forms
                    for data in forms_data:
                        data['form'].save()
                    
                    messages.success(request, 'Your weekly schedule has been updated successfully.')
                    return redirect('appointments:dentist_schedule')
                else:
                    # Re-render with errors
                    weekday_schedules = []
                    for data in forms_data:
                        weekday_schedules.append({
                            'weekday': data['weekday'],
                            'weekday_name': data['schedule'].get_weekday_display(),
                            'schedule': data['schedule'],
                            'form': data['form'],
                            'is_weekend': data['weekday'] >= 5,
                        })
                    
                    context = self.get_context_data(**kwargs)
                    context['weekday_schedules'] = weekday_schedules
                    return render(request, self.template_name, context)
                    
        except Exception as e:
            messages.error(request, f'An error occurred while updating your schedule: {str(e)}')
            return redirect('appointments:dentist_schedule')


class DentistScheduleOverviewView(LoginRequiredMixin, TemplateView):
    """
    BACKEND VIEW: Overview of all dentists' weekly schedules
    Administrative view to see all dentist availability patterns
    """
    template_name = 'appointments/schedule_overview.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('appointments'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        dentists = User.objects.filter(is_active_dentist=True).order_by('first_name', 'last_name')
        
        dentist_schedules = []
        for dentist in dentists:
            # Get weekly schedule for this dentist
            weekly_schedule = []
            for weekday in range(7):
                try:
                    schedule = DentistSchedule.objects.get(dentist=dentist, weekday=weekday)
                except DentistSchedule.DoesNotExist:
                    # Create default schedule if doesn't exist
                    schedule = DentistSchedule.objects.create(
                        dentist=dentist,
                        weekday=weekday,
                        is_working=weekday < 5,  # Monday to Friday
                        start_time=time(10, 0),
                        end_time=time(18, 0),
                        lunch_start=time(12, 0),
                        lunch_end=time(13, 0),
                        has_lunch_break=True,
                    )
                
                weekly_schedule.append({
                    'weekday': weekday,
                    'weekday_name': schedule.get_weekday_display()[:3],  # Mon, Tue, etc.
                    'schedule': schedule,
                })
            
            dentist_schedules.append({
                'dentist': dentist,
                'weekly_schedule': weekly_schedule,
            })
        
        context['dentist_schedules'] = dentist_schedules
        
        return context


# API endpoint for loading dentist templates (for AJAX calls in bulk create)
def get_dentist_template_api(request):
    """
    API ENDPOINT: Get dentist's weekly schedule template for bulk creation
    Used by the bulk create form to auto-populate time slots
    """
    if not request.user.has_permission('appointments'):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    dentist_id = request.GET.get('dentist_id')
    if not dentist_id:
        return JsonResponse({'error': 'dentist_id required'}, status=400)
    
    try:
        dentist = User.objects.get(id=dentist_id, is_active_dentist=True)
        
        # Get weekly schedules for this dentist
        weekly_schedules = {}
        for weekday in range(7):
            try:
                schedule = DentistSchedule.objects.get(dentist=dentist, weekday=weekday)
                weekly_schedules[weekday] = {
                    'is_working': schedule.is_working,
                    'start_time': schedule.start_time.strftime('%H:%M') if schedule.is_working else None,
                    'end_time': schedule.end_time.strftime('%H:%M') if schedule.is_working else None,
                    'lunch_start': schedule.lunch_start.strftime('%H:%M') if schedule.has_lunch_break else None,
                    'lunch_end': schedule.lunch_end.strftime('%H:%M') if schedule.has_lunch_break else None,
                    'has_lunch_break': schedule.has_lunch_break,
                }
            except DentistSchedule.DoesNotExist:
                # Default schedule
                weekly_schedules[weekday] = {
                    'is_working': weekday < 5,  # Mon-Fri
                    'start_time': '10:00' if weekday < 5 else None,
                    'end_time': '18:00' if weekday < 5 else None,
                    'lunch_start': '12:00' if weekday < 5 else None,
                    'lunch_end': '13:00' if weekday < 5 else None,
                    'has_lunch_break': weekday < 5,
                }
        
        return JsonResponse({
            'success': True,
            'dentist_name': dentist.full_name,
            'weekly_schedules': weekly_schedules
        })
        
    except User.DoesNotExist:
        return JsonResponse({'error': 'Dentist not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)