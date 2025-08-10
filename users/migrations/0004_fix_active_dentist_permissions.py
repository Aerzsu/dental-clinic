from django.db import migrations

def fix_active_dentist_permissions(apps, schema_editor):
    """
    Set is_active_dentist to False for all users whose role is not admin or dentist
    """
    User = apps.get_model('users', 'User')
    Role = apps.get_model('users', 'Role')
    
    # Get non-admin/dentist roles
    excluded_roles = Role.objects.exclude(name__in=['admin', 'dentist'])
    
    # Update users with these roles to have is_active_dentist=False
    updated_count = User.objects.filter(
        role__in=excluded_roles,
        is_active_dentist=True
    ).update(is_active_dentist=False)
    
    print(f"Updated {updated_count} users - set is_active_dentist=False for non-admin/dentist roles")

def reverse_fix_active_dentist_permissions(apps, schema_editor):
    """
    This migration is irreversible since we don't know the original state
    """
    pass

class Migration(migrations.Migration):
    dependencies = [
        ('users', '0003_fix_default_roles'),  # Replace with your actual last migration
    ]

    operations = [
        migrations.RunPython(fix_active_dentist_permissions, reverse_fix_active_dentist_permissions),
    ]