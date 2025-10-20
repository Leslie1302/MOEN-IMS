"""
Script to check which items from the Excel file are missing from the inventory
"""
import sqlite3
import pandas as pd

# Items from the uploaded Excel file
excel_items = [
    "HV Fuse",
    "11kV T Poles",
    "33kV Voltage Level",
    "11kV Voltage Level",
    "33kV Pin Insulators c/w Spindle",
    "11kV Pin Insulators c/w Spindle",
    "33kV Binding Stirrup",
    "11kV Binding Stirrup",
    "PG Binding wire",
    "Cu Binding wire",
    "11kV Angle Iron Crossarm c/w Straps",
    "33kV Angle Iron Crossarm c/w Straps",
    "MX2kil",
    "MX28P",
    "MX34D",
    "M1622D",
    "Stay Equipment",
    "Stay Wire",
    "Stay Equipment Complete",
    "Stay Insulators",
    "Wooden stay block",
    "Strain Insulators",
    "2core Tramble-Sec Domplex CABO1 ind. 2.5",
    "Cu Earthing Conductor",
    "Al Earthing Conductor",
    "Al Earthing Conductor",
    "Al clamps for Sleqpin",
    "Cu clamps for 28qpin",
    "Cu clamps for 70qpin",
    "33/2kVA, 1-ph",
    "33/0.4kV0.6kVA, 3-ph",
    "33/0.433, 0.6kVA, 3-ph",
    "33/0.433, 50kVA, 3-ph",
    "33/0.433, 200kVA, 3-ph",
    "11/0.4.1kV2.kV25, 3-ph",
    "129 sq mm HD AL Conductor",
    "30 sq mm HD AL Conductor",
    "70 sq mm HD OD conductor",
    "35 sq mm IHD conductor",
    "11kV Load Isolators c/w Steelworks",
    "33kV Dropout Fuse Links",
    "33kV Expulsion Fuseline-3A",
    "33kV Expulsion Fuseline-10A",
    "11kV Expulsion Fuseline-3A",
    "11kV Expulsion Fuseline-10A",
    "33kV Fuse links-5 Amps",
    "33kV Fuse links-10 Amps",
    "11kV Fuse links-10 Amps",
    "11kV Fuse links-2.5 Amps",
]

# Connect to the database
db_path = r"c:\Users\Nii\Documents\GitHub\MOEN-IMS\IMS\Inventory_management_system\db.sqlite3"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all inventory items from database
cursor.execute("SELECT name FROM Inventory_inventoryitem")
db_items = [row[0] for row in cursor.fetchall()]

print("=" * 80)
print("INVENTORY ITEMS COMPARISON")
print("=" * 80)
print(f"\nTotal items in Excel file: {len(set(excel_items))}")
print(f"Total items in database: {len(db_items)}")

# Find missing items (case-insensitive comparison)
db_items_lower = {item.lower().strip() for item in db_items}
missing_items = []
found_items = []

for excel_item in set(excel_items):
    excel_item_clean = excel_item.strip()
    if excel_item_clean.lower() not in db_items_lower:
        missing_items.append(excel_item_clean)
    else:
        found_items.append(excel_item_clean)

# Close connection
conn.close()

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"✓ Found in inventory: {len(found_items)} items")
print(f"✗ Missing from inventory: {len(missing_items)} items")
print(f"Coverage: {len(found_items) / len(set(excel_items)) * 100:.1f}%")

print("\n" + "=" * 80)
print(f"❌ MISSING ITEMS THAT NEED TO BE ADDED ({len(missing_items)} items)")
print("=" * 80)
if missing_items:
    print("\nThese items from your Excel file do NOT exist in the inventory database:")
    print("You need to add them before they can be requested.\n")
    for i, item in enumerate(sorted(missing_items), 1):
        print(f"  {i:2d}. {item}")
    print("\n" + "-" * 80)
    print("Copy this list to add these items to your inventory system.")
else:
    print("✓ All items from Excel file exist in the inventory!")
    print("You can proceed with the bulk upload.")
