from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.db.models import Q
from django import forms
from .models import Service, Discount

class ServiceForm(forms.ModelForm):
    """Form for creating and updating services"""
    
    class Meta:
        model = Service
        fields = ['name', 'description', 'min_price', 'max_price', 'duration_minutes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'description': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500', 'rows': 4}),
            'min_price': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500', 'step': '0.01'}),
            'max_price': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500', 'step': '0.01'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500', 'min': '15', 'step': '15'}),
        }
        help_texts = {
            'min_price': 'Minimum price for this service',
            'max_price': 'Maximum price for this service',
            'duration_minutes': 'Expected duration in minutes (15-minute intervals)',
        }
    
    def clean(self):
        cleaned_data = super().clean()
        min_price = cleaned_data.get('min_price')
        max_price = cleaned_data.get('max_price')
        duration = cleaned_data.get('duration_minutes')
        
        if min_price and max_price and max_price < min_price:
            raise forms.ValidationError('Maximum price cannot be less than minimum price.')
        
        if duration and duration < 15:
            raise forms.ValidationError('Duration must be at least 15 minutes.')
        
        return cleaned_data

class DiscountForm(forms.ModelForm):
    """Form for creating and updating discounts"""
    
    class Meta:
        model = Discount
        fields = ['name', 'amount', 'is_percentage']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'amount': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500', 'step': '0.01'}),
            'is_percentage': forms.CheckboxInput(attrs={'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
        }
        help_texts = {
            'amount': 'Amount to discount (in pesos if flat rate, in percentage if percentage)',
            'is_percentage': 'Check if this is a percentage discount',
        }

class ServiceListView(LoginRequiredMixin, ListView):
    """List all services with search functionality"""
    model = Service
    template_name = 'services/service_list.html'
    context_object_name = 'services'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Service.objects.all()
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )
        
        # Filter by archived status
        show_archived = self.request.GET.get('show_archived')
        if not show_archived:
            queryset = queryset.filter(is_archived=False)
        
        return queryset.order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'search_query': self.request.GET.get('search', ''),
            'show_archived': self.request.GET.get('show_archived', False),
        })
        return context

class ServiceDetailView(LoginRequiredMixin, DetailView):
    """View service details"""
    model = Service
    template_name = 'services/service_detail.html'
    context_object_name = 'service'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)

class ServiceCreateView(LoginRequiredMixin, CreateView):
    """Create new service"""
    model = Service
    form_class = ServiceForm
    template_name = 'services/service_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, f'Service {form.instance.name} created successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('services:service_detail', kwargs={'pk': self.object.pk})

class ServiceUpdateView(LoginRequiredMixin, UpdateView):
    """Update service information"""
    model = Service
    form_class = ServiceForm
    template_name = 'services/service_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, f'Service {form.instance.name} updated successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('services:service_detail', kwargs={'pk': self.object.pk})

class ServiceArchiveView(LoginRequiredMixin, UpdateView):
    """Archive/unarchive service"""
    model = Service
    fields = []
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        service = self.get_object()
        service.is_archived = not service.is_archived
        service.save()
        
        status = 'archived' if service.is_archived else 'unarchived'
        messages.success(self.request, f'Service {service.name} has been {status}.')
        
        return redirect('services:service_list')

# Discount Views
class DiscountListView(LoginRequiredMixin, ListView):
    """List all discounts"""
    model = Discount
    template_name = 'services/discount_list.html'
    context_object_name = 'discounts'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = Discount.objects.all()
        
        # Search functionality
        search_query = self.request.GET.get('search')
        if search_query:
            queryset = queryset.filter(name__icontains=search_query)
        
        # Filter by active status
        show_inactive = self.request.GET.get('show_inactive')
        if not show_inactive:
            queryset = queryset.filter(is_active=True)
        
        return queryset.order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'search_query': self.request.GET.get('search', ''),
            'show_inactive': self.request.GET.get('show_inactive', False),
        })
        return context

class DiscountDetailView(LoginRequiredMixin, DetailView):
    """View discount details"""
    model = Discount
    template_name = 'services/discount_detail.html'
    context_object_name = 'discount'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)

class DiscountCreateView(LoginRequiredMixin, CreateView):
    """Create new discount"""
    model = Discount
    form_class = DiscountForm
    template_name = 'services/discount_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, f'Discount {form.instance.name} created successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('services:discount_detail', kwargs={'pk': self.object.pk})

class DiscountUpdateView(LoginRequiredMixin, UpdateView):
    """Update discount information"""
    model = Discount
    form_class = DiscountForm
    template_name = 'services/discount_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, f'Discount {form.instance.name} updated successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('services:discount_detail', kwargs={'pk': self.object.pk})

class DiscountToggleView(LoginRequiredMixin, UpdateView):
    """Toggle discount active status"""
    model = Discount
    fields = []
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('billing'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        discount = self.get_object()
        discount.is_active = not discount.is_active
        discount.save()
        
        status = 'activated' if discount.is_active else 'deactivated'
        messages.success(self.request, f'Discount {discount.name} has been {status}.')
        
        return redirect('services:discount_list')