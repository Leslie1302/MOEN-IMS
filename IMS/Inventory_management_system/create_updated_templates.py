#!/usr/bin/env python
"""
Script to create updated Excel templates for BOQ and Material Orders
WITHOUT the community field (package-based tracking only)
"""

import pandas as pd
from pathlib import Path

# Get the script directory
base_dir = Path(__file__).parent

# Create BOQ Template (without community field)
boq_template_data = {
    'region': ['Northern', 'Greater Accra'],
    'district': ['Tamale Metropolitan', 'Accra Metropolitan'],
    'consultant': ['ABC Consultants', 'XYZ Engineering'],
    'contractor': ['BuildCo Ltd', 'ConstructPro'],
    'package_number': ['PKG-001', 'PKG-002'],
    'material_description': ['Concrete Poles', 'Steel Wires'],
    'contract_quantity': [1000, 500],
    'quantity_received': [0, 0]
}

boq_df = pd.DataFrame(boq_template_data)
boq_template_path = base_dir / 'boq_upload_template.xlsx'
boq_df.to_excel(boq_template_path, index=False, sheet_name='Bill of Quantity')
print(f"✅ Created BOQ template: {boq_template_path}")

# Create Material Order Bulk Request Template (without community field)
material_order_data = {
    'name': ['Concrete Poles', 'Steel Wires'],
    'quantity': [50, 100],
    'region': ['Northern', 'Greater Accra'],
    'district': ['Tamale Metropolitan', 'Accra Metropolitan'],
    'consultant': ['ABC Consultants', 'XYZ Engineering'],
    'contractor': ['BuildCo Ltd', 'ConstructPro'],
    'package_number': ['PKG-001', 'PKG-002'],
    'warehouse': ['Main Warehouse', 'Regional Store']
}

material_order_df = pd.DataFrame(material_order_data)
material_order_template_path = base_dir / 'bulk_request_template_updated.xlsx'
material_order_df.to_excel(material_order_template_path, index=False, sheet_name='Material Requests')
print(f"✅ Created Material Order template: {material_order_template_path}")

# Create Contract Package Template (NEW - for managing community lists)
contract_package_data = {
    'package_number': ['PKG-001', 'PKG-002'],
    'project_name': ['Rural Electrification Phase 1', 'Urban Grid Expansion'],
    'region': ['Northern', 'Greater Accra'],
    'district': ['Tamale Metropolitan', 'Accra Metropolitan'],
    'communities': ['Community A, Community B, Community C', 'Community X, Community Y'],
    'consultant': ['ABC Consultants', 'XYZ Engineering'],
    'contractor': ['BuildCo Ltd', 'ConstructPro'],
    'contract_value': [500000.00, 750000.00],
    'start_date': ['2024-01-01', '2024-02-01'],
    'end_date': ['2024-12-31', '2025-01-31'],
    'status': ['Active', 'Active'],
    'notes': ['Phase 1 implementation', 'City expansion project']
}

contract_package_df = pd.DataFrame(contract_package_data)
contract_package_template_path = base_dir / 'contract_package_template.xlsx'
contract_package_df.to_excel(contract_package_template_path, index=False, sheet_name='Contract Packages')
print(f"✅ Created Contract Package template: {contract_package_template_path}")

print("\n" + "="*60)
print("TEMPLATE CREATION SUMMARY")
print("="*60)
print("\n📋 BOQ Template Columns:")
print("   - region, district, consultant, contractor")
print("   - package_number, material_description")
print("   - contract_quantity, quantity_received")
print("   ❌ REMOVED: community")
print("\n📦 Material Order Template Columns:")
print("   - name, quantity, region, district")
print("   - consultant, contractor, package_number, warehouse")
print("   ❌ REMOVED: community")
print("\n🏢 Contract Package Template Columns (NEW):")
print("   - package_number, project_name, region, district")
print("   - communities (comma-separated list)")
print("   - consultant, contractor, contract_value")
print("   - start_date, end_date, status, notes")
print("\n" + "="*60)
print("✨ All templates created successfully!")
print("="*60)
