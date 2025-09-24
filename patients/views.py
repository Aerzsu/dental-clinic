# patients/views.py - Updated for AM/PM slot system
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.db.models import Q, Count, Case, When
from django.http import JsonResponse, HttpResponse
from datetime import date, timedelta
import csv
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO

from .models import Patient
from .forms import PatientForm, PatientSearchForm, FindPatientForm
from appointments.models import Appointment


class PatientListView(LoginRequiredMixin, ListView):
    """Enhanced list view with filtering, search, and export functionality - UPDATED for AM/PM system"""
    model = Patient
    template_name = 'patients/patient_list.html'
    context_object_name = 'patients'
    paginate_by = 25
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('patients'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        # Updated to use appointment_date instead of appointment_slot
        queryset = Patient.objects.select_related().prefetch_related('appointments__service', 'appointments__assigned_dentist')
        
        # Get filter parameters
        search = self.request.GET.get('search', '').strip()
        status = self.request.GET.get('status', '')
        contact = self.request.GET.get('contact', '')
        activity = self.request.GET.get('activity', '')
        sort_by = self.request.GET.get('sort', 'name_asc')
        
        # Apply search filter
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search) |
                Q(email__icontains=search) |
                Q(contact_number__icontains=search)
            )
        
        # Apply status filter
        if status:
            if status == 'active':
                queryset = queryset.filter(is_active=True)
            elif status == 'inactive':
                queryset = queryset.filter(is_active=False)
        
        # Apply contact method filter
        if contact:
            if contact == 'email_only':
                queryset = queryset.filter(email__isnull=False, contact_number='')
            elif contact == 'phone_only':
                queryset = queryset.filter(contact_number__isnull=False, email='')
            elif contact == 'both':
                queryset = queryset.filter(email__isnull=False, contact_number__isnull=False)
            elif contact == 'none':
                queryset = queryset.filter(email='', contact_number='')
        
        # Apply activity filter - UPDATED to use appointment_date
        if activity:
            today = date.today()
            if activity == 'recent':
                recent_date = today - timedelta(days=30)
                recent_patient_ids = Appointment.objects.filter(
                    appointment_date__gte=recent_date,
                    status='completed'
                ).values_list('patient_id', flat=True).distinct()
                queryset = queryset.filter(id__in=recent_patient_ids)
            elif activity == 'upcoming':
                upcoming_patient_ids = Appointment.objects.filter(
                    appointment_date__gte=today,
                    status__in=['approved', 'pending']
                ).values_list('patient_id', flat=True).distinct()
                queryset = queryset.filter(id__in=upcoming_patient_ids)
            elif activity == 'no_recent':
                old_date = today - timedelta(days=90)
                recent_patient_ids = Appointment.objects.filter(
                    appointment_date__gte=old_date
                ).values_list('patient_id', flat=True).distinct()
                queryset = queryset.exclude(id__in=recent_patient_ids)
        
        # Apply sorting - UPDATED to use appointment_date
        if sort_by == 'name_asc':
            queryset = queryset.order_by('last_name', 'first_name')
        elif sort_by == 'name_desc':
            queryset = queryset.order_by('-last_name', '-first_name')
        elif sort_by == 'date_added_desc':
            queryset = queryset.order_by('-created_at')
        elif sort_by == 'date_added_asc':
            queryset = queryset.order_by('created_at')
        elif sort_by == 'last_visit_desc':
            # Updated to use appointment_date
            queryset = queryset.annotate(
                last_visit_date=Case(
                    When(appointments__appointment_date__isnull=False, 
                         then='appointments__appointment_date'),
                    default=None
                )
            ).order_by('-last_visit_date')
        elif sort_by == 'last_visit_asc':
            queryset = queryset.annotate(
                last_visit_date=Case(
                    When(appointments__appointment_date__isnull=False, 
                         then='appointments__appointment_date'),
                    default=None
                )
            ).order_by('last_visit_date')
        
        # Add appointment counts for display
        queryset = queryset.annotate(
            visit_count=Count('appointments', distinct=True)
        )
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter parameters (unchanged)
        context['current_filters'] = {
            'search': self.request.GET.get('search', ''),
            'status': self.request.GET.get('status', ''),
            'contact': self.request.GET.get('contact', ''),
            'activity': self.request.GET.get('activity', ''),
            'sort': self.request.GET.get('sort', 'name_asc'),
        }
        
        # Build active filters list for display (unchanged)
        active_filters = []
        if context['current_filters']['search']:
            active_filters.append(f"Search: {context['current_filters']['search']}")
        if context['current_filters']['status']:
            active_filters.append(f"Status: {context['current_filters']['status'].title()}")
        if context['current_filters']['contact']:
            active_filters.append(f"Contact: {context['current_filters']['contact'].replace('_', ' ').title()}")
        if context['current_filters']['activity']:
            active_filters.append(f"Activity: {context['current_filters']['activity'].replace('_', ' ').title()}")
        
        context['active_filters'] = active_filters
        
        # Get insights for dashboard - UPDATED to exclude pending appointments
        total_patients = Patient.objects.filter(is_active=True).count()
        today = date.today()
        
        # Only count appointments with confirmed patient records
        upcoming_appointments = Appointment.objects.filter(
            appointment_date__gte=today,
            status__in=['confirmed', 'pending'],  # pending appointments with existing patients still count
            patient__isnull=False  # Only count appointments with linked patient records
        ).values('patient').distinct().count()
        
        with_email = Patient.objects.filter(is_active=True, email__isnull=False).exclude(email='').count()
        
        # Only consider patients with completed appointments (confirmed patients only)
        old_date = today - timedelta(days=90)
        no_recent_visits = Patient.objects.filter(is_active=True).exclude(
            appointments__appointment_date__gte=old_date,
            appointments__status='completed',
            appointments__patient__isnull=False  # Only confirmed appointments
        ).count()
        
        context['insights'] = {
            'total_active': total_patients,
            'upcoming_appointments': upcoming_appointments,
            'with_email': with_email,
            'no_recent_visits': no_recent_visits,
        }
        
        # Total count remains the same (only actual Patient records)
        context['total_count'] = Patient.objects.count()
        
        # Handle export (unchanged)
        export_format = self.request.GET.get('export')
        if export_format in ['csv', 'pdf']:
            return self.export_patients(context['patients'], export_format)
        
        return context
    
    def export_patients(self, patients, format_type):
        """Export patients to CSV or PDF"""
        if format_type == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="patients.csv"'
            
            writer = csv.writer(response)
            writer.writerow(['Name', 'Email', 'Phone', 'Address', 'Date of Birth', 'Created', 'Total Visits'])
            
            for patient in patients:
                writer.writerow([
                    patient.full_name,
                    patient.email,
                    patient.contact_number,
                    patient.address,
                    patient.date_of_birth.strftime('%Y-%m-%d') if patient.date_of_birth else '',
                    patient.created_at.strftime('%Y-%m-%d'),
                    getattr(patient, 'visit_count', 0)
                ])
            
            return response
        
        elif format_type == 'pdf':
            # Simple PDF export using reportlab
            buffer = BytesIO()
            p = canvas.Canvas(buffer, pagesize=letter)
            
            # Title
            p.setFont("Helvetica-Bold", 16)
            p.drawString(50, 750, "Patient List Report")
            
            # Headers
            y = 700
            p.setFont("Helvetica-Bold", 12)
            p.drawString(50, y, "Name")
            p.drawString(200, y, "Email")
            p.drawString(350, y, "Phone")
            p.drawString(500, y, "Visits")
            
            # Data
            y -= 20
            p.setFont("Helvetica", 10)
            for patient in patients[:50]:  # Limit to 50 for simplicity
                if y < 50:
                    p.showPage()
                    y = 750
                
                p.drawString(50, y, patient.full_name[:25])
                p.drawString(200, y, patient.email[:20])
                p.drawString(350, y, patient.contact_number[:15])
                p.drawString(500, y, str(getattr(patient, 'visit_count', 0)))
                y -= 15
            
            p.save()
            buffer.seek(0)
            
            response = HttpResponse(buffer.read(), content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="patients.pdf"'
            return response


class PatientDetailView(LoginRequiredMixin, DetailView):
    """View patient details with appointment history - UPDATED for AM/PM system and payment context"""
    model = Patient
    template_name = 'patients/patient_detail.html'
    context_object_name = 'patient'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('patients'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        patient = self.object
        
        # Get all appointments ordered by date (most recent first) - UPDATED for AM/PM system
        appointments = Appointment.objects.filter(patient=patient).select_related(
            'service', 'assigned_dentist'
        ).order_by('-appointment_date', '-period', '-requested_at')
        
        # Categorize appointments - UPDATED to use appointment_date
        today = date.today()
        completed_appointments = appointments.filter(status='completed')
        upcoming_appointments = appointments.filter(
            appointment_date__gte=today, 
            status__in=['confirmed', 'pending']
        )
        cancelled_appointments = appointments.filter(status__in=['cancelled', 'rejected'])
        
        # Payment context - NEW
        from appointments.models import Payment, PaymentTransaction
        from decimal import Decimal
        
        # Get all payments for this patient
        patient_payments = Payment.objects.filter(patient=patient).select_related('appointment__service')
        
        # Calculate payment summary
        total_amount_due = Decimal('0')
        total_amount_paid = Decimal('0')
        
        for payment in patient_payments:
            total_amount_due += payment.total_amount
            total_amount_paid += payment.amount_paid
        
        outstanding_balance = total_amount_due - total_amount_paid
        
        # Get recent payments for display (last 5)
        recent_payments = patient_payments.order_by('-created_at')[:5]
        
        # Get next due date and check if overdue
        next_due_date = None
        is_overdue = False
        
        overdue_payment = patient_payments.filter(
            status__in=['pending', 'partially_paid'],
            next_due_date__isnull=False
        ).order_by('next_due_date').first()
        
        if overdue_payment:
            next_due_date = overdue_payment.next_due_date
            is_overdue = next_due_date < today
        
        # Get last payment transaction
        last_payment = None
        if patient_payments.exists():
            last_payment = PaymentTransaction.objects.filter(
                payment__patient=patient
            ).order_by('-payment_datetime').first()
        
        context.update({
            'appointments': appointments,
            'completed_appointments': completed_appointments,
            'upcoming_appointments': upcoming_appointments,
            'cancelled_appointments': cancelled_appointments,
            
            # Payment context
            'patient_payments': patient_payments,
            'total_amount_due': total_amount_due,
            'total_amount_paid': total_amount_paid,
            'outstanding_balance': outstanding_balance,
            'recent_payments': recent_payments,
            'next_due_date': next_due_date,
            'is_overdue': is_overdue,
            'last_payment': last_payment,
        })
        
        return context

class PatientCreateView(LoginRequiredMixin, CreateView):
    """Create new patient"""
    model = Patient
    form_class = PatientForm
    template_name = 'patients/patient_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('patients'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, f'Patient {form.instance.full_name} created successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('patients:patient_detail', kwargs={'pk': self.object.pk})


class PatientUpdateView(LoginRequiredMixin, UpdateView):
    """Update patient information"""
    model = Patient
    form_class = PatientForm
    template_name = 'patients/patient_form.html'
    context_object_name = 'patient'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('patients'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, f'Patient {form.instance.full_name} updated successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('patients:patient_detail', kwargs={'pk': self.object.pk})


class PatientSearchView(LoginRequiredMixin, ListView):
    """Search patients with advanced filtering"""
    model = Patient
    template_name = 'patients/patient_search.html'
    context_object_name = 'patients'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('patients'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        form = PatientSearchForm(self.request.GET)
        queryset = Patient.objects.none()
        
        if form.is_valid():
            query = form.cleaned_data.get('query')
            search_type = form.cleaned_data.get('search_type', 'all')
            
            if query:
                if search_type == 'name':
                    queryset = Patient.objects.filter(
                        Q(first_name__icontains=query) | Q(last_name__icontains=query)
                    )
                elif search_type == 'email':
                    queryset = Patient.objects.filter(email__icontains=query)
                elif search_type == 'phone':
                    queryset = Patient.objects.filter(contact_number__icontains=query)
                else:  # all
                    queryset = Patient.objects.filter(
                        Q(first_name__icontains=query) |
                        Q(last_name__icontains=query) |
                        Q(email__icontains=query) |
                        Q(contact_number__icontains=query)
                    )
        
        return queryset.order_by('last_name', 'first_name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = PatientSearchForm(self.request.GET)
        context['query'] = self.request.GET.get('query', '')
        return context


class FindPatientView(LoginRequiredMixin, ListView):
    """Find patient by email or phone for appointment booking"""
    model = Patient
    template_name = 'patients/find_patient.html'
    context_object_name = 'patients'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('patients'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        identifier = self.request.GET.get('identifier', '').strip()
        if not identifier:
            return Patient.objects.none()
        
        # Search by email or phone number
        return Patient.objects.filter(
            Q(email__iexact=identifier) | Q(contact_number=identifier)
        ).order_by('last_name', 'first_name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = FindPatientForm(self.request.GET)
        context['identifier'] = self.request.GET.get('identifier', '')
        
        # If no results and identifier provided, suggest creating new patient
        if context['identifier'] and not context['patients']:
            context['suggest_create'] = True
        
        return context


@login_required
def toggle_patient_active(request, pk):
    """Toggle patient active status"""
    if not request.user.has_permission('patients'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    patient = get_object_or_404(Patient, pk=pk)
    patient.is_active = not patient.is_active
    patient.save()
    
    status = 'activated' if patient.is_active else 'deactivated'
    messages.success(request, f'Patient {patient.full_name} has been {status}.')
    
    return redirect('patients:patient_detail', pk=pk)


@login_required  
def patient_quick_info(request, pk):
    """Return quick patient info as JSON for AJAX requests - UPDATED for AM/PM system"""
    if not request.user.has_permission('patients'):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        patient = Patient.objects.get(pk=pk)
        
        # Get recent appointments - UPDATED to use appointment_date
        recent_appointments = patient.appointments.filter(
            appointment_date__gte=date.today() - timedelta(days=30)
        ).order_by('-appointment_date', '-period')[:3]
        
        appointments_data = []
        for apt in recent_appointments:
            appointments_data.append({
                'date': apt.appointment_date.strftime('%Y-%m-%d'),
                'period': apt.get_period_display(),  # 'Morning' or 'Afternoon'
                'service': apt.service.name,
                'status': apt.get_status_display(),
            })
        
        data = {
            'id': patient.pk,
            'name': patient.full_name,
            'email': patient.email,
            'phone': patient.contact_number,
            'age': patient.age,
            'is_minor': patient.is_minor,
            'medical_notes': patient.medical_notes,
            'recent_appointments': appointments_data,
            'total_visits': patient.appointments.filter(status='completed').count(),
        }
        
        return JsonResponse(data)
        
    except Patient.DoesNotExist:
        return JsonResponse({'error': 'Patient not found'}, status=404)