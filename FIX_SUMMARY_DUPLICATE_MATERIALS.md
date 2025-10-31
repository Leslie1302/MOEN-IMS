# Fix: Multiple Warehouse Support for Same Materials

## Problem
**Error**: `InventoryItem.MultipleObjectsReturned: get() returned more than one InventoryItem -- it returned 2!`

**Root Cause**: The system was trying to look up materials by name only, but the database correctly allows the same material to exist in multiple warehouses (enforced by `unique_together=['code', 'warehouse']`).

When a user tried to add a material request for "Material X" that existed in both Warehouse A and Warehouse B, the form failed with a `MultipleObjectsReturned` error.

## Solution Overview
Changed the material lookup mechanism from **name-based** to **ID-based** (primary key), with warehouse-aware lookup. Users select a material from the dropdown and choose a warehouse, then the system uses both to find the specific inventory item.

## Changes Made

### 1. Forms (`forms.py`)
**MaterialOrderForm** and **MaterialReceiptForm**:
- **Removed** `to_field_name="name"` parameter
- Now uses primary key (ID) for lookups instead of name
- Django automatically handles the lookup by ID

### 2. Model Display (`models.py`)
**InventoryItem.__str__**:
- Kept simple: Returns just the material name
- Warehouse selection on the form determines which specific item
- System uses material name + warehouse to find the right inventory item

### 3. View Handlers (`views.py`)
Updated both request and receipt handlers to use warehouse-aware lookup:
```python
# BEFORE (Wrong):
selected_item = InventoryItem.objects.filter(name=form.cleaned_data['name']).first()

# AFTER (Correct):
selected_item = form.cleaned_data['name']  # InventoryItem object from form
selected_warehouse = form.cleaned_data.get('warehouse')

# Look up specific item by material name + warehouse
if selected_item and selected_warehouse:
    inventory_item = InventoryItem.objects.get(
        name=selected_item.name,
        warehouse=selected_warehouse
    )
    material_order.code = inventory_item.code
    material_order.category = inventory_item.category
    # etc.
```

### 4. JavaScript Templates
Updated 3 template files to lookup by ID:
- `request_material.html`
- `receive_material.html`
- `material_receipt.html`

Changed autofill logic:
```javascript
// BEFORE:
const item = inventoryItems.find(i => i.name === selectedName);

// AFTER:
const item = inventoryItems.find(i => i.id == selectedId);
```

### 5. JSON Data
Updated all view methods to include `id` and `warehouse__name` in inventory data:
```python
inventory_items = list(items.values('id', 'name', 'category__name', 'unit__name', 'code', 'warehouse__name'))
```

## Files Modified

1. `/Inventory/forms.py` - MaterialOrderForm, MaterialReceiptForm
2. `/Inventory/models.py` - InventoryItem.__str__()
3. `/Inventory/views.py` - RequestMaterialView, MaterialReceiptView (6 locations)
4. `/Inventory/templates/Inventory/request_material.html`
5. `/Inventory/templates/Inventory/receive_material.html`
6. `/Inventory/templates/Inventory/material_receipt.html`

## Impact

### ✅ Benefits
- Users can now add materials that exist in other warehouses without errors
- Warehouse field on form determines which specific inventory item is used
- System automatically looks up correct item based on material name + warehouse
- Maintains database integrity with `unique_together=['code', 'warehouse']`
- No data migration needed

### ⚠️ Note
The lint errors about Django template syntax (`{{ inventory_items|safe }}`) in JavaScript are **false positives** and can be ignored. They occur because the IDE doesn't recognize Django template tags.

## Testing Steps

1. **Create duplicate materials**:
   - Add "Cement" to "Accra Warehouse" with code "CEM-ACC-001"
   - Add "Cement" to "Kumasi Warehouse" with code "CEM-KUM-001"
   - Both have same name, different warehouses and codes

2. **Test material request**:
   - Go to `/request-material/`
   - Select "Cement" from material dropdown (may appear multiple times)
   - Select "Accra Warehouse" from warehouse dropdown
   - Submit form successfully
   - System should use code "CEM-ACC-001" from Accra warehouse

3. **Verify warehouse-specific lookup**:
   - Create another request with "Cement"
   - Select "Kumasi Warehouse" this time
   - System should use code "CEM-KUM-001" from Kumasi warehouse
   - Category, code, and unit auto-populate based on selected warehouse

## Database Schema
```
InventoryItem:
  - code (unique with warehouse)
  - warehouse (ForeignKey)
  - unique_together = ['code', 'warehouse']
```

This allows:
- Same material name in different warehouses ✅
- Different codes per warehouse (optional) ✅
- Prevents duplicate code+warehouse combinations ✅
