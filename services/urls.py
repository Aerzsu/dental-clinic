#services/urls.py
from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    # Services
    path('', views.ServiceListView.as_view(), name='service_list'),
    path('create/', views.ServiceCreateView.as_view(), name='service_create'),
    path('<int:pk>/', views.ServiceDetailView.as_view(), name='service_detail'),
    path('<int:pk>/edit/', views.ServiceUpdateView.as_view(), name='service_update'),
    path('<int:pk>/toggle-archive/', views.ServiceArchiveView.as_view(), name='service_toggle_archive'),
    
    # Discounts
    path('discounts/', views.DiscountListView.as_view(), name='discount_list'),
    path('discounts/create/', views.DiscountCreateView.as_view(), name='discount_create'),
    path('discounts/<int:pk>/', views.DiscountDetailView.as_view(), name='discount_detail'),
    path('discounts/<int:pk>/edit/', views.DiscountUpdateView.as_view(), name='discount_update'),
    path('discounts/<int:pk>/toggle/', views.DiscountToggleView.as_view(), name='discount_toggle'),
]