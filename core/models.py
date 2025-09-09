# core/models.py
from django.db import models
from datetime import datetime

class SystemSetting(models.Model):
    SETTING_TYPES = [
        ('string', 'String'),
        ('integer', 'Integer'),
        ('boolean', 'Boolean'),
        ('time', 'Time'),
        ('date', 'Date'),
        ('json', 'JSON'),
    ]
    
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    setting_type = models.CharField(max_length=20, choices=SETTING_TYPES, default='string')
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
    def set_setting(cls, key, value, setting_type='string', description=''):
        """Set or update a setting"""
        setting, created = cls.objects.get_or_create(
            key=key,
            defaults={
                'value': str(value),
                'setting_type': setting_type,
                'description': description,
                'is_active': True
            }
        )
        if not created:
            setting.value = str(value)
            setting.setting_type = setting_type
            setting.description = description
            setting.is_active = True
            setting.save()
        return setting


class Holiday(models.Model):
    name = models.CharField(max_length=100)
    date = models.DateField()
    is_active = models.BooleanField(default=True)
    is_recurring = models.BooleanField(default=False, help_text="If true, holiday repeats annually")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['date']
        unique_together = ['name', 'date']
    
    def __str__(self):
        return f"{self.name} - {self.date}"
    
    @classmethod
    def is_holiday(cls, check_date):
        """Check if a given date is a holiday"""
        # Check exact date match
        if cls.objects.filter(date=check_date, is_active=True).exists():
            return True
        
        # Check recurring holidays (same month/day)
        recurring_holidays = cls.objects.filter(
            is_recurring=True, 
            is_active=True,
            date__month=check_date.month,
            date__day=check_date.day
        )
        return recurring_holidays.exists()


class AuditLog(models.Model):
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
    user_agent = models.TextField(blank=True)
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
            log_entry.user_agent = request.META.get('HTTP_USER_AGENT', '')
        
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