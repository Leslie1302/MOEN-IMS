#!/usr/bin/env python
"""
Script to check for duplicate material codes in the inventory before applying the unique constraint.
"""
import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Inventory_management_system'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
django.setup()

from Inventory.models import InventoryItem
from django.db.models import Count

def check_duplicates():
    """Check for duplicate code+warehouse combinations in the database."""
    print("Checking for duplicate code+warehouse combinations...")
    print("=" * 60)
    
    # Find duplicate code+warehouse combinations
    duplicates = (
        InventoryItem.objects
        .values('code', 'warehouse')
        .annotate(count=Count('id'))
        .filter(count__gt=1)
        .order_by('-count')
    )
    
    if not duplicates:
        print("✓ No duplicate code+warehouse combinations found!")
        print("  You can safely apply the migration.")
        return True
    
    print(f"⚠ Found {len(duplicates)} duplicate code+warehouse combination(s):\n")
    
    for dup in duplicates:
        code = dup['code']
        warehouse_id = dup['warehouse']
        count = dup['count']
        
        from Inventory.models import Warehouse
        warehouse_name = Warehouse.objects.get(id=warehouse_id).name if warehouse_id else "No Warehouse"
        
        print(f"  Code: '{code}' + Warehouse: '{warehouse_name}' appears {count} times")
        
        # Show the items with this combination
        items = InventoryItem.objects.filter(code=code, warehouse_id=warehouse_id)
        for item in items:
            print(f"    - ID: {item.id}, Name: {item.name}, Quantity: {item.quantity}")
        print()
    
    print("\n" + "=" * 60)
    print("ACTION REQUIRED:")
    print("  You must resolve these duplicates before applying the migration.")
    print("  Options:")
    print("  1. Change warehouse or code for duplicate entries")
    print("  2. Delete duplicate entries")
    print("  3. Merge duplicate items into one")
    print("=" * 60)
    
    return False

if __name__ == '__main__':
    check_duplicates()
