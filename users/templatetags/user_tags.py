# users/templatetags/user_tags.py
from django import template

register = template.Library()

@register.filter
def has_permission(user, module_name):
    """Check if user has permission for a specific module"""
    if not user or not user.is_authenticated:
        return False
    
    if user.is_superuser:
        return True
        
    if not hasattr(user, 'role') or not user.role:
        return False
        
    return user.role.permissions.get(module_name, False)

@register.simple_tag
def can_access(user, module_name):
    """Template tag to check user permissions"""
    return has_permission(user, module_name)

@register.inclusion_tag('users/_permission_badge.html')
def permission_badge(permission_name, has_access):
    """Display a permission badge"""
    return {
        'permission_name': permission_name,
        'has_access': has_access,
    }