#!/usr/bin/env python
"""
Script to update existing MaterialTransport records to use processed quantities
Run this with: python manage.py shell < update_transport_quantities.py
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
django.setup()

from Inventory.models import MaterialTransport, MaterialOrder

def update_transport_quantities():
    """Update existing MaterialTransport records to use processed quantities"""
    
    print("🔄 Starting transport quantity update...")
    
    # Get all transport records
    transports = MaterialTransport.objects.all()
    updated_count = 0
    
    for transport in transports:
        if transport.material_order:
            # Get the processed quantity (or fall back to full quantity)
            processed_qty = transport.material_order.processed_quantity or transport.material_order.quantity
            
            # Only update if the current quantity is different from processed quantity
            if transport.quantity != processed_qty:
                old_qty = transport.quantity
                transport.quantity = processed_qty
                
                # Save without triggering the auto-populate logic
                super(MaterialTransport, transport).save()
                
                print(f"✅ Updated Transport {transport.id}: {old_qty} → {processed_qty} {transport.unit}")
                updated_count += 1
            else:
                print(f"⏭️  Transport {transport.id}: Already correct ({transport.quantity} {transport.unit})")
    
    print(f"\n🎉 Update complete! Updated {updated_count} transport records.")
    
    # Show summary of current state
    print("\n📊 Current Transport Summary:")
    for transport in MaterialTransport.objects.all()[:5]:  # Show first 5
        material_qty = transport.material_order.quantity if transport.material_order else "N/A"
        processed_qty = transport.material_order.processed_quantity if transport.material_order else "N/A"
        print(f"   Transport {transport.id}: {transport.quantity} (Material: {material_qty}, Processed: {processed_qty})")

if __name__ == "__main__":
    update_transport_quantities()
