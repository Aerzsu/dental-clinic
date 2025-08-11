#core/urls.py
from django.urls import path
from . import views
from core.views import BookAppointmentView

app_name = 'core'

urlpatterns = [
    # Public pages
    path('', views.HomeView.as_view(), name='home'),
    path('book-appointment/', BookAppointmentView.as_view(), name='book_appointment'),
    # Authenticated pages
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    
    # Maintenance module
    path('holidays/', views.HolidayListView.as_view(), name='holiday_list'),
    path('holidays/create/', views.HolidayCreateView.as_view(), name='holiday_create'),
    path('holidays/<int:pk>/edit/', views.HolidayUpdateView.as_view(), name='holiday_update'),
    path('holidays/<int:pk>/delete/', views.HolidayDeleteView.as_view(), name='holiday_delete'),
    
    # Audit logs
    path('audit-logs/', views.AuditLogListView.as_view(), name='audit_logs'),
    
    # System settings
    path('settings/', views.SystemSettingsView.as_view(), name='system_settings'),
]