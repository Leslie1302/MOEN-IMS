#!/usr/bin/env python
"""
Diagnostic script to check current quantities in the database
Run this with: python manage.py shell < check_quantities.py
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
django.setup()

from Inventory.models import MaterialTransport, MaterialOrder

def check_quantities():
    """Check current quantities in MaterialOrder and MaterialTransport records"""
    
    print("🔍 Checking current quantities in the database...\n")
    
    # Check MaterialOrder records
    print("📦 MATERIAL ORDERS:")
    orders = MaterialOrder.objects.all()[:5]  # First 5 orders
    for order in orders:
        print(f"   Order {order.id} ({order.name}):")
        print(f"      Requested: {order.quantity} {order.unit}")
        print(f"      Processed: {order.processed_quantity} {order.unit}")
        print(f"      Status: {order.status}")
        print()
    
    # Check MaterialTransport records
    print("🚛 MATERIAL TRANSPORTS:")
    transports = MaterialTransport.objects.all()[:5]  # First 5 transports
    for transport in transports:
        if transport.material_order:
            print(f"   Transport {transport.id} (Order: {transport.material_order.id}):")
            print(f"      Transport Qty: {transport.quantity} {transport.unit}")
            print(f"      Material Requested: {transport.material_order.quantity} {transport.material_order.unit}")
            print(f"      Material Processed: {transport.material_order.processed_quantity} {transport.material_order.unit}")
            
            # Check if partial fulfillment should show
            if transport.material_order.processed_quantity:
                is_partial = transport.quantity < transport.material_order.quantity
                print(f"      Should show partial: {is_partial}")
            print()
    
    # Summary
    total_orders = MaterialOrder.objects.count()
    total_transports = MaterialTransport.objects.count()
    orders_with_processed = MaterialOrder.objects.exclude(processed_quantity__isnull=True).count()
    
    print(f"📊 SUMMARY:")
    print(f"   Total Orders: {total_orders}")
    print(f"   Orders with processed_quantity: {orders_with_processed}")
    print(f"   Total Transports: {total_transports}")

if __name__ == "__main__":
    check_quantities()
