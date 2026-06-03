"""
Management command to populate supplier price catalogue with sample data.
Creates realistic pricing for existing suppliers and materials.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from decimal import Decimal
from datetime import timedelta

from Inventory.models import Supplier, InventoryItem, Warehouse
from Inventory.models.suppliers import SupplierPriceCatalog


class Command(BaseCommand):
    help = 'Populate supplier price catalogue with sample data'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting price catalogue population...'))

        # Get all suppliers and materials
        suppliers = Supplier.objects.filter(is_active=True)
        materials = InventoryItem.objects.all()
        warehouses = Warehouse.objects.filter(is_active=True)

        if not suppliers.exists():
            self.stdout.write(self.style.ERROR('No active suppliers found. Please create suppliers first.'))
            return

        if not materials.exists():
            self.stdout.write(self.style.ERROR('No materials found. Please upload materials first.'))
            return

        # Sample pricing data (material name -> base price)
        base_prices = {
            'Gravel': Decimal('150.00'),
            'Sand': Decimal('120.00'),
            'Cement': Decimal('45.00'),
            'Steel Bar': Decimal('320.00'),
            'Pole': Decimal('500.00'),
            'Wire': Decimal('25.00'),
            'Pipe': Decimal('85.00'),
            'Plywood': Decimal('180.00'),
            'Nail': Decimal('5.00'),
            'Paint': Decimal('95.00'),
        }

        created_count = 0
        skipped_count = 0

        # Create prices for each supplier-material combination
        for supplier in suppliers:
            for material in materials:
                # Check if price already exists
                existing = SupplierPriceCatalog.objects.filter(
                    supplier=supplier,
                    material=material
                ).exists()

                if existing:
                    skipped_count += 1
                    continue

                # Get base price from mapping, or calculate from material name
                base_price = base_prices.get(material.name)
                if not base_price:
                    # Random pricing based on material name length
                    base_price = Decimal(str(50 + (len(material.name) * 2)))

                # Vary price by supplier (add some variation)
                supplier_variation = Decimal(str(0.8 + (hash(supplier.code) % 40) / 100))
                unit_rate = base_price * supplier_variation

                # Create price record
                try:
                    SupplierPriceCatalog.objects.create(
                        supplier=supplier,
                        material=material,
                        unit_rate=unit_rate,
                        currency='GHS',
                        effective_date=timezone.now().date(),
                        expiry_date=timezone.now().date() + timedelta(days=365),
                        minimum_order_quantity=1,
                        warehouse=warehouses.first() if warehouses.exists() else None,
                        lead_time_days=5 + (hash(supplier.code) % 10),
                        notes=f'Standard pricing from {supplier.name}',
                        is_active=True
                    )
                    created_count += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Error creating price for {supplier.name} - {material.name}: {str(e)}'
                        )
                    )
                    skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Populated price catalogue successfully!'
                f'\n  Created: {created_count} price records'
                f'\n  Skipped: {skipped_count} (already exist)'
            )
        )
