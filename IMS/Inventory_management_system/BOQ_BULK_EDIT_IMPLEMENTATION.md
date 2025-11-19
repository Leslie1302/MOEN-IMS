# Bill of Quantities Bulk Edit Implementation

## Overview
This implementation adds bulk editing functionality to the Bill of Quantities (BOQ) table, allowing superusers to edit multiple BOQ items at once. The site logs continue to automatically populate the `quantity_received` field.

## Features Implemented

### 1. **Actions Column with Checkboxes**
- Added a checkbox column at the beginning of the BOQ table
- Added an Actions column with individual "Edit" buttons for each item
- Only visible to superusers
- "Select All" checkbox to quickly select/deselect all items on the current page

### 2. **Bulk Edit Functionality**
- **Bulk Edit Button**: Appears at the top of the table, showing the count of selected items
- Button is disabled until at least one item is selected
- Clicking the button takes you to a bulk edit page where you can edit all selected items at once

### 3. **Single Item Edit**
- Individual edit button for each BOQ item in the Actions column
- Opens a dedicated edit page for that single item

### 4. **Edit Pages**
Both bulk and single edit pages include:
- All BOQ fields organized into logical sections:
  - Location Information (Region, District, Community)
  - Project Details (Consultant, Contractor, Package Number)
  - Material Information (Material Description, Item Code)
  - Quantities & Warehouse (Contract Quantity, Quantity Received, Warehouse)
- Real-time balance display showing current balance and overissuance warnings
- Form validation with error messages
- Cancel and Save buttons
- Unsaved changes warning if you try to leave the page

### 5. **Site Logs Integration**
- Site logs continue to automatically update the `quantity_received` field
- The system maintains the automatic BOQ updates when Site Receipts are created
- Manual edits are possible but the field includes a warning note

## Files Created/Modified

### New Files:
1. **`Inventory/boq_views.py`**: Contains the bulk edit and single edit views
   - `BulkEditBOQView`: Handles bulk editing of multiple BOQ items
   - `SingleEditBOQView`: Handles editing of a single BOQ item

2. **`Inventory/templates/Inventory/boq_bulk_edit.html`**: Template for bulk editing
   - Shows all selected BOQ items in a formset
   - Organized card-based layout for easy editing

3. **`Inventory/templates/Inventory/boq_single_edit.html`**: Template for single item editing
   - Clean, sectioned layout with balance information
   - Visual indicators for overissuance

### Modified Files:
1. **`Inventory/forms.py`**:
   - Added `BillOfQuantity` to imports
   - Created `BillOfQuantityForm` with all editable fields
   - Created `BillOfQuantityFormSet` using modelformset_factory

2. **`Inventory/urls.py`**:
   - Imported BOQ views
   - Added routes:
     - `/bill-of-quantity/bulk-edit/` → Bulk edit page
     - `/bill-of-quantity/<id>/edit/` → Single item edit page

3. **`Inventory/templates/Inventory/bill_of_quantity.html`**:
   - Added checkbox column (superuser only)
   - Added Actions column with Edit button (superuser only)
   - Added "Bulk Edit Selected" button with counter
   - Added JavaScript for checkbox selection and form handling
   - "Select All" functionality that respects filtered rows

## Usage Instructions

### For Superusers:

#### Bulk Edit:
1. Navigate to the Bill of Quantity page
2. Select the items you want to edit by checking the checkboxes
3. Click the "Bulk Edit Selected (X)" button at the top
4. Edit the fields for each selected item
5. Click "Save All Changes" to save all modifications at once

#### Single Item Edit:
1. Navigate to the Bill of Quantity page
2. Click the pencil icon (Edit button) in the Actions column for the item you want to edit
3. Make your changes
4. Click "Save Changes"

#### Quick Selection:
- Use the "Select All" checkbox in the table header to select/deselect all visible items
- The selection respects any filters you've applied to the table

## Technical Details

### Security:
- Only superusers can access the edit functionality
- Uses Django's `UserPassesTestMixin` for permission checking
- CSRF protection enabled on all forms

### Data Integrity:
- Form validation ensures data consistency
- Transaction-based saves ensure all-or-nothing bulk updates
- Site logs continue to update `quantity_received` automatically
- Balance is calculated dynamically (contract_quantity - quantity_received)

### User Experience:
- Real-time counter shows how many items are selected
- Bulk edit button is disabled when no items are selected
- Unsaved changes warning prevents accidental data loss
- Error messages scroll into view automatically
- Sticky save buttons for easy access when editing many items

### Pagination Support:
- Checkboxes and bulk edit work across pagination
- Can select items from different pages and edit them together

## Database Changes
**No database migrations required** - This implementation uses existing database structures.

## Compatibility
- Works with the existing Bill of Quantity workflow
- Site Receipt automatic updates continue to function normally
- No breaking changes to existing functionality
- Fully compatible with the overissuance tracking system

## Future Enhancements (Optional)
1. Add ability to bulk delete BOQ items
2. Add filtering/search on the bulk edit page
3. Add "Edit All Visible" button to edit all filtered items
4. Export selected items to Excel
5. Add audit logging for BOQ edits

## Notes
- The `quantity_received` field includes a warning that it's automatically updated by site logs
- Superusers can still manually edit this field if needed (e.g., for data corrections)
- The balance is calculated in real-time and displayed on edit pages
- Overissuance warnings are prominently displayed on edit pages

