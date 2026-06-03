"""
Management command to verify supplier prices were populated correctly.
"""

from django.core.management.base import BaseCommand
from Inventory.models import Supplier, InventoryItem
from Inventory.models.suppliers import SupplierPriceCatalog


class Command(BaseCommand):
    help = 'Check supplier price catalogue data'

    def handle(self, *args, **options):
        suppliers = Supplier.objects.filter(is_active=True)
        materials = InventoryItem.objects.all()

        self.stdout.write(f'\n✓ Active Suppliers: {suppliers.count()}')
        self.stdout.write(f'✓ Materials: {materials.count()}')

        price_count = SupplierPriceCatalog.objects.count()
        self.stdout.write(f'✓ Total Prices: {price_count}')

        if price_count == 0:
            self.stdout.write(self.style.ERROR('\n✗ No prices found! Run: python manage.py populate_supplier_prices'))
            return

        # Show sample prices
        self.stdout.write('\n📋 Sample Prices:')
        samples = SupplierPriceCatalog.objects.select_related('supplier', 'material')[:10]
        for price in samples:
            self.stdout.write(
                f'  {price.supplier.name} → {price.material.name}: '
                f'{price.currency} {price.unit_rate} (Active: {price.is_active})'
            )

        # Check for materials missing prices
        self.stdout.write('\n🔍 Materials with no prices:')
        missing = 0
        for material in materials[:5]:  # Check first 5
            has_price = SupplierPriceCatalog.objects.filter(
                material=material,
                is_active=True
            ).exists()
            if not has_price:
                self.stdout.write(f'  ✗ {material.name}')
                missing += 1

        if missing == 0:
            self.stdout.write(self.style.SUCCESS('  ✓ All checked materials have prices'))

        self.stdout.write('\n' + self.style.SUCCESS('✓ Price catalogue check complete!'))
