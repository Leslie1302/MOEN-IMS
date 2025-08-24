from django.core.management.base import BaseCommand
import pandas as pd
from io import BytesIO
from django.http import HttpResponse
import os

class Command(BaseCommand):
    help = 'Create a sample Excel template for inventory uploads'

    def handle(self, *args, **options):
        self.stdout.write('Creating sample inventory Excel template...')
        
        # Sample data for the template
        sample_data = {
            'name': [
                'Portland Cement',
                'Steel Reinforcement Bars',
                'Sand',
                'Gravel',
                'Timber Planks'
            ],
            'quantity': [
                1000,
                500,
                2000,
                1500,
                800
            ],
            'category': [
                'Construction Materials',
                'Steel Products',
                'Aggregates',
                'Aggregates',
                'Timber Products'
            ],
            'code': [
                'CEM-001',
                'STEEL-001',
                'SAND-001',
                'GRAVEL-001',
                'TIMBER-001'
            ],
            'unit': [
                'Bags',
                'Tons',
                'Cubic Meters',
                'Cubic Meters',
                'Pieces'
            ],
            'warehouse': [
                'Main Warehouse',
                'Main Warehouse',
                'Northern Regional Warehouse',
                'Western Regional Warehouse',
                'Eastern Regional Warehouse'
            ]
        }
        
        # Create DataFrame
        df = pd.DataFrame(sample_data)
        
        # Create output directory if it doesn't exist
        output_dir = 'sample_templates'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Save as Excel file
        output_file = os.path.join(output_dir, 'sample_inventory_template.xlsx')
        df.to_excel(output_file, index=False, sheet_name='Inventory Template')
        
        self.stdout.write(f'✅ Sample template created: {output_file}')
        self.stdout.write('\n📋 Template includes the following columns:')
        for col in df.columns:
            self.stdout.write(f'  • {col}')
        
        self.stdout.write('\n📝 Sample data includes:')
        for i, row in df.iterrows():
            self.stdout.write(f'  • {row["name"]} - {row["quantity"]} {row["unit"]} at {row["warehouse"]}')
        
        self.stdout.write('\n💡 Users can:')
        self.stdout.write('  1. Download this template')
        self.stdout.write('  2. Fill in their inventory data')
        self.stdout.write('  3. Upload the completed file')
        self.stdout.write('\n⚠️  Important: Warehouse names must match exactly with existing warehouses in the system.')
