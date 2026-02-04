from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from Inventory.models import MaterialOrder, MaterialTransport, ReleaseLetter, SiteReceipt, BillOfQuantity


class Command(BaseCommand):
    help = 'Set up user groups and permissions for the inventory management system'

    def handle(self, *args, **options):
        self.stdout.write('Setting up user groups and permissions...')
        
        # Create groups
        groups_data = [
            {
                'name': 'Schedule Officer',
                'description': 'Users who can request materials and view orders',
                'permissions': [
                    'add_materialorder',
                    'change_materialorder',
                    'view_materialorder',
                    'view_materialtransport',
                    'view_sitereceipt',
                ]
            },
            {
                'name': 'Store Officer',
                'description': 'Users who manage inventory and process orders',
                'permissions': [
                    'add_materialorder',
                    'change_materialorder',
                    'view_materialorder',
                    'add_materialtransport',
                    'change_materialtransport',
                    'view_materialtransport',
                    'add_releaseletter',
                    'change_releaseletter',
                    'view_releaseletter',
                    'add_sitereceipt',
                    'change_sitereceipt',
                    'view_sitereceipt',
                ]
            },
            {
                'name': 'Transport Officer',
                'description': 'Users who manage transportation and logistics',
                'permissions': [
                    'view_materialorder',
                    'add_materialtransport',
                    'change_materialtransport',
                    'view_materialtransport',
                    'view_releaseletter',
                    'view_sitereceipt',
                ]
            },
            {
                'name': 'Consultant',
                'description': 'Users who work on site and log receipts',
                'permissions': [
                    'view_materialorder',
                    'view_materialtransport',
                    'add_sitereceipt',
                    'change_sitereceipt',
                    'view_sitereceipt',
                ]
            },
            {
                'name': 'Management',
                'description': 'Users with management oversight and reporting access',
                'permissions': [
                    'view_materialorder',
                    'view_materialtransport',
                    'view_releaseletter',
                    'view_sitereceipt',
                    'view_billofquantity',
                    'add_billofquantity',
                    'change_billofquantity',
                ]
            },
        ]
        
        created_groups = []
        
        for group_data in groups_data:
            group, created = Group.objects.get_or_create(name=group_data['name'])
            
            if created:
                self.stdout.write(f'✅ Created group: {group.name}')
            else:
                self.stdout.write(f'ℹ️  Group already exists: {group.name}')
            
            # Get permissions
            permissions = []
            for perm_name in group_data['permissions']:
                try:
                    # Try to get permission by codename
                    if 'billofquantity' in perm_name:
                        content_type = ContentType.objects.get_for_model(BillOfQuantity)
                    elif 'materialorder' in perm_name:
                        content_type = ContentType.objects.get_for_model(MaterialOrder)
                    elif 'materialtransport' in perm_name:
                        content_type = ContentType.objects.get_for_model(MaterialTransport)
                    elif 'releaseletter' in perm_name:
                        content_type = ContentType.objects.get_for_model(ReleaseLetter)
                    elif 'sitereceipt' in perm_name:
                        content_type = ContentType.objects.get_for_model(SiteReceipt)
                    else:
                        continue
                    
                    permission = Permission.objects.get(
                        content_type=content_type,
                        codename=perm_name
                    )
                    permissions.append(permission)
                except Permission.DoesNotExist:
                    self.stdout.write(f'⚠️  Permission not found: {perm_name}')
                    continue
            
            # Assign permissions to group
            group.permissions.set(permissions)
            self.stdout.write(f'   Assigned {len(permissions)} permissions to {group.name}')
            
            created_groups.append(group)
        
        self.stdout.write(f'\n🎉 Successfully set up {len(created_groups)} groups!')
        self.stdout.write('\nGroups created:')
        for group in created_groups:
            self.stdout.write(f'  • {group.name} - {group.permissions.count()} permissions')
        
        self.stdout.write('\nTo assign users to groups, use the Django admin interface or run:')
        self.stdout.write('python manage.py shell')
        self.stdout.write('Then in the shell:')
        self.stdout.write('from django.contrib.auth.models import User, Group')
        self.stdout.write('user = User.objects.get(username="your_username")')
        self.stdout.write('group = Group.objects.get(name="Schedule Officer")')
        self.stdout.write('user.groups.add(group)')
