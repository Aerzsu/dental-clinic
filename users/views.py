#users/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.db.models import Q
from django.http import JsonResponse
from django.contrib.auth.forms import UserCreationForm
from django import forms
from .models import User, Role

class UserForm(forms.ModelForm):
    """Form for creating and updating users"""
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput,
        required=False,
        help_text="Leave blank to keep current password (for updates)"
    )
    password2 = forms.CharField(
        label='Confirm Password',
        widget=forms.PasswordInput,
        required=False
    )
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'role', 'is_active_dentist', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'first_name': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'last_name': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'email': forms.EmailInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'phone': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'role': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.is_update = kwargs.pop('is_update', False)
        super().__init__(*args, **kwargs)
        
        # Make password required for new users
        if not self.is_update:
            self.fields['password1'].required = True
            self.fields['password2'].required = True
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        # Password validation for new users or when password is being changed
        if password1 or password2:
            if password1 != password2:
                raise forms.ValidationError("Passwords don't match.")
            if len(password1) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long.")
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        
        if password:
            user.set_password(password)
        
        if commit:
            user.save()
        return user

class RoleForm(forms.ModelForm):
    """Form for creating and updating roles"""
    
    class Meta:
        model = Role
        fields = ['name', 'display_name', 'description', 'permissions']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'display_name': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500'}),
            'description': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500', 'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Create permission checkboxes
        permission_choices = [
            ('dashboard', 'Dashboard'),
            ('appointments', 'Appointments'),
            ('patients', 'Patients'),
            ('billing', 'Billing'),
            ('reports', 'Reports'),
            ('maintenance', 'Maintenance'),
        ]
        
        for perm_key, perm_label in permission_choices:
            field_name = f'perm_{perm_key}'
            initial_value = False
            
            if self.instance and self.instance.permissions:
                initial_value = self.instance.permissions.get(perm_key, False)
            
            self.fields[field_name] = forms.BooleanField(
                label=perm_label,
                required=False,
                initial=initial_value,
                widget=forms.CheckboxInput(attrs={'class': 'rounded border-gray-300 text-primary-600 shadow-sm focus:border-primary-500 focus:ring-primary-500'})
            )
    
    def save(self, commit=True):
        role = super().save(commit=False)
        
        # Build permissions dict from checkboxes
        permissions = {}
        permission_keys = ['dashboard', 'appointments', 'patients', 'billing', 'reports', 'maintenance']
        
        for perm_key in permission_keys:
            field_name = f'perm_{perm_key}'
            permissions[perm_key] = self.cleaned_data.get(field_name, False)
        
        role.permissions = permissions
        
        if commit:
            role.save()
        return role

class UserListView(LoginRequiredMixin, ListView):
    """List all users with search functionality"""
    model = User
    template_name = 'users/user_list.html'
    context_object_name = 'users'
    paginate_by = 20
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        queryset = User.objects.select_related('role')
        search_query = self.request.GET.get('search')
        
        if search_query:
            queryset = queryset.filter(
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query)
            )
        
        return queryset.order_by('username')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        return context

class UserDetailView(LoginRequiredMixin, DetailView):
    """View user details"""
    model = User
    template_name = 'users/user_detail.html'
    context_object_name = 'user_obj'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)

class UserCreateView(LoginRequiredMixin, CreateView):
    """Create new user"""
    model = User
    form_class = UserForm
    template_name = 'users/user_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['is_update'] = False
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, f'User {form.instance.username} created successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('users:user_detail', kwargs={'pk': self.object.pk})

class UserUpdateView(LoginRequiredMixin, UpdateView):
    """Update user information"""
    model = User
    form_class = UserForm
    template_name = 'users/user_form.html'
    context_object_name = 'user_obj'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['is_update'] = True
        return kwargs
    
    def form_valid(self, form):
        messages.success(self.request, f'User {form.instance.username} updated successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('users:user_detail', kwargs={'pk': self.object.pk})

@login_required
def toggle_user_active(request, pk):
    """Toggle user active status"""
    if not request.user.has_permission('maintenance'):
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('core:dashboard')
    
    user = get_object_or_404(User, pk=pk)
    
    # Don't let users deactivate themselves
    if user == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('users:user_detail', pk=pk)
    
    user.is_active = not user.is_active
    user.save()
    
    status = 'activated' if user.is_active else 'deactivated'
    messages.success(request, f'User {user.username} has been {status}.')
    
    return redirect('users:user_detail', pk=pk)

# Role Views
class RoleListView(LoginRequiredMixin, ListView):
    """List all roles"""
    model = Role
    template_name = 'users/role_list.html'
    context_object_name = 'roles'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_queryset(self):
        return Role.objects.all().order_by('name')

class RoleDetailView(LoginRequiredMixin, DetailView):
    """View role details"""
    model = Role
    template_name = 'users/role_detail.html'
    context_object_name = 'role'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)

class RoleCreateView(LoginRequiredMixin, CreateView):
    """Create new role"""
    model = Role
    form_class = RoleForm
    template_name = 'users/role_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        messages.success(self.request, f'Role {form.instance.display_name} created successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('users:role_detail', kwargs={'pk': self.object.pk})

class RoleUpdateView(LoginRequiredMixin, UpdateView):
    """Update role information"""
    model = Role
    form_class = RoleForm
    template_name = 'users/role_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_permission('maintenance'):
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('core:dashboard')
        return super().dispatch(request, *args, **kwargs)
    
    def get_object(self):
        role = super().get_object()
        # Prevent editing of default roles
        if role.is_default:
            messages.error(self.request, 'Default roles cannot be edited.')
            raise redirect('users:role_list')
        return role
    
    def form_valid(self, form):
        messages.success(self.request, f'Role {form.instance.display_name} updated successfully.')
        return super().form_valid(form)
    
    def get_success_url(self):
        return reverse_lazy('users:role_detail', kwargs={'pk': self.object.pk})