# users/management/commands/setup_users.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from users.models import Role

User = get_user_model()

class Command(BaseCommand):
    help = 'Set up default roles and admin user for the dental clinic system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--admin-username',
            type=str,
            default='admin',
            help='Username for the admin user (default: admin)',
        )
        parser.add_argument(
            '--admin-password',
            type=str,
            default='admin123',
            help='Password for the admin user (default: admin123)',
        )
        parser.add_argument(
            '--admin-email',
            type=str,
            default='admin@dentalclinic.com',
            help='Email for the admin user',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up default roles and admin user...'))
        
        # Create default roles
        self.create_default_roles()
        
        # Create admin user
        self.create_admin_user(
            username=options['admin_username'],
            password=options['admin_password'],
            email=options['admin_email']
        )
        
        self.stdout.write(self.style.SUCCESS('Setup completed successfully!'))

    def create_default_roles(self):
        """Create the three default roles: Admin, Dentist, Staff"""
        
        roles_data = [
            {
                'name': 'admin',
                'display_name': 'Administrator',
                'description': 'Full system access and user management capabilities.',
                'permissions': {
                    'dashboard': True,
                    'appointments': True,
                    'patients': True,
                    'billing': True,
                    'reports': True,
                    'maintenance': True,
                },
                'is_default': True,
            },
            {
                'name': 'dentist',
                'display_name': 'Dentist',
                'description': 'Access to appointments, patient records, and billing. Cannot access reports or system maintenance.',
                'permissions': {
                    'dashboard': True,
                    'appointments': True,
                    'patients': True,
                    'billing': True,
                    'reports': False,
                    'maintenance': False,
                },
                'is_default': True,
            },
            {
                'name': 'staff',
                'display_name': 'Staff',
                'description': 'Reception and administrative staff. Access to appointments and patient management only.',
                'permissions': {
                    'dashboard': True,
                    'appointments': True,
                    'patients': True,
                    'billing': False,
                    'reports': False,
                    'maintenance': False,
                },
                'is_default': True,
            },
        ]
        
        for role_data in roles_data:
            role, created = Role.objects.get_or_create(
                name=role_data['name'],
                defaults=role_data
            )
            
            if created:
                self.stdout.write(f'Created role: {role.display_name}')
            else:
                # Update permissions for existing default roles
                if role.is_default:
                    role.permissions = role_data['permissions']
                    role.description = role_data['description']
                    role.save()
                    self.stdout.write(f'Updated role: {role.display_name}')
                else:
                    self.stdout.write(f'Role already exists: {role.display_name}')

    def create_admin_user(self, username, password, email):
        """Create the admin user with the admin role"""
        
        # Get the admin role
        try:
            admin_role = Role.objects.get(name='admin')
        except Role.DoesNotExist:
            self.stdout.write(
                self.style.ERROR('Admin role not found. Please run the role creation first.')
            )
            return
        
        # Check if admin user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(f'Admin user "{username}" already exists.')
            
            # Update existing admin user
            admin_user = User.objects.get(username=username)
            admin_user.role = admin_role
            admin_user.is_superuser = True
            admin_user.is_staff = True
            admin_user.is_active = True
            admin_user.email = email
            admin_user.save()
            
            self.stdout.write(f'Updated existing admin user: {username}')
        else:
            # Create new admin user
            admin_user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name='System',
                last_name='Administrator',
            )
            
            # Set admin properties
            admin_user.role = admin_role
            admin_user.is_superuser = True
            admin_user.is_staff = True
            admin_user.is_active = True
            admin_user.save()
            
            self.stdout.write(f'Created admin user: {username}')
        
        # Display login information
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== LOGIN INFORMATION ==='))
        self.stdout.write(f'Username: {username}')
        self.stdout.write(f'Password: {password}')
        self.stdout.write(f'Email: {email}')
        self.stdout.write('')
        self.stdout.write(
            self.style.WARNING(
                'IMPORTANT: Please change the admin password after first login for security.'
            )
        )