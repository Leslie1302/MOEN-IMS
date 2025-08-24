from django.core.management.base import BaseCommand
from Inventory.models import Warehouse


class Command(BaseCommand):
    help = 'Set up default warehouses for the inventory management system'

    def handle(self, *args, **options):
        self.stdout.write('Setting up default warehouses...')
        
        # Default warehouses data
        warehouses_data = [
            {
                'name': 'Main Warehouse',
                'code': 'MW-001',
                'location': 'Accra Central, Ghana',
                'contact_person': 'Warehouse Manager',
                'contact_phone': '+233 20 123 4567',
                'contact_email': 'warehouse@moen-ims.com',
                'notes': 'Primary warehouse for construction materials and equipment'
            },
            {
                'name': 'Northern Regional Warehouse',
                'code': 'NRW-001',
                'location': 'Tamale, Northern Region, Ghana',
                'contact_person': 'Regional Supervisor',
                'contact_phone': '+233 20 234 5678',
                'contact_email': 'northern.warehouse@moen-ims.com',
                'notes': 'Regional warehouse serving Northern Ghana projects'
            },
            {
                'name': 'Western Regional Warehouse',
                'code': 'WRW-001',
                'location': 'Takoradi, Western Region, Ghana',
                'contact_person': 'Regional Supervisor',
                'contact_phone': '+233 20 345 6789',
                'contact_email': 'western.warehouse@moen-ims.com',
                'notes': 'Regional warehouse serving Western Ghana projects'
            },
            {
                'name': 'Eastern Regional Warehouse',
                'code': 'ERW-001',
                'location': 'Koforidua, Eastern Region, Ghana',
                'contact_person': 'Regional Supervisor',
                'contact_phone': '+233 20 456 7890',
                'contact_email': 'eastern.warehouse@moen-ims.com',
                'notes': 'Regional warehouse serving Eastern Ghana projects'
            },
            {
                'name': 'Ashanti Regional Warehouse',
                'code': 'ARW-001',
                'location': 'Kumasi, Ashanti Region, Ghana',
                'contact_person': 'Regional Supervisor',
                'contact_phone': '+233 20 567 8901',
                'contact_email': 'ashanti.warehouse@moen-ims.com',
                'notes': 'Regional warehouse serving Ashanti Region projects'
            }
        ]
        
        created_warehouses = []
        
        for warehouse_data in warehouses_data:
            warehouse, created = Warehouse.objects.get_or_create(
                code=warehouse_data['code'],
                defaults=warehouse_data
            )
            
            if created:
                self.stdout.write(f'✅ Created warehouse: {warehouse.name} ({warehouse.code})')
            else:
                self.stdout.write(f'ℹ️  Warehouse already exists: {warehouse.name} ({warehouse.code})')
            
            created_warehouses.append(warehouse)
        
        self.stdout.write(f'\n🎉 Successfully set up {len(created_warehouses)} warehouses!')
        self.stdout.write('\nWarehouses created:')
        for warehouse in created_warehouses:
            self.stdout.write(f'  • {warehouse.name} - {warehouse.code}')
            self.stdout.write(f'    Location: {warehouse.location}')
            self.stdout.write(f'    Contact: {warehouse.contact_person}')
            self.stdout.write('')
        
        self.stdout.write('\nTo add more warehouses, use the Django admin interface or run:')
        self.stdout.write('python manage.py shell')
        self.stdout.write('Then in the shell:')
        self.stdout.write('from Inventory.models import Warehouse')
        self.stdout.write('warehouse = Warehouse.objects.create(name="New Warehouse", code="NW-001", location="Location")')
