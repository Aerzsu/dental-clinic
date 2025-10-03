# core/middleware.py
"""
Middleware to track current user for audit logging
This allows signals to access the current user when models are saved
"""

import threading

# Thread-local storage for the current user
_thread_locals = threading.local()


def get_current_user():
    """Get the current user from thread-local storage"""
    return getattr(_thread_locals, 'user', None)


def set_current_user(user):
    """Set the current user in thread-local storage"""
    _thread_locals.user = user


class AuditMiddleware:
    """
    Middleware to track the current user for audit logging
    Stores user in thread-local storage so signals can access it
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Set current user in thread-local storage
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            set_current_user(user)
        else:
            set_current_user(None)
        
        response = self.get_response(request)
        
        # Clean up after request
        set_current_user(None)
        
        return response


# Mixin to add current user to model instances
class AuditMixin:
    """
    Mixin for models to attach current user before save
    Usage: class MyModel(AuditMixin, models.Model): ...
    """
    
    def save(self, *args, **kwargs):
        # Attach current user to instance for signal handlers
        current_user = get_current_user()
        if current_user:
            self._current_user = current_user
        
        return super().save(*args, **kwargs)