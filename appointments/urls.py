#appointments/urls.py
from django.urls import path
from . import views, schedule_views

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

    # Schedule Settings - NEW
    path('schedule-settings/', schedule_views.DentistScheduleSettingsView.as_view(), name='schedule_settings'),
    path('schedule-settings/create-default/<int:dentist_id>/', schedule_views.create_default_schedule, name='create_default_schedule'),
    path('schedule-settings/reset/<int:dentist_id>/', schedule_views.reset_dentist_schedule, name='reset_dentist_schedule'),
    
    # Time Block Management - NEW
    path('time-blocks/', schedule_views.TimeBlockListView.as_view(), name='time_block_list'),
    path('time-blocks/create/', schedule_views.TimeBlockCreateView.as_view(), name='time_block_create'),
    path('time-blocks/<int:pk>/edit/', schedule_views.TimeBlockUpdateView.as_view(), name='time_block_update'),
    path('time-blocks/<int:pk>/delete/', schedule_views.TimeBlockDeleteView.as_view(), name='time_block_delete'),

    # API endpoints
    path('api/dentist-template/', schedule_views.get_dentist_template_api, name='get_dentist_template_api'),
    path('api/time-blocks/', schedule_views.get_time_blocks_api, name='get_time_blocks_api'),
    path('api/check-conflicts/', schedule_views.check_schedule_conflicts_api, name='check_schedule_conflicts_api'),
    path('api/available-dates/', views.get_available_dates_api, name='get_available_dates_api'),
    path('api/available-times/', views.get_available_times_api, name='get_available_times_api'),
    path('api/find-patient/', views.find_patient_api, name='find_patient_api'),
]