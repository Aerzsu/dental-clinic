# users/templatetags/user_tags.py
from django import template

register = template.Library()

@register.filter
def has_permission(user, module_name):
    """
    Template filter to check if user has permission for a module.
    Usage: {% if user|has_permission:'appointments' %}
    """
    if not user or not user.is_authenticated:
        return False
    return user.has_permission(module_name)

@register.simple_tag
def user_can(user, module_name):
    """
    Template tag to check if user has permission for a module.
    Usage: {% user_can user 'appointments' as can_view_appointments %}
           {% if can_view_appointments %}
    """
    if not user or not user.is_authenticated:
        return False
    return user.has_permission(module_name)