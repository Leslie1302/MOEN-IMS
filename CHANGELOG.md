# MOEN Inventory Management System - Changelog

## Table of Contents
- [Recent Fixes](#recent-fixes)
- [Major Features](#major-features)
- [Bug Fixes History](#bug-fixes-history)
- [Performance Optimizations](#performance-optimizations)
- [System Architecture Changes](#system-architecture-changes)

---

## Recent Fixes

### [2025-10-31] Fix: Multiple Warehouse Support for Duplicate Materials
**Issue**: `InventoryItem.MultipleObjectsReturned` error when adding materials that exist in multiple warehouses

**Root Cause**: Form was looking up materials by name only using `to_field_name="name"`, but database allows same material in different warehouses via `unique_together=['code', 'warehouse']`

**Solution**:
- Changed form lookups from name-based to ID-based (primary key)
- Updated `InventoryItem.__str__()` to display "Material Name - Warehouse Name"
- Fixed view handlers to extract name from InventoryItem object
- Updated JavaScript in 3 templates to lookup by ID
- Added warehouse info to all inventory JSON data

**Files Modified**:
- `/Inventory/forms.py` - MaterialOrderForm, MaterialReceiptForm
- `/Inventory/models.py` - InventoryItem display
- `/Inventory/views.py` - RequestMaterialView, MaterialReceiptView
- `/Inventory/templates/Inventory/request_material.html`
- `/Inventory/templates/Inventory/receive_material.html`
- `/Inventory/templates/Inventory/material_receipt.html`

**Impact**: Users can now add materials that exist in other warehouses without errors

---

## Major Features

### 1. Bill of Quantity (BoQ) Overissuance Tracking System
**Added**: Complete workflow for tracking and justifying BoQ overissuances

**Components**:
- **Model**: `BoQOverissuanceJustification`
  - Tracks justifications with status workflow (Pending → Under Review → Approved/Rejected)
  - Categories: Design Change, Site Condition, Measurement Error, Emergency Need, Variation Order, Other
  - Custom permissions: `can_review_overissuance`, `can_view_overissuance_summary`

**Views**:
- `BoQOverissuanceSummaryView` - Projects with overissuances grouped by package_number
- `BoQOverissuanceJustificationCreateView` - Submit justification form
- `BoQOverissuanceJustificationListView` - Filterable list with status
- `BoQOverissuanceJustificationDetailView` - Full details with review functionality
- `review_overissuance_justification` - Approve/reject workflow
- `boq_overissuance_stats` - AJAX statistics endpoint

**URL Patterns**:
```
/boq/overissuance/summary/
/boq/overissuance/<boq_id>/justify/
/boq/overissuance/justifications/
/boq/overissuance/justifications/<pk>/
/boq/overissuance/justifications/<pk>/review/
/boq/overissuance/stats/
```

**Files**:
- `/Inventory/models.py` - BoQOverissuanceJustification model
- `/Inventory/forms.py` - BoQOverissuanceJustificationForm
- `/Inventory/boq_overissuance_views.py` - All views
- `/Inventory/templates/Inventory/boq_overissuance_*.html` - 4 templates
- Migration: `0012_boqoverissuancejustification.py`

### 2. Role-Based Notification System
**Added**: Comprehensive notification system reflecting all system activities

**Features**:
- Auto-notifications for material requests, processing, transport, delivery
- Role-based visibility (Schedule Officers, Storekeepers, Management, Consultants)
- Low inventory alerts (critical < 5, low < 10)
- Mark as read/unread functionality
- Global unread count badge via context processor

**Notification Types**:
- `material_request` - New material requests
- `material_processed` - Materials processed by storekeepers
- `transport_assigned` - Transport assigned
- `material_delivered` - Materials delivered
- `site_receipt_logged` - Site receipts confirmed
- `boq_updated` - BOQ entries created/updated
- `staff_prompt` - Low inventory alerts

**Files**:
- `/Inventory/signals.py` - Django signals for auto-notification
- `/Inventory/notification_views.py` - Notification management views
- `/Inventory/context_processors.py` - Global notifications context
- `/settings.py` - Context processor registration

**Endpoints**:
```
/notifications/ - List view
/notifications/<id>/ - Detail view
/notifications/<id>/mark-read/ - AJAX mark as read
/notifications/mark-all-read/ - Mark all
/notifications/unread-count/ - Get count (AJAX)
/notifications/<id>/delete/ - Delete (superuser)
```

### 3. Transporter Management & Partial Fulfillment
**Added**: Complete transporter assignment with partial order support

**Features**:
- Orders remain visible if `remaining_quantity > 0` even after partial transport
- Multiple transporters can handle different portions of same order
- Status tracking: Pending → In Transit → Delivered → Completed

**Display Logic**:
- Shows: Requested | Processed | Assigned | Pending Processing
- Assign button disabled when `remaining_transport_quantity = 0`
- Orders stay visible for subsequent partial fulfillments

**Example Scenario**:
```
Order: 1000 poles
→ Storekeeper processes 800 → processed_quantity=800, remaining=200
→ Transporter A takes 800
→ Order STILL VISIBLE showing "200 pending processing"
→ Storekeeper processes remaining 200
→ Transporter B can take the 200
```

**Files**:
- `/Inventory/transporter_views.py` - TransporterAssignmentView
- `/Inventory/templates/Inventory/transporter_assignment.html`

### 4. Release Letter Management
**Added**: PDF upload and tracking system for material release authorization

**Features**:
- Upload signed release letters linked to request codes
- Auto-approval of related material orders upon upload
- Request code grouping (base codes without row numbers)
- Validation prevents uploading for completed requests

**Files**:
- `/Inventory/models.py` - ReleaseLetter model
- `/Inventory/forms.py` - ReleaseLetterUploadForm
- `/Inventory/views.py` - Release letter handling in material requests

---

## Bug Fixes History

### [Fixed] MaterialOrder Status: 'Fulfilled' → 'Completed'
**Issue**: 500 error when completing release requests due to invalid status

**Root Cause**: 
- `MaterialOrder.save()` was setting `status='Fulfilled'` 
- 'Fulfilled' doesn't exist in `STATUS_CHOICES` (valid: 'Partially Fulfilled' or 'Completed')

**Solution**:
```python
# Changed in /Inventory/models.py line 360:
status='Fulfilled' → status='Completed'

# Also removed 'Fulfilled' from:
# - Line 357: status check list
# - Line 372: is_approved property
```

### [Fixed] Inventory Lookup by Code+Warehouse
**Issue**: `InventoryItem.MultipleObjectsReturned` when completing release requests with duplicate material names

**Root Cause**: Views were matching inventory by name only, causing errors with duplicates

**Solution**: Changed to code+warehouse lookup using `unique_together` constraint
```python
# BEFORE (WRONG):
inventory_item = InventoryItem.objects.get(name__iexact=order.name)

# AFTER (CORRECT):
if order.warehouse:
    inventory_item = InventoryItem.objects.get(
        code=order.code,
        warehouse=order.warehouse
    )
else:
    inventory_item = InventoryItem.objects.get(code=order.code)
```

**Files Modified**:
- `/Inventory/views.py` - UpdateMaterialStatusView (lines 668-708)
- `/Inventory/views.py` - update_material_receipt function (lines 2294-2312)

**Exception Handling Added**:
- `InventoryItem.DoesNotExist` - Returns 400 with clear message
- `InventoryItem.MultipleObjectsReturned` - Returns 500 asking admin to resolve

### [Fixed] Bulk Upload: Warehouse Field Missing
**Issue**: Warehouse field not populated during bulk material request uploads

**Root Cause**: Excel required 'warehouse' column but `handle_bulk_request()` wasn't extracting/saving it

**Solution**: Added warehouse lookup logic
```python
# Extract warehouse name from Excel row
# Perform case-insensitive lookup
# Assign to order_data before creating MaterialOrder
# Log warnings if not found but continue processing
```

**File Modified**: `/Inventory/views.py` - RequestMaterialView.handle_bulk_request() (lines 294-307)

**Behavior**: Warehouse names must match existing records (case-insensitive). If not found, order created with `warehouse=None` + warning logged.

### [Fixed] BoQ Upload: Strict Material Matching
**Issue**: Inconsistent material codes due to auto-generation fallback

**Root Cause**: System allowed BOQ uploads with non-existent materials, auto-generating codes like `BOQ-{DESC}-{INDEX}`

**Solution**: Enforced strict uniformity
- All `material_description` values MUST match existing InventoryItem names (case-insensitive)
- Removed auto-generation fallback completely
- Rows without matching inventory items are rejected with clear errors
- `item_code` automatically pulled from matched InventoryItem

**Impact**: Ensures data consistency across system

**File Modified**: `/Inventory/views.py` - UploadBillOfQuantityView class

---

## Performance Optimizations

### [Implemented] N+1 Query Optimization with django-auto-prefetch
**Problem**: Severe performance degradation with large datasets
- Material orders list (100 records) generated 500+ queries
- Each access to `order.user.username`, `order.category.name`, etc. triggered separate queries
- Page load times: 3-5 seconds

**Solution**: Implemented `django-auto-prefetch` package
- Automatically detects ForeignKey access in loops
- Batches related object fetches into single queries
- Completely transparent - no view/template changes needed

**Implementation**:
```python
# All models updated to use:
import auto_prefetch

class ModelName(auto_prefetch.Model):
    foreign_key = auto_prefetch.ForeignKey(...)
    one_to_one = auto_prefetch.OneToOneField(...)
    
    class Meta(auto_prefetch.Model.Meta):
        ...
```

**Models Updated (18 total)**:
1. Warehouse, Supplier, ReleaseLetter
2. InventoryItem, Category, Unit
3. MaterialOrder (critical)
4. Profile, BillOfQuantity
5. MaterialOrderAudit, ReportSubmission
6. MaterialTransport (critical), SiteReceipt
7. Project, ProjectSite, ProjectPhase
8. Notification
9. Transporter, TransportVehicle

**Performance Gains**:
- Query count: 90%+ reduction (from 500+ to 5-10 queries)
- Page load: <0.5 seconds (from 3-5 seconds)

**Files Modified**:
- `/Inventory/models.py`
- `/Inventory/transporter_models.py`
- `requirements.txt`

**Installation**:
```bash
pip install django-auto-prefetch
python manage.py makemigrations Inventory
python manage.py migrate
```

---

## System Architecture Changes

### [Reverted] Package-Based → Community-Based Tracking
**Date**: October 29, 2025 (per supervisor directive)

**What Was Reverted**:
- Rolled back migrations 0013 and 0014 to migration 0012
- DELETED: Region and District models
- DELETED: ContractPackage model
- DELETED: contract_package_views.py and templates
- DELETED: Contract package URL routes and navigation

**What Was Restored**:
- `community` field restored to: BillOfQuantity, MaterialOrder, MaterialTransport, ReportSubmission
- Field type: `CharField(max_length=100, null=True, blank=True)`
- Existing data preserved (community=NULL for old package-based records)

**Current State**:
- Migration: `0012_boqoverissuancejustification`
- Models use: region, district, community, package_number fields

**Impact on System**:
1. Excel templates need community column
2. BOQ upload view needs community extraction
3. Material request forms need community field
4. Templates need community display/filter
5. Existing NULL records may need population

**Reference**: See `REVERSION_TO_COMMUNITY_BASED.md` for complete details

### Database Schema: InventoryItem Uniqueness
**Constraint**: `unique_together = ['code', 'warehouse']`

**Purpose**: Allows same material in multiple warehouses while preventing duplicate code+warehouse combinations

**Behavior**:
- ✅ "Cement" in Accra Warehouse + "Cement" in Kumasi Warehouse
- ✅ Different codes per warehouse (optional)
- ❌ Duplicate code+warehouse combination

---

## Known Features & Behaviors

### Material Request Workflow
1. **Draft** - Initial submission
2. **Pending** - Awaiting approval
3. **Approved** - Approved for processing
4. **In Progress** - Being processed by storekeeper
5. **Partially Fulfilled** - Some quantity processed/transported
6. **Completed** - Fully fulfilled

### Quantity Tracking
- `quantity` - Original requested amount
- `processed_quantity` - Amount processed by storekeeper
- `remaining_quantity` - quantity - processed_quantity
- `remaining_transport_quantity` - Processed but not yet transported

### Request Type Choices
- **Release** - Materials going out to projects (requires region, district, consultant, contractor, package_number, warehouse)
- **Receipt** - Materials coming in from suppliers (requires name, quantity, warehouse; supplier optional)

### Priority Levels
- Low
- Medium (default)
- High
- Urgent

### Excel Upload Requirements
**Release Request**:
```
Required columns: name, quantity, region, district, consultant, contractor, package_number, warehouse
```

**Receipt Request**:
```
Required columns: name, quantity, warehouse
Optional: supplier
```

---

## File Structure

### Core Models (`/Inventory/models.py`)
- Warehouse, Supplier
- InventoryItem (code + warehouse uniqueness)
- Category, Unit
- MaterialOrder (main transaction model)
- BillOfQuantity
- MaterialTransport, SiteReceipt
- ReleaseLetter
- Profile, Notification
- BoQOverissuanceJustification

### Transporter Models (`/Inventory/transporter_models.py`)
- Transporter
- TransportVehicle

### Main Views (`/Inventory/views.py`)
- RequestMaterialView - Material requests (single + bulk)
- MaterialReceiptView - Material receipts (single + bulk)
- MaterialOrdersView - List all orders
- UpdateMaterialStatusView - Storekeeper processing
- And 20+ other views

### Specialized Views
- `/Inventory/transporter_views.py` - Transporter assignment
- `/Inventory/notification_views.py` - Notification management
- `/Inventory/boq_overissuance_views.py` - BoQ overissuance tracking

### Forms (`/Inventory/forms.py`)
- InventoryItemForm, MaterialOrderForm, MaterialReceiptForm
- BulkMaterialRequestForm
- ReleaseLetterUploadForm
- TransporterForm, TransportVehicleForm, TransportAssignmentForm
- SiteReceiptForm
- BoQOverissuanceJustificationForm

---

## Development Notes

### Testing Requirements
When making changes, test:
1. Single material request form
2. Bulk Excel upload (Release + Receipt)
3. Material processing by storekeeper
4. Transporter assignment
5. Site receipt logging
6. BoQ uploads
7. Notification generation

### Key Dependencies
```
django-auto-prefetch  # Query optimization
pandas               # Excel processing
openpyxl            # Excel reading
```

### Custom Permissions
- `can_review_overissuance`
- `can_view_overissuance_summary`

### Signals
File: `/Inventory/signals.py`
- Auto-create notifications on model changes
- Load via `apps.py` ready() method

### Context Processors
File: `/Inventory/context_processors.py`
- `notifications_context` - Global unread count

---

## Migration History
- `0012_boqoverissuancejustification` - Current migration
- `0013_*`, `0014_*` - DELETED (package-based system)
- Earlier migrations - Core models and features

---

## Future Considerations

### Potential Enhancements
1. Populate community field for existing NULL records
2. Add community filter to Excel templates
3. Implement inventory forecasting
4. Add barcode scanning for warehouse operations
5. Mobile app for site receipts
6. Dashboard analytics for material flow

### Technical Debt
- JavaScript lint errors in templates (Django template syntax - false positives)
- Some legacy code may still reference old status values
- Consider adding indexes for frequently queried fields

---

## Support & Maintenance

### Common Issues
1. **MultipleObjectsReturned errors** - Usually indicates duplicate materials; use code+warehouse lookup
2. **Status validation errors** - Ensure status values match STATUS_CHOICES
3. **Excel upload failures** - Check column names match exactly (case-sensitive)
4. **Permission denied** - Verify user groups and custom permissions

### Debugging Tips
1. Check Django development server console for detailed tracebacks
2. Verify database constraints with `python manage.py dbshell`
3. Use Django debug toolbar for query analysis
4. Check signal firing with logging statements

---

**Last Updated**: October 31, 2025
**System Version**: Migration 0012
**Django Version**: [Check requirements.txt]
