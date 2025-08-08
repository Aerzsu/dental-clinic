from django.urls import path
from . import views

app_name = 'appointments'

urlpatterns = [
    # Main appointment views
    path('', views.AppointmentListView.as_view(), name='appointment_list'),
    path('calendar/', views.AppointmentCalendarView.as_view(), name='appointment_calendar'),
    path('requests/', views.AppointmentRequestsView.as_view(), name='appointment_requests'),
    
    # Appointment CRUD
    path('create/', views.AppointmentCreateView.as_view(), name='appointment_create'),
    path('<int:pk>/', views.AppointmentDetailView.as_view(), name='appointment_detail'),
    path('<int:pk>/edit/', views.AppointmentUpdateView.as_view(), name='appointment_update'),
    
    # Appointment actions
    path('<int:pk>/approve/', views.approve_appointment, name='approve_appointment'),
    path('<int:pk>/reject/', views.reject_appointment, name='reject_appointment'),
    path('<int:pk>/cancel/', views.cancel_appointment, name='cancel_appointment'),
    path('<int:pk>/complete/', views.complete_appointment, name='complete_appointment'),
    
    # Schedule management
    path('schedules/', views.ScheduleListView.as_view(), name='schedule_list'),
    path('schedules/create/', views.ScheduleCreateView.as_view(), name='schedule_create'),
    
    # AJAX endpoints
    path('api/available-dates/', views.get_available_dates, name='get_available_dates'),
    path('api/available-times/', views.get_available_times, name='get_available_times'),
]