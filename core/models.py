# core/models.py - Simplified version for small dental clinic
from django.db import models
from datetime import datetime

class SystemSetting(models.Model):
    """Simplified system settings - just key-value pairs"""
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'System Setting'
        verbose_name_plural = 'System Settings'
        ordering = ['key']
    
    def __str__(self):
        return f"{self.key}: {self.value}"
    
    @classmethod
    def get_setting(cls, key, default=None):
        """Get a setting value by key"""
        try:
            setting = cls.objects.get(key=key, is_active=True)
            return setting.value
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def get_int_setting(cls, key, default=0):
        """Get an integer setting value"""
        try:
            setting = cls.objects.get(key=key, is_active=True)
            return int(setting.value)
        except (cls.DoesNotExist, ValueError):
            return default
    
    @classmethod
    def get_bool_setting(cls, key, default=False):
        """Get a boolean setting value"""
        try:
            setting = cls.objects.get(key=key, is_active=True)
            return setting.value.lower() in ('true', '1', 'yes', 'on')
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def get_time_setting(cls, key, default=None):
        """Get a time setting value"""
        try:
            setting = cls.objects.get(key=key, is_active=True)
            return datetime.strptime(setting.value, '%H:%M').time()
        except (cls.DoesNotExist, ValueError):
            return default
    
    @classmethod
    def set_setting(cls, key, value, description=''):
        """Set or update a setting"""
        setting, created = cls.objects.get_or_create(
            key=key,
            defaults={
                'value': str(value),
                'description': description,
                'is_active': True
            }
        )
        if not created:
            setting.value = str(value)
            setting.description = description
            setting.is_active = True
            setting.save()
        return setting

class AuditLog(models.Model):
    """Simplified audit logging"""
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('approve', 'Approve'),
        ('reject', 'Reject'),
        ('cancel', 'Cancel'),
    ]
    
    user = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=50)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['model_name', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} {self.action} {self.model_name} at {self.timestamp}"
    
    @classmethod
    def log_action(cls, user, action, model_instance, changes=None, request=None):
        """Log an action"""
        log_entry = cls(
            user=user,
            action=action,
            model_name=model_instance._meta.model_name,
            object_id=model_instance.pk,
            object_repr=str(model_instance),
            changes=changes or {}
        )
        
        if request:
            log_entry.ip_address = cls.get_client_ip(request)
        
        log_entry.save()
        return log_entry
    
    @staticmethod
    def get_client_ip(request):
        """Get client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip