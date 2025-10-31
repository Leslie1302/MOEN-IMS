# Known Issues & Bug Tracker

## Current Issues

### 🟢 Resolved Issues

#### [FIXED - 2025-10-31] Multiple Warehouse Material Lookup Error
**Severity**: High  
**Status**: ✅ Fixed  
**Issue**: `InventoryItem.MultipleObjectsReturned` when same material exists in multiple warehouses  
**Impact**: Users unable to request materials that exist in other warehouses  
**Root Cause**: Form using name-based lookup instead of ID-based  
**Fix**: Changed to PK lookup, updated model display to show warehouse  
**Files**: forms.py, models.py, views.py, 3 templates  
**See**: FIX_SUMMARY_DUPLICATE_MATERIALS.md

#### [FIXED] MaterialOrder Status: 'Fulfilled' Invalid Value
**Severity**: Critical  
**Status**: ✅ Fixed  
**Issue**: 500 error on completing release requests  
**Root Cause**: Code setting status='Fulfilled' which doesn't exist in STATUS_CHOICES  
**Fix**: Changed to status='Completed'  
**Files**: /Inventory/models.py (lines 360, 357, 372)  

#### [FIXED] Inventory Lookup by Name Only
**Severity**: High  
**Status**: ✅ Fixed  
**Issue**: MultipleObjectsReturned on release completion  
**Root Cause**: Views matching by name only, not using code+warehouse unique constraint  
**Fix**: Implemented code+warehouse lookup with proper exception handling  
**Files**: /Inventory/views.py (UpdateMaterialStatusView, update_material_receipt)  

#### [FIXED] Bulk Upload: Missing Warehouse Field
**Severity**: Medium  
**Status**: ✅ Fixed  
**Issue**: Warehouse not populated during bulk Excel upload  
**Root Cause**: handle_bulk_request() not extracting warehouse from Excel  
**Fix**: Added warehouse lookup logic with case-insensitive matching  
**Files**: /Inventory/views.py (RequestMaterialView.handle_bulk_request)  

#### [FIXED] BoQ Upload: Auto-Generated Codes
**Severity**: Medium  
**Status**: ✅ Fixed  
**Issue**: Inconsistent material codes due to BOQ-{DESC}-{INDEX} fallback  
**Root Cause**: System allowed non-existent materials, auto-generating codes  
**Fix**: Enforced strict matching - all materials must exist in inventory  
**Files**: /Inventory/views.py (UploadBillOfQuantityView)  

---

## 🟡 Open Issues

### Minor Issues

#### [OPEN] Django Template Syntax Lint Errors
**Severity**: Low (False Positive)  
**Status**: 🟡 Open - Won't Fix  
**Issue**: IDE shows JavaScript errors in templates with `{{ inventory_items|safe }}`  
**Impact**: None - cosmetic only, doesn't affect functionality  
**Root Cause**: IDE doesn't recognize Django template tags in JavaScript blocks  
**Workaround**: Ignore these specific errors  
**Files**: request_material.html, receive_material.html, material_receipt.html  
**Example Error**: "Property assignment expected" at `const inventoryItems = {{ inventory_items|safe }};`  

#### [OPEN] Community Field NULL for Historical Records
**Severity**: Low  
**Status**: 🟡 Open  
**Issue**: Older records have community=NULL after package-to-community reversion  
**Impact**: Filtering/reporting by community incomplete for old data  
**Root Cause**: Reversion from package-based system preserved NULL values  
**Potential Fix**: Data migration to populate historical community values  
**Affected**: BillOfQuantity, MaterialOrder, MaterialTransport, ReportSubmission  

#### [OPEN] No Pagination on Large Lists
**Severity**: Low  
**Status**: 🟡 Open  
**Issue**: Large lists (1000+ orders) load slowly without pagination  
**Impact**: Performance degradation on high-volume views  
**Mitigation**: Auto-prefetch reduces query count, but DOM size still grows  
**Potential Fix**: Implement Django pagination (25-50 items per page)  
**Affected Views**: MaterialOrdersView, TransporterAssignmentView, NotificationListView  

---

## 🔴 Critical Monitoring Points

### Performance Watchpoints

#### Query Performance
**Monitor**: Number of database queries per page load  
**Target**: < 10 queries with auto-prefetch  
**Alert Threshold**: > 50 queries  
**Action**: Check if auto-prefetch models used, verify select_related/prefetch_related  

#### Page Load Times
**Monitor**: Time to first byte (TTFB)  
**Target**: < 500ms for list views, < 200ms for simple views  
**Alert Threshold**: > 2 seconds  
**Action**: Profile queries, check database indexes, verify auto-prefetch  

#### File Storage
**Monitor**: Media files directory size  
**Target**: Growth proportional to usage  
**Alert Threshold**: > 80% disk usage  
**Action**: Implement file cleanup for old PDFs, compress images, archive old records  

### Data Integrity Watchpoints

#### Inventory Balance
**Monitor**: Negative inventory quantities  
**Alert**: Any item with quantity < 0  
**Action**: Investigate transaction history, verify receipt/release calculations  

#### BoQ Balance Anomalies
**Monitor**: Extreme overissuances (> 200% of contract)  
**Alert**: balance < -2 * contract_quantity  
**Action**: Verify data entry accuracy, check for duplicate entries  

#### Orphaned Records
**Monitor**: MaterialTransport without MaterialOrder  
**Alert**: Any transport with order_id pointing to deleted/non-existent order  
**Action**: Database cleanup, enforce foreign key constraints  

#### Missing Required Fields
**Monitor**: Orders with NULL in required fields (region, district, package_number)  
**Alert**: Any Release-type order missing project info  
**Action**: Data validation, form validation review  

---

## 🔵 Feature Requests / Enhancements

### High Priority

#### Inventory Forecasting
**Description**: Predict when inventory will run out based on usage patterns  
**Benefit**: Proactive procurement, reduced stockouts  
**Complexity**: Medium  
**Dependencies**: Historical data analysis, time-series calculations  

#### Barcode Scanning
**Description**: Mobile barcode scanning for warehouse operations  
**Benefit**: Faster processing, reduced data entry errors  
**Complexity**: High  
**Dependencies**: Mobile app or web-based scanner, barcode generation  

#### Advanced Reporting Dashboard
**Description**: Interactive charts/graphs for material flow analysis  
**Benefit**: Better insights, data-driven decisions  
**Complexity**: Medium  
**Dependencies**: charting library (Chart.js, D3.js), aggregation queries  

### Medium Priority

#### Email Notifications
**Description**: Send email notifications in addition to in-app  
**Benefit**: Improved awareness, faster response times  
**Complexity**: Low  
**Dependencies**: Email backend configuration, templates  

#### Mobile-Optimized Views
**Description**: Responsive design for mobile devices  
**Benefit**: Field access for consultants/transporters  
**Complexity**: Medium  
**Dependencies**: Bootstrap responsive utilities, mobile testing  

#### Batch Operations
**Description**: Bulk approve/reject multiple requests at once  
**Benefit**: Faster processing for storekeepers  
**Complexity**: Low  
**Dependencies**: Checkboxes, bulk action endpoint  

### Low Priority

#### Material Photos
**Description**: Add photos to inventory items  
**Benefit**: Visual identification, training aid  
**Complexity**: Low  
**Dependencies**: Image upload, storage  

#### QR Code Generation
**Description**: Generate QR codes for materials, orders  
**Benefit**: Quick lookup, mobile integration  
**Complexity**: Low  
**Dependencies**: QR code library (qrcode)  

#### Audit Trail Viewer
**Description**: UI for viewing MaterialOrderAudit records  
**Benefit**: Transparency, compliance  
**Complexity**: Low  
**Dependencies**: Simple list view with filters  

---

## Bug Reporting Template

When reporting new bugs, please include:

```markdown
### [BUG] Short Description

**Severity**: Critical / High / Medium / Low
**Status**: 🔴 New
**Reported By**: [Name]
**Date**: YYYY-MM-DD

**Description**:
[Detailed description of the issue]

**Steps to Reproduce**:
1. Go to...
2. Click on...
3. Enter...
4. See error

**Expected Behavior**:
[What should happen]

**Actual Behavior**:
[What actually happens]

**Error Message** (if any):
```
[Paste full error traceback]
```

**Environment**:
- Browser: [Chrome/Firefox/Safari/Edge]
- User Role: [Superuser/Storekeeper/Schedule Officer/etc.]
- Django Version: [Check requirements.txt]
- Database: [PostgreSQL/SQLite]

**Screenshots**:
[Attach screenshots if applicable]

**Related Files**:
- [List relevant files/views]

**Possible Cause**:
[Your hypothesis if you have one]
```

---

## Testing Checklist

Before marking bug as fixed:

- [ ] Issue reproduced in development environment
- [ ] Fix implemented and tested locally
- [ ] Unit tests added (if applicable)
- [ ] Integration tests pass
- [ ] No new errors introduced
- [ ] Performance impact assessed
- [ ] Edge cases tested
- [ ] Documentation updated
- [ ] Code reviewed
- [ ] Deployed to staging
- [ ] User acceptance testing completed
- [ ] Deployed to production
- [ ] Post-deployment verification
- [ ] Monitoring configured

---

## Version History

### v1.2.0 (Current) - October 31, 2025
- Fixed: Multiple warehouse material lookup
- Enhanced: Inventory item display with warehouse name
- Improved: Form validation for duplicate materials

### v1.1.0 - October 2025
- Added: BoQ overissuance tracking system
- Added: Transporter partial fulfillment support
- Fixed: Inventory lookup by code+warehouse
- Fixed: MaterialOrder status values
- Fixed: Bulk upload warehouse field

### v1.0.0 - September 2025
- Initial release
- Core inventory management
- Material request/receipt workflows
- Basic reporting
- User authentication and roles
- Warehouse management
- Bill of Quantity tracking
- Notification system
- Release letter management
- Site receipt logging
- Performance optimization (auto-prefetch)

---

## Migration Notes

### Reverted: Package-Based System (Oct 29, 2025)
**Reason**: Supervisor directive to use community-based tracking  
**Actions Taken**:
- Rolled back migrations 0013, 0014 to 0012
- Deleted Region, District, ContractPackage models
- Deleted contract_package_views.py and templates
- Restored community field to all models
- Preserved existing data (community=NULL for old records)

**Current State**:
- Models use: region, district, community, package_number
- Current migration: 0012_boqoverissuancejustification
- See: REVERSION_TO_COMMUNITY_BASED.md

---

## Contact & Support

**Technical Issues**: Report in this document or create GitHub issue  
**Feature Requests**: Add to Feature Requests section above  
**Security Concerns**: Contact system administrator immediately  
**Data Issues**: Contact database administrator  

**Last Updated**: October 31, 2025
