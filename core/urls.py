#core/urls.py
from django.urls import path
from . import views
from appointments import views as appointment_views
from core.views import BookAppointmentView

app_name = 'core'

urlpatterns = [
    # Public pages
    path('', views.HomeView.as_view(), name='home'),
    path('book-appointment/', BookAppointmentView.as_view(), name='book_appointment'),
    # Authenticated pages
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    
    # Maintenance module
    path('maintenance/', views.MaintenanceHubView.as_view(), name='maintenance_hub'),
    
    # Audit logs
    path('audit-logs/', views.AuditLogListView.as_view(), name='audit_logs'),
    
    # System settings
    path('settings/', views.SystemSettingsView.as_view(), name='system_settings'),
]