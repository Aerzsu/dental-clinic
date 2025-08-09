# services/templatetags/service_filters.py
from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def subtract(value, arg):
    """Subtract arg from value"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def calculate_discount_amount(discount, original_amount):
    """Calculate the discount amount for a given original amount"""
    try:
        original = Decimal(str(original_amount))
        if discount.is_percentage:
            return float(original * (discount.amount / 100))
        return float(min(discount.amount, original))
    except (ValueError, TypeError, AttributeError):
        return 0

@register.filter
def calculate_final_amount(discount, original_amount):
    """Calculate the final amount after discount"""
    try:
        original = float(original_amount)
        discount_amount = calculate_discount_amount(discount, original_amount)
        return original - discount_amount
    except (ValueError, TypeError):
        return 0