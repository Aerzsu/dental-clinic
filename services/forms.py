# services/forms.py
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
            'duration_minutes': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500', 'min': '1'}),
        }
        help_texts = {
            'min_price': 'Minimum price for this service',
            'max_price': 'Maximum price for this service',
            'duration_minutes': 'Expected duration in minutes',
        }
    
    def clean(self):
        cleaned_data = super().clean()
        min_price = cleaned_data.get('min_price')
        max_price = cleaned_data.get('max_price')
        duration = cleaned_data.get('duration_minutes')
        
        if min_price and max_price and max_price < min_price:
            raise forms.ValidationError('Maximum price cannot be less than minimum price.')
        
        if duration and duration < 1:
            raise forms.ValidationError('Duration must be at least 1 minute.')
        
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
    
    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        is_percentage = cleaned_data.get('is_percentage')
        
        if is_percentage and amount and amount > 100:
            raise forms.ValidationError('Percentage discount cannot exceed 100%.')
        
        if amount and amount <= 0:
            raise forms.ValidationError('Discount amount must be greater than zero.')
        
        return cleaned_data