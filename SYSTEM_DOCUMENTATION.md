# MOEGT Integrated Energy Project System (IEPS) - Complete Documentation

## System Overview

The MOEGT IEPS is a comprehensive integrated energy project and inventory management system designed for the Ministry of Energy and Green Transition (MOEGT).

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [User Roles & Permissions](#user-roles--permissions)
3. [Core Features](#core-features)
4. [API Endpoints](#api-endpoints)
5. [Database Schema](#database-schema)
6. [Workflows](#workflows)
7. [Integration Guide](#integration-guide)

---

## System Architecture

### Technology Stack
```
Backend:    Django 
Database:   PostgreSQL/SQLite
Frontend:   HTML, CSS (Bootstrap), JavaScript
Excel:      pandas, openpyxl
Optimization: django-auto-prefetch
```

### Application Structure
```
MOEN-IMS/
├── IMS/
│   └── Inventory_management_system/
│       ├── Inventory/
│       │   ├── models.py              # Core data models
│       │   ├── transporter_models.py  # Transport-specific models
│       │   ├── views.py               # Main views
│       │   ├── transporter_views.py   # Transport views
│       │   ├── notification_views.py  # Notification system
│       │   ├── boq_overissuance_views.py  # BoQ overissuance
│       │   ├── forms.py               # Form definitions
│       │   ├── signals.py             # Django signals
│       │   ├── context_processors.py  # Global context
│       │   ├── urls.py                # URL routing
│       │   ├── admin.py               # Admin interface
│       │   ├── templates/
│       │   │   └── Inventory/         # HTML templates
│       │   └── migrations/            # Database migrations
│       └── settings.py
└── requirements.txt
```

### Design Patterns
- **Model-View-Template (MVT)**: Django's MVC variant
- **Signal-based notifications**: Automatic notification generation
- **Formset pattern**: Dynamic form handling
- **Context processors**: Global data availability
- **Auto-prefetch optimization**: Automatic query optimization

---

## User Roles & Permissions

### 1. Superuser/Administrator
**Access**: Full system access
- Manage all users and permissions
- View all data across system
- Delete records
- Configure system settings
- Access Django admin panel

### 2. Schedule Officers
**Primary Role**: Request materials for projects

**Permissions**:
- Create material requests (Release type)
- View their own requests
- Upload release letters
- Track request status
- Receive notifications for their requests

### 3. Storekeepers
**Primary Role**: Process material requests and manage inventory

**Permissions**:
- View all pending material requests
- Process requests (approve/reject/fulfill)
- Update inventory quantities
- Create material receipts
- Assign transporters
- Receive low inventory alerts
- Track material movements

### 4. Management
**Primary Role**: Oversight and reporting

**Permissions**:
- View all transactions
- Generate reports
- Approve high-priority requests
- View BoQ overissuance summaries
- Access system analytics

### 5. Consultants
**Primary Role**: Monitor project deliveries

**Permissions**:
- View material deliveries to their projects
- Log site receipts (waybills, photos)
- Track delivery status
- Confirm material conditions
- Receive delivery notifications

### 6. Transporters
**Primary Role**: Execute material deliveries

**Permissions**:
- View assigned transport tasks
- Update delivery status
- Upload delivery documentation
- Manage vehicle information

### Custom Permissions
```python
can_review_overissuance       # Review BoQ overissuance justifications
can_view_overissuance_summary # View overissuance summary reports
```

---

## Core Features

### 1. Material Management

#### Inventory Items
- **Unique Constraint**: code + warehouse combination
- **Fields**: name, quantity, category, unit, code, warehouse, user, group
- **Support**: Multiple warehouses can stock same material with different codes

#### Categories & Units
- Flexible categorization system
- Custom unit definitions (kg, meters, pieces, etc.)

#### Warehouses
- Multiple warehouse support
- Contact information tracking
- Active/inactive status
- Location tracking

#### Suppliers
- Supplier database management
- Contact information
- Active/inactive tracking
- Receipt linkage

### 2. Material Request System

#### Request Types
**Release Request** (Materials going out):
- Full project information required
- Release letter linkage
- Priority levels
- Approval workflow
- Region, district, consultant, contractor, package tracking

**Receipt Request** (Materials coming in):
- Supplier information
- Warehouse destination
- Simpler workflow
- Optional supplier linkage

#### Request Workflow
```
Draft → Pending → Approved → In Progress → Partially Fulfilled → Completed
```

#### Features
- Single request form (dynamic formsets)
- Bulk Excel upload
- Request code generation (`REQ-YYYYMMDD-UUID`)
- Priority levels (Low, Medium, High, Urgent)
- Quantity tracking (requested, processed, remaining)
- Release letter attachment

### 3. Bill of Quantity (BoQ) System

#### Core Functionality
- Project-level material tracking
- Contract quantity vs received quantity
- Balance calculation (remaining or overissuance)
- Excel bulk upload
- Package number tracking
- Region/district/community assignment

#### BoQ Overissuance Management
**Complete workflow for handling negative balances**

**Features**:
- Automatic detection of overissuances
- Justification submission form
- Review workflow (Pending → Under Review → Approved/Rejected)
- Categorization (Design Change, Site Condition, Measurement Error, Emergency Need, Variation Order, Other)
- Supporting documentation tracking
- Status filtering
- Summary reports by project/package

**Justification Categories**:
1. Design Change
2. Site Condition
3. Measurement Error
4. Emergency Need
5. Variation Order
6. Other

### 4. Transportation Management

#### Transporter System
- Transporter database
- Vehicle management
- Driver information
- Contact tracking
- Active/inactive status

#### Transport Assignment
- Link material orders to transporters
- Vehicle assignment
- Driver details
- Status tracking (Scheduled → In Transit → Delivered → Completed)
- Quantity verification

#### Partial Fulfillment Support
**Key Feature**: Orders remain visible for subsequent fulfillments

**Example**:
```
Order: 1000 poles requested
Step 1: Storekeeper processes 800 poles
Step 2: Transporter A delivers 800 poles
Result: Order STILL VISIBLE with "200 pending processing"
Step 3: Storekeeper processes remaining 200 poles
Step 4: Transporter B can deliver remaining 200 poles
```

**Display Logic**:
- Requested | Processed | Assigned | Pending Processing
- Assign button active only when `remaining_transport_quantity > 0`
- Status filter includes 'Completed' for partial tracking

### 5. Release Letter System

#### Purpose
Formal authorization for material releases, now with robust drawdown and fulfillment tracking.

#### Features
- **PDF upload**: Secure storage of signed authorization documents.
- **Request code linkage**: Groups related orders under a single letter.
- **Authorized Quantity Tracking**: Explicitly tracks total quantity authorized vs requested.
- **Drawdown Analysis**: Real-time tracking of requested quantity against authorization.
- **Fulfillment Tracking**: Monitors physical movement (transports) against authorized amounts.
- **Material Classification**: Categorizes letters by material type (Transformers, Poles, etc.).
- **Project Phase Tracking**: Links authorizations to specific project phases (e.g., SHEP-4).
- **Maintenance Tools**: AJAX-based adjustment of authorized quantities for administrators.
- **Validation**: Prevents material releases that exceed the authorized letter balance.

#### Workflow
1. Schedule officer creates material request
2. Release letter uploaded (signed PDF)
3. System auto-approves related orders
4. Storekeeper processes approved requests

### 6. Site Receipt Logging

#### Purpose
Consultants confirm delivery at project sites

#### Features
- Waybill PDF upload
- Acknowledgement sheet upload
- Site photos (multiple)
- Quantity verification
- Condition assessment (Good, Damaged, Incomplete)
- Notes field
- Timestamp tracking

#### Condition Options
- Good
- Damaged
- Incomplete

### 7. Notification System

#### Automatic Notifications
**Signal-based**: Notifications generated automatically on events

**Notification Types**:
1. `material_request` - New requests submitted
2. `material_processed` - Storekeeper processing
3. `transport_assigned` - Transport scheduled
4. `material_delivered` - Delivery completed
5. `site_receipt_logged` - Site confirmation
6. `boq_updated` - BoQ changes
7. `staff_prompt` - Low inventory alerts

#### Role-Based Visibility
- Schedule Officers: Their requests + updates
- Storekeepers: New requests + inventory alerts
- Management: Everything for oversight
- Consultants: Deliveries + site-related
- Superusers: All notifications

#### Features
- Mark as read/unread
- Delete (superuser only)
- Unread count badge (global)
- AJAX endpoints for real-time updates
- Filter by read/unread status

#### Inventory Alerts
- **Critical**: quantity < 5 units
- **Low**: quantity < 10 units
- Auto-generated notifications to storekeepers

### 8. Bulk Operations

#### Excel Upload Support
**Material Requests**:
```excel
Columns (Release): name, quantity, region, district, consultant, contractor, package_number, warehouse
Columns (Receipt): name, quantity, warehouse, [supplier]
```

**BoQ Upload**:
```excel
Columns: package_number, material_description, contract_quantity, quantity_received, region, district, consultant, contractor
```

#### Features
- Validation before processing
- Error reporting
- Filtered row tracking (zero/negative quantities removed)
- Transaction safety (all-or-nothing)
- Duplicate handling

### 9. Reporting & Analytics

#### Available Reports
1. Material orders by status
2. Inventory levels by warehouse
3. Transport assignments
4. BoQ overissuance summary
5. Notification history
6. Material movement tracking

#### Export Options
- Excel export
- PDF reports
- CSV data dumps

---

## API Endpoints

### Material Requests
```
GET  /request-material/          # Material request form
POST /request-material/          # Submit request (single or bulk)
GET  /material-orders/           # List all orders
GET  /material-orders/<id>/      # Order detail
POST /update-material-status/   # Storekeeper processing
```

### Material Receipts
```
GET  /material-receipt/          # Receipt form
POST /material-receipt/          # Submit receipt (single or bulk)
GET  /receive-material/          # Alternative receipt view
```

### Bill of Quantity
```
GET  /bill-of-quantity/                           # BoQ list
GET  /upload-bill-of-quantity/                    # Upload form
POST /upload-bill-of-quantity/                    # Process upload
GET  /boq/overissuance/summary/                   # Overissuance summary
GET  /boq/overissuance/<boq_id>/justify/         # Justification form
POST /boq/overissuance/<boq_id>/justify/         # Submit justification
GET  /boq/overissuance/justifications/           # List justifications
GET  /boq/overissuance/justifications/<pk>/      # Justification detail
POST /boq/overissuance/justifications/<pk>/review/ # Review action
GET  /boq/overissuance/stats/                    # AJAX statistics
```

### Transportation
```
GET  /transporters/                        # Transporter list
GET  /transporters/<id>/                   # Transporter detail
POST /transporters/create/                 # Create transporter
GET  /transporters/<id>/edit/              # Edit form
POST /transporters/<id>/update/            # Update transporter
GET  /transporter-assignment/              # Assignment view
POST /assign-transport/                    # Assign transporter
POST /update-transport-status/             # Update delivery status
```

### Site Receipts
```
GET  /site-receipts/                       # List receipts
GET  /site-receipts/<transport_id>/log/   # Log receipt form
POST /site-receipts/<transport_id>/log/   # Submit receipt
GET  /site-receipts/<id>/                 # Receipt detail
```

### Notifications
```
GET  /notifications/                      # List notifications
GET  /notifications/<id>/                 # Detail (auto-marks read)
POST /notifications/<id>/mark-read/       # AJAX mark as read
POST /notifications/mark-all-read/        # Mark all read
GET  /notifications/unread-count/         # AJAX unread count
POST /notifications/<id>/delete/          # Delete (superuser)
```

### Release Letters
```
GET  /release-letters/                    # List letters
GET  /release-letters/upload/             # Upload form
POST /release-letters/upload/             # Process upload
GET  /release-letters/<id>/               # Letter detail
```

### Admin & Reports
```
GET  /admin/                              # Django admin panel
GET  /dashboard/                          # System dashboard
GET  /reports/                            # Reports section
```

---

## Database Schema

### Core Models

#### InventoryItem
```python
name: CharField(200)
quantity: IntegerField
category: ForeignKey(Category)
code: CharField(200)
unit: ForeignKey(Unit)
warehouse: ForeignKey(Warehouse)
user: ForeignKey(User)
group: ForeignKey(Group)
date_created: DateTimeField

UNIQUE_TOGETHER: ['code', 'warehouse']
```

#### MaterialOrder
```python
name: CharField(200)
quantity: DecimalField(10, 2)
category: ForeignKey(Category)
code: CharField(200)
unit: ForeignKey(Unit)
user: ForeignKey(User)
group: ForeignKey(Group)
warehouse: ForeignKey(Warehouse)
supplier: ForeignKey(Supplier)

# Request metadata
date_requested: DateTimeField
date_required: DateField
priority: CharField (Low/Medium/High/Urgent)
request_type: CharField (Release/Receipt)
request_code: CharField(50)
status: CharField (Draft/Pending/Approved/In Progress/Partially Fulfilled/Completed)

# Quantity tracking
processed_quantity: DecimalField(10, 2)
remaining_quantity: DecimalField(10, 2)

# Project information
region: CharField(100)
district: CharField(100)
community: CharField(100)
consultant: CharField(200)
contractor: CharField(200)
package_number: CharField(50)

# Release letter
release_letter: ForeignKey(ReleaseLetter)
```

#### ReleaseLetter
```python
request_code: CharField(50)
title: CharField(200)
pdf_file: FileField
total_quantity: DecimalField(12, 2)
material_type: CharField (Transformers/Poles/Cables/etc.)
project_phase: CharField(100)
reference_number: CharField(50, unique=True)
status: CharField (Open/Closed)
uploaded_by: ForeignKey(User)
upload_time: DateTimeField
notes: TextField
```

#### BillOfQuantity
```python
package_number: CharField(50)
material_description: CharField(200)
item_code: CharField(100)
contract_quantity: DecimalField(15, 2)
quantity_received: DecimalField(15, 2)
region: CharField(100)
district: CharField(100)
community: CharField(100)
consultant: CharField(200)
contractor: CharField(200)
created_at: DateTimeField
updated_at: DateTimeField

@property
balance: contract_quantity - quantity_received
```

#### MaterialTransport
```python
material_order: ForeignKey(MaterialOrder)
letter: ForeignKey(ReleaseLetter)
transporter: ForeignKey(Transporter)
vehicle: ForeignKey(TransportVehicle)
driver_name: CharField(200)
driver_phone: CharField(20)
status: CharField (Scheduled/In Transit/Delivered/Completed)
quantity: DecimalField(10, 2)
unit: CharField(50)

# Auto-populated from order
material_name: CharField(200)
material_code: CharField(200)
recipient: CharField(200)
consultant: CharField(200)
region: CharField(100)
district: CharField(100)
community: CharField(100)
package_number: CharField(50)

assigned_date: DateTimeField
delivery_date: DateTimeField
notes: TextField
```

#### SiteReceipt
```python
transport: OneToOneField(MaterialTransport)
received_quantity: DecimalField(10, 2)
waybill_pdf: FileField
acknowledgement_sheet: FileField
site_photos: FileField
condition: CharField (Good/Damaged/Incomplete)
notes: TextField
received_by: ForeignKey(User)
receipt_date: DateTimeField
```

#### BoQOverissuanceJustification
```python
boq_item: ForeignKey(BillOfQuantity)
package_number: CharField(50)
project_name: CharField(200)
overissuance_quantity: DecimalField(15, 2)
justification_category: CharField (Design Change/Site Condition/Measurement Error/Emergency Need/Variation Order/Other)
reason: TextField
supporting_documents: TextField
status: CharField (Pending/Under Review/Approved/Rejected)
submitted_by: ForeignKey(User)
reviewed_by: ForeignKey(User)
submitted_at: DateTimeField
reviewed_at: DateTimeField
review_notes: TextField
```

#### Notification
```python
recipient: ForeignKey(User)
notification_type: CharField
title: CharField(200)
message: TextField
related_object_id: IntegerField
is_read: BooleanField
created_at: DateTimeField
read_at: DateTimeField
```

#### Warehouse
```python
name: CharField(200)
code: CharField(50, unique=True)
location: CharField(500)
contact_person: CharField(200)
contact_phone: CharField(20)
contact_email: EmailField
is_active: BooleanField
notes: TextField
created_at: DateTimeField
updated_at: DateTimeField
```

#### Transporter
```python
name: CharField(200)
contact_person: CharField(200)
email: EmailField
phone: CharField(20)
address: TextField
is_active: BooleanField
notes: TextField
created_at: DateTimeField
```

#### TransportVehicle
```python
registration_number: CharField(50, unique=True)
vehicle_type: CharField (Truck/Van/Pickup/Other)
capacity: CharField(100)
transporter: ForeignKey(Transporter)
is_active: BooleanField
notes: TextField
```

---

## Workflows

### Material Release Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SCHEDULE OFFICER: Create Material Request                │
│    - Select materials (with warehouse visibility)            │
│    - Enter project details                                   │
│    - Set priority                                            │
│    - Optionally attach release letter                        │
│    Status: Draft                                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. SYSTEM: Auto-Submit Request                              │
│    - Generate request code                                   │
│    - Create notification (to storekeepers)                   │
│    Status: Pending                                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. [OPTIONAL] Upload Release Letter                         │
│    - Management/Schedule officer uploads signed PDF          │
│    - System auto-approves linked orders                      │
│    Status: Approved                                          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. STOREKEEPER: Process Request                             │
│    - Review request details                                  │
│    - Verify inventory availability                           │
│    - Enter processed quantity                                │
│    - Can partially fulfill (process < requested)             │
│    - Update inventory (deduct from stock)                    │
│    Status: In Progress / Partially Fulfilled                 │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. STOREKEEPER: Assign Transporter                          │
│    - Select transporter and vehicle                          │
│    - Enter driver details                                    │
│    - Specify transport quantity                              │
│    - Create MaterialTransport record                         │
│    - Notification sent to transporter                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. TRANSPORTER: Execute Delivery                            │
│    - Update status: In Transit                               │
│    - Deliver to project site                                 │
│    - Update status: Delivered                                │
│    - Notification sent to consultant                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. CONSULTANT: Log Site Receipt                             │
│    - Verify delivered quantity                               │
│    - Upload waybill PDF                                      │
│    - Upload acknowledgement sheet                            │
│    - Add site photos                                         │
│    - Assess condition (Good/Damaged/Incomplete)              │
│    - Add notes                                               │
│    Status: Completed                                         │
└─────────────────────────────────────────────────────────────┘
```

### Material Receipt Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. STOREKEEPER: Create Receipt Request                      │
│    - Select material                                         │
│    - Enter quantity received                                 │
│    - Select warehouse                                        │
│    - Optionally specify supplier                             │
│    Status: Draft                                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. SYSTEM: Process Receipt                                  │
│    - Update inventory quantity (add to stock)                │
│    - Record receipt transaction                              │
│    - Generate notification (if low stock alert cleared)      │
│    Status: Completed                                         │
└─────────────────────────────────────────────────────────────┘
```

### BoQ Overissuance Resolution Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. SYSTEM: Detect Overissuance                              │
│    - Calculate: quantity_received > contract_quantity        │
│    - Display in overissuance summary                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. PROJECT STAFF: Submit Justification                      │
│    - Select justification category                           │
│    - Provide detailed reason (min 20 chars)                  │
│    - Reference supporting documents                          │
│    Status: Pending                                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. REVIEWER: Mark Under Review                              │
│    - Authorized user reviews justification                   │
│    - May request additional information                      │
│    Status: Under Review                                      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. REVIEWER: Approve or Reject                              │
│    - Make final decision                                     │
│    - Add review notes                                        │
│    - Record timestamp                                        │
│    Status: Approved / Rejected                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Integration Guide

### Adding New Material Types

1. **Create Category** (if needed):
   ```python
   Category.objects.create(name="Electronics")
   ```

2. **Create Unit** (if needed):
   ```python
   Unit.objects.create(name="pieces")
   ```

3. **Add Inventory Item**:
   ```python
   InventoryItem.objects.create(
       name="LED Bulbs",
       code="ELEC-001",
       quantity=100,
       category=category,
       unit=unit,
       warehouse=warehouse,
       user=user,
       group=group
   )
   ```

### Adding New Warehouse

```python
Warehouse.objects.create(
    name="Regional Warehouse - Western",
    code="WH-WR",
    location="Takoradi, Western Region",
    contact_person="John Doe",
    contact_phone="+233-XXX-XXXX",
    contact_email="warehouse.western@moen.gov.gh",
    is_active=True
)
```

### Bulk Material Upload Template

**Excel Template (Release Request)**:
```
| name        | quantity | region  | district | consultant | contractor | package_number | warehouse |
|-------------|----------|---------|----------|------------|------------|----------------|-----------|
| Cement      | 100      | Greater | Accra    | ABC Ltd    | XYZ Co     | PKG-001       | Accra WH  |
| Steel Rods  | 500      | Greater | Accra    | ABC Ltd    | XYZ Co     | PKG-001       | Accra WH  |
```

**Excel Template (Receipt)**:
```
| name        | quantity | warehouse | supplier     |
|-------------|----------|-----------|--------------|
| Cement      | 200      | Accra WH  | BuildCo Ltd  |
| Steel Rods  | 1000     | Accra WH  | SteelCorp    |
```

### Custom Notification Types

Add to `/Inventory/signals.py`:
```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import YourModel, Notification

@receiver(post_save, sender=YourModel)
def create_custom_notification(sender, instance, created, **kwargs):
    if created:
        # Create notification for specific users
        Notification.objects.create(
            recipient=target_user,
            notification_type='your_type',
            title='Your Title',
            message=f'Your message with {instance}',
            related_object_id=instance.id
        )
```

### Query Optimization Best Practices

```python
# GOOD: Use auto-prefetch models
items = InventoryItem.objects.all()  # Auto-prefetches related objects

# GOOD: Use select_related for foreign keys
orders = MaterialOrder.objects.select_related('user', 'category')

# GOOD: Use prefetch_related for reverse FKs and M2M
orders = MaterialOrder.objects.prefetch_related('transports')

# AVOID: N+1 queries
for order in orders:
    print(order.user.username)  # Triggers query per order
```

---

## Deployment Checklist

### Pre-Deployment
- [ ] Run migrations: `python manage.py migrate`
- [ ] Collect static files: `python manage.py collectstatic`
- [ ] Create superuser: `python manage.py createsuperuser`
- [ ] Configure email backend (for notifications)
- [ ] Set up media file storage (for PDFs, photos)
- [ ] Configure allowed hosts in settings
- [ ] Set DEBUG = False
- [ ] Configure secure secret key

### Database Setup
- [ ] Create initial warehouses
- [ ] Create initial categories and units
- [ ] Set up user groups
- [ ] Assign permissions
- [ ] Import initial inventory (if applicable)

### Testing
- [ ] Test material request flow (single + bulk)
- [ ] Test material receipt flow
- [ ] Test transporter assignment
- [ ] Test site receipt logging
- [ ] Test notification generation
- [ ] Test BoQ upload and overissuance
- [ ] Test permissions for each role
- [ ] Load test with realistic data volumes

### Monitoring
- [ ] Set up error logging
- [ ] Configure performance monitoring
- [ ] Set up database backups
- [ ] Monitor disk space (media files)
- [ ] Configure uptime monitoring

---

## Troubleshooting

### Common Issues

#### "MultipleObjectsReturned" Error
**Cause**: Multiple items with same identifier  
**Solution**: Use code+warehouse lookup, ensure unique constraints

#### "Status validation error"
**Cause**: Invalid status value  
**Solution**: Check STATUS_CHOICES, use: Draft, Pending, Approved, In Progress, Partially Fulfilled, Completed

#### Excel upload fails
**Cause**: Column name mismatch  
**Solution**: Ensure exact column names (case-sensitive), verify Excel format

#### Notifications not generating
**Cause**: Signals not loaded  
**Solution**: Verify `apps.py` imports signals in `ready()` method

#### Slow page loads
**Cause**: N+1 query problem  
**Solution**: Verify auto-prefetch is installed and models inherit from `auto_prefetch.Model`

#### Permission denied errors
**Cause**: User lacks required permission  
**Solution**: Check user groups, assign custom permissions in admin

---

## Performance Metrics

### Expected Performance (with auto-prefetch)
- Material orders list (100 items): < 0.5 seconds, 5-10 queries
- Dashboard load: < 1 second
- Excel upload (50 items): < 2 seconds
- Notification generation: < 100ms

### Database Optimization
- Indexes on: request_code, status, date_requested, package_number
- Unique constraints enforced
- Foreign key indexes automatic

---

## Security Considerations

### Data Protection
- User authentication required for all views
- Role-based access control (RBAC)
- Permission checks on sensitive operations
- File upload validation (PDF only for letters/waybills)
- SQL injection prevention (Django ORM)

### File Security
- Media files stored outside web root
- PDF validation before upload
- File size limits enforced
- Secure file naming (UUIDs)

### Best Practices
- Never hardcode credentials
- Use environment variables for secrets
- Regular security updates
- Audit trail via MaterialOrderAudit model
- Session management configured

---

## Maintenance Tasks

### Daily
- Monitor error logs
- Check notification delivery
- Verify backup completion

### Weekly
- Review low inventory alerts
- Clean up old notifications (optional)
- Check storage usage

### Monthly
- Database optimization
- Review user permissions
- Archive old completed orders (optional)
- Generate compliance reports

### Quarterly
- Security audit
- Performance review
- User training refresher
- System updates

---

**Document Version**: 1.0  
**Last Updated**: October 31, 2025  
**Maintained By**: MOEN IT Department
