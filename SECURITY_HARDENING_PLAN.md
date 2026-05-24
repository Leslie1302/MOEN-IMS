# MOEN-IMS Security Hardening Implementation Plan

**Purpose:** Turn the audit findings into a systematic, code-first roadmap with concrete patterns, tests, and deployment steps.

**Outcome:** Upgrade from 58/100 to 75+/100 in 6 weeks.

---

## TABLE OF CONTENTS

1. [Executive Implementation Strategy](#executive-implementation-strategy)
2. [Phase 1: Authorization Foundation (Weeks 1–2)](#phase-1-authorization-foundation-weeks-1--2)
3. [Phase 2: API & Data Security (Weeks 3–4)](#phase-2-api--data-security-weeks-3--4)
4. [Phase 3: Infrastructure & Observability (Weeks 5–6)](#phase-3-infrastructure--observability-weeks-5--6)
5. [Testing & Validation Strategy](#testing--validation-strategy)
6. [Deployment Checklist](#deployment-checklist)

---

## EXECUTIVE IMPLEMENTATION STRATEGY

### Why This Order?

1. **Authorization first** — IDOR affects 30+ endpoints; fixing here has the highest security-to-effort ratio.
2. **API security second** — Protects data exposure; unblocks rate limiting and error handling.
3. **Infrastructure last** — Database migration, CI/CD, CSP are force multipliers once data is safe.

### Team Roles

- **Backend Lead (YOU):** Authorization patterns, QuerySet filtering, tests.
- **DevOps:** Database migration, CI/CD security scanning, secrets management.
- **Code Reviewer:** Every authorization change must be reviewed (high risk).

### Timeline

- **Week 1–2:** Row-level access control (foundation).
- **Week 3–4:** API hardening, file uploads, error handling.
- **Week 5–6:** Database, rate limiting, secrets rotation.
- **Week 7+:** Type hints, CSP, audit logging (nice-to-have).

---

# PHASE 1: AUTHORIZATION FOUNDATION (Weeks 1–2)

## **Objective**
Implement row-level access control across all sensitive views. Close IDOR vulnerabilities.

---

## 1.1 Create Authorization Mixins & Utilities

Create a new file: `Inventory/permissions.py`

```python
"""
Permission utilities for row-level access control.
All sensitive views must use these checks.
"""

from functools import wraps
from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# ROLE-BASED QUERY FILTERING
# ============================================================================

def filter_user_material_orders(queryset, user):
    """
    Filter material orders visible to a user.
    
    Rules:
    - Superuser: sees all.
    - User who created the order: sees it.
    - Member of assigned group: sees it.
    - Warehouse manager: sees orders for their warehouse (future).
    """
    if user.is_superuser:
        return queryset
    
    return queryset.filter(
        Q(created_by=user) |
        Q(user=user) |
        Q(group__in=user.groups.all())
    ).distinct()


def filter_user_release_letters(queryset, user):
    """
    Filter release letters visible to a user.
    - Superuser: sees all.
    - Created by user or assigned to user's group: sees it.
    - Transporters: see letters for their assignments (future refinement).
    """
    if user.is_superuser:
        return queryset
    
    return queryset.filter(
        Q(uploaded_by=user) |
        Q(request_code__in=[
            mo.request_code 
            for mo in filter_user_material_orders(
                __import__('Inventory.models', fromlist=['MaterialOrder']).MaterialOrder.objects.all(),
                user
            )
        ])
    ).distinct()


def filter_user_boq(queryset, user):
    """
    Filter Bill of Quantity records visible to a user.
    - Superuser: sees all.
    - Group member: sees BOQs assigned to that group.
    - User: sees BOQs they created.
    """
    if user.is_superuser:
        return queryset
    
    return queryset.filter(
        Q(user=user) |
        Q(group__in=user.groups.all())
    ).distinct()


# ============================================================================
# OBJECT-LEVEL ACCESS CHECKS
# ============================================================================

def user_can_view(obj, user):
    """
    Check if a user can view a specific object.
    Supports MaterialOrder, ReleaseLetter, BillOfQuantity, MaterialTransport.
    """
    if user.is_superuser:
        return True
    
    obj_type = type(obj).__name__
    
    if obj_type == 'MaterialOrder':
        return (
            obj.created_by == user or
            obj.user == user or
            user.groups.filter(id=obj.group_id).exists()
        )
    
    elif obj_type == 'ReleaseLetter':
        # User can view if they created it or it's linked to their material order
        if obj.uploaded_by == user:
            return True
        # Check if any of user's orders reference this release letter
        from Inventory.models import MaterialOrder
        return MaterialOrder.objects.filter(
            release_letter=obj,
            **{'Q(created_by=user) | Q(user=user) | Q(group__in=user.groups.all())': None}
        ).exists()
    
    elif obj_type == 'BillOfQuantity':
        return obj.user == user or user.groups.filter(id=obj.group_id).exists()
    
    elif obj_type == 'MaterialTransport':
        return (
            obj.created_by == user or
            user.groups.filter(id=obj.material_order.group_id).exists()
        )
    
    return False


def user_can_edit(obj, user):
    """
    Check if a user can edit a specific object.
    Stricter than can_view: typically only creator or designated admin.
    """
    if user.is_superuser:
        return True
    
    obj_type = type(obj).__name__
    
    if obj_type == 'MaterialOrder':
        # Only creator can edit; once approved, frozen
        return obj.created_by == user and obj.status == 'Draft'
    
    elif obj_type == 'BillOfQuantity':
        # Only creator can edit
        return obj.user == user
    
    # For others, default to superuser-only
    return False


# ============================================================================
# CLASS-BASED VIEW MIXINS
# ============================================================================

class UserOwnsObjectMixin(UserPassesTestMixin):
    """
    Mixin for DetailView/UpdateView: enforces that user owns the object.
    Raises Http404 if not (don't leak existence).
    """
    
    def test_func(self):
        obj = self.get_object()
        return user_can_view(obj, self.request.user)
    
    def handle_no_permission(self):
        # Return 404 instead of 403 to not leak object existence
        logger.warning(
            f"Unauthorized access attempt by {self.request.user} to {self.model.__name__} {self.kwargs}"
        )
        raise Http404("Not found")


class UserCanEditObjectMixin(UserPassesTestMixin):
    """
    Mixin for UpdateView: stricter check that user can *edit* (not just view).
    """
    
    def test_func(self):
        obj = self.get_object()
        return user_can_edit(obj, self.request.user)
    
    def handle_no_permission(self):
        logger.warning(
            f"Unauthorized edit attempt by {self.request.user} to {self.model.__name__} {self.kwargs}"
        )
        raise Http404("Not found")


# ============================================================================
# FUNCTION-BASED VIEW DECORATORS
# ============================================================================

def require_object_access(model_name, obj_id_kwarg='pk', permission='view'):
    """
    Decorator for function-based views.
    Validates user can access the object before view logic runs.
    
    Example:
        @require_object_access('MaterialOrder', obj_id_kwarg='order_id', permission='view')
        def material_order_detail(request, order_id):
            order = MaterialOrder.objects.get(id=order_id)
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            from Inventory import models as inv_models
            
            model = getattr(inv_models, model_name)
            obj_id = kwargs.get(obj_id_kwarg)
            
            if not obj_id:
                return HttpResponseForbidden("Missing object ID")
            
            try:
                obj = model.objects.get(pk=obj_id)
            except model.DoesNotExist:
                raise Http404(f"{model_name} not found")
            
            if permission == 'view':
                check = user_can_view(obj, request.user)
            elif permission == 'edit':
                check = user_can_edit(obj, request.user)
            else:
                check = False
            
            if not check:
                logger.warning(
                    f"Unauthorized {permission} attempt by {request.user} to {model_name} {obj_id}"
                )
                raise Http404("Not found")
            
            # Attach object to request for view function
            request.accessed_object = obj
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


# ============================================================================
# QUERYSET FILTERING (Generic for List Views)
# ============================================================================

class FilteredListViewMixin:
    """
    Mixin for ListView: automatically filters queryset by user permissions.
    
    Usage:
        class MyListView(FilteredListViewMixin, ListView):
            model = MaterialOrder
            filter_type = 'material_orders'  # See filter_queryset below
    """
    
    filter_type = None  # Override in subclass
    
    def get_queryset(self):
        qs = super().get_queryset()
        
        if self.filter_type == 'material_orders':
            return filter_user_material_orders(qs, self.request.user)
        elif self.filter_type == 'release_letters':
            return filter_user_release_letters(qs, self.request.user)
        elif self.filter_type == 'boq':
            return filter_user_boq(qs, self.request.user)
        else:
            # Default: return all if no filter defined (be explicit about this)
            logger.warning(f"No filter_type defined for {self.__class__.__name__}")
            return qs
```

---

## 1.2 Update Existing Views to Use Permission Checks

### **Example 1: Material Orders List View**

**Before:**
```python
class MaterialOrdersView(LoginRequiredMixin, ListView):
    model = MaterialOrder
    template_name = 'Inventory/material_orders.html'
    context_object_name = 'orders'
    paginate_by = 25

    def get_queryset(self):
        return MaterialOrder.objects.all().order_by('-date_requested')
```

**After:**
```python
from Inventory.permissions import FilteredListViewMixin

class MaterialOrdersView(LoginRequiredMixin, FilteredListViewMixin, ListView):
    model = MaterialOrder
    template_name = 'Inventory/material_orders.html'
    context_object_name = 'orders'
    paginate_by = 25
    filter_type = 'material_orders'  # <-- Add this

    def get_queryset(self):
        # FilteredListViewMixin.get_queryset() handles filtering
        return super().get_queryset().order_by('-date_requested')
```

---

### **Example 2: Update Material Status (Detail + Update)**

**Before:**
```python
@require_POST
def update_material_status(request, order_id, new_status):
    order = MaterialOrder.objects.get(id=order_id)
    order.status = new_status
    order.save()
    return JsonResponse({'success': True})
```

**After:**
```python
from Inventory.permissions import require_object_access
from django.views.decorators.http import require_POST

@require_POST
@require_object_access('MaterialOrder', obj_id_kwarg='order_id', permission='edit')
def update_material_status(request, order_id, new_status):
    # order already validated by decorator; access it from request or DB
    order = request.accessed_object
    order.status = new_status
    order.last_updated_by = request.user
    order.updated_at = timezone.now()
    order.save()
    
    # Log this action for audit
    from Inventory.models import MaterialOrderAudit
    MaterialOrderAudit.objects.create(
        order=order,
        action=f"Status updated to {new_status}",
        performed_by=request.user
    )
    
    return JsonResponse({'success': True})
```

---

### **Example 3: Release Letter Detail View**

**Before:**
```python
class ReleaseLetterDetailView(LoginRequiredMixin, DetailView):
    model = ReleaseLetter
    template_name = 'Inventory/release_letter_detail.html'
    context_object_name = 'release_letter'
```

**After:**
```python
from Inventory.permissions import UserOwnsObjectMixin

class ReleaseLetterDetailView(LoginRequiredMixin, UserOwnsObjectMixin, DetailView):
    model = ReleaseLetter
    template_name = 'Inventory/release_letter_detail.html'
    context_object_name = 'release_letter'
    # UserOwnsObjectMixin enforces access check; raises Http404 if denied
```

---

## 1.3 Update All API Endpoints to Filter by User

### **Cascading Dropdown APIs**

**File:** `Inventory/views/data_views.py`

**Before:**
```python
@login_required
def get_boq_data(request):
    boq_data = {
        'regions': list(BillOfQuantity.objects.values_list('region', flat=True).distinct()),
        'districts': list(BillOfQuantity.objects.values_list('district', flat=True).distinct()),
        ...
    }
    return JsonResponse(boq_data)
```

**After:**
```python
from Inventory.permissions import filter_user_boq

@login_required
def get_boq_data(request):
    user_boqs = filter_user_boq(BillOfQuantity.objects.all(), request.user)
    
    boq_data = {
        'regions': list(user_boqs.values_list('region', flat=True).distinct()),
        'districts': list(user_boqs.values_list('district', flat=True).distinct()),
        ...
    }
    return JsonResponse(boq_data)
```

---

## 1.4 Write Tests for Authorization

**File:** `Inventory/tests/test_authorization.py` (new)

```python
"""
Tests for row-level access control.
Ensures users can only access records they own or are assigned to.
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from Inventory.models import MaterialOrder, ReleaseLetter, BillOfQuantity
from Inventory.permissions import user_can_view, user_can_edit
import json


class AuthorizationTestCase(TestCase):
    
    def setUp(self):
        """Set up test users, groups, and objects."""
        # Create users
        self.superuser = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='admin123'
        )
        self.user1 = User.objects.create_user(
            username='user1', email='user1@test.com', password='pass123'
        )
        self.user2 = User.objects.create_user(
            username='user2', email='user2@test.com', password='pass123'
        )
        
        # Create groups
        self.group1 = Group.objects.create(name='Schedule Officers')
        self.user1.groups.add(self.group1)
        
        # Create test material orders
        self.order_user1 = MaterialOrder.objects.create(
            name='Order by User1',
            quantity=100,
            code='ORD001',
            created_by=self.user1,
            status='Draft'
        )
        
        self.order_user2 = MaterialOrder.objects.create(
            name='Order by User2',
            quantity=200,
            code='ORD002',
            created_by=self.user2,
            status='Draft'
        )
        
        self.client = Client()
    
    def test_user_can_view_own_order(self):
        """User1 should see their own order."""
        self.assertTrue(user_can_view(self.order_user1, self.user1))
    
    def test_user_cannot_view_other_user_order(self):
        """User1 should NOT see User2's order."""
        self.assertFalse(user_can_view(self.order_user2, self.user1))
    
    def test_superuser_can_view_all(self):
        """Superuser should see all orders."""
        self.assertTrue(user_can_view(self.order_user1, self.superuser))
        self.assertTrue(user_can_view(self.order_user2, self.superuser))
    
    def test_user_can_edit_own_draft_order(self):
        """User1 can edit their own draft order."""
        self.assertTrue(user_can_edit(self.order_user1, self.user1))
    
    def test_user_cannot_edit_after_approval(self):
        """User1 cannot edit order once status != Draft."""
        self.order_user1.status = 'Approved'
        self.order_user1.save()
        self.assertFalse(user_can_edit(self.order_user1, self.user1))
    
    def test_material_orders_list_filters_by_user(self):
        """GET /material-orders/ should only return user's orders."""
        self.client.login(username='user1', password='pass123')
        response = self.client.get(reverse('material_orders'))
        
        self.assertEqual(response.status_code, 200)
        orders = response.context['orders']
        
        # Should contain only user1's order
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].created_by, self.user1)
    
    def test_material_order_detail_idor_blocked(self):
        """GET /material-orders/2/ should return 404 if user1 doesn't own it."""
        self.client.login(username='user1', password='pass123')
        # Try to access user2's order
        response = self.client.get(
            reverse('material_order_detail', kwargs={'pk': self.order_user2.pk})
        )
        
        # Should be 404 (not 403, to not leak object existence)
        self.assertEqual(response.status_code, 404)
    
    def test_material_order_update_idor_blocked(self):
        """POST to update user2's order should fail for user1."""
        self.client.login(username='user1', password='pass123')
        response = self.client.post(
            reverse('update_material_status', 
                   kwargs={'order_id': self.order_user2.pk, 'new_status': 'Approved'})
        )
        
        self.assertEqual(response.status_code, 404)
        
        # Verify status wasn't actually changed
        self.order_user2.refresh_from_db()
        self.assertEqual(self.order_user2.status, 'Draft')
```

**Run tests:**
```bash
python manage.py test Inventory.tests.test_authorization -v 2
```

---

## 1.5 Create Migration Script for Audit Logging

**File:** `Inventory/migrations/audit_baseline.py`

Ensure `MaterialOrderAudit` is actively used on all mutations. Add a management command to backfill existing actions:

```python
# Inventory/management/commands/backfill_audit_log.py

from django.core.management.base import BaseCommand
from Inventory.models import MaterialOrder, MaterialOrderAudit

class Command(BaseCommand):
    help = 'Backfill audit log for existing orders without audit entries'
    
    def handle(self, *args, **options):
        for order in MaterialOrder.objects.all():
            if not MaterialOrderAudit.objects.filter(order=order).exists():
                MaterialOrderAudit.objects.create(
                    order=order,
                    action='backfill: order created',
                    performed_by=order.created_by
                )
        
        self.stdout.write(self.style.SUCCESS('Audit log backfilled'))
```

Run:
```bash
python manage.py backfill_audit_log
```

---

## **PHASE 1 DELIVERABLES**

- ✅ `Inventory/permissions.py` with row-level filtering functions
- ✅ All MaterialOrder, ReleaseLetter, BillOfQuantity views updated
- ✅ Test suite covering IDOR scenarios
- ✅ All API endpoints filtered by user
- ✅ Audit logging enabled on mutations

**Timeline:** 2 weeks  
**Effort:** ~40 dev hours (high complexity; pair program for auth changes)  
**Testing:** Run full test suite + manual smoke tests on staging

---

# PHASE 2: API & DATA SECURITY (Weeks 3–4)

## **Objective**
Protect unauthenticated data exposure, add rate limiting, harden error handling, validate file uploads.

---

## 2.1 Protect Unauthenticated API Endpoints

### **Before:**
```python
# Inventory/views/data_views.py
def list_categories(request):
    categories = list(Category.objects.values('id', 'name'))
    return JsonResponse({'categories': categories})
```

### **After:**
```python
from django.contrib.auth.decorators import login_required

@login_required
def list_categories(request):
    categories = list(Category.objects.values('id', 'name'))
    return JsonResponse({'categories': categories})


@login_required
def list_units(request):
    units = list(Unit.objects.values('id', 'name'))
    return JsonResponse({'units': units})
```

**Audit all endpoints in `urls.py` that start with `/api/` — add `@login_required` to every one.**

---

## 2.2 Implement Rate Limiting

### **Install django-ratelimit:**
```bash
pip install django-ratelimit
```

### **Update settings.py:**
```python
# settings.py

# Rate limiting
RATELIMIT_ENABLE = not DEBUG
RATELIMIT_USE_CACHE = 'default'  # Requires Redis in production
RATELIMIT_VIEW = '5/m'  # 5 requests per minute (default; override per view)

# Cache configuration for rate limiting
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/1'),
    }
}
```

### **Apply to high-risk endpoints:**

```python
# Inventory/views/data_views.py

from django_ratelimit.decorators import ratelimit
from django.contrib.auth.decorators import login_required

@login_required
@ratelimit(key='user', rate='100/h', method='GET')  # 100 GETs per hour per user
def get_boq_data(request):
    """Cascading dropdown data — limit to prevent enumeration attacks."""
    ...

@login_required
@ratelimit(key='user', rate='10/h', method='POST')  # 10 uploads per hour per user
def upload_inventory(request):
    """File upload endpoint — strict rate limit."""
    ...

@login_required
@ratelimit(key='user', rate='50/h', method='GET')  # API access
def ghana_map_data_api(request):
    ...
```

---

## 2.3 Validate File Uploads

### **Install python-magic:**
```bash
pip install python-magic-bin  # Windows/Mac; use python-magic on Linux
```

### **Create upload validator:**

```python
# Inventory/utils/file_validation.py

import magic
import os
import logging

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',  # .xlsx
    'application/vnd.ms-excel',  # .xls
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def validate_excel_upload(uploaded_file):
    """
    Validate an uploaded Excel file.
    Returns (is_valid, error_message).
    """
    # Check file size
    if uploaded_file.size > MAX_FILE_SIZE:
        return False, f"File exceeds {MAX_FILE_SIZE // (1024*1024)}MB limit"
    
    # Check MIME type
    file_mime = magic.from_buffer(uploaded_file.read(1024), mime=True)
    uploaded_file.seek(0)  # Reset file pointer
    
    if file_mime not in ALLOWED_MIME_TYPES:
        logger.warning(
            f"Invalid MIME type {file_mime} for upload by {uploaded_file.name}"
        )
        return False, "Invalid file type. Please upload an Excel file (.xlsx or .xls)"
    
    # Check file extension
    valid_extensions = {'.xlsx', '.xls'}
    _, ext = os.path.splitext(uploaded_file.name)
    if ext.lower() not in valid_extensions:
        return False, "Invalid file extension. Please upload .xlsx or .xls"
    
    return True, None
```

### **Update upload views:**

```python
# Inventory/views/data_views.py

from Inventory.utils.file_validation import validate_excel_upload

class UploadInventoryView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.is_superuser

    def post(self, request):
        form = ExcelUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = request.FILES['file']
            
            # Validate file
            is_valid, error = validate_excel_upload(file)
            if not is_valid:
                messages.error(request, error)
                return render(request, self.template_name, {'form': form})
            
            try:
                df = pd.read_excel(file, engine='openpyxl')
                # ... rest of processing
            except Exception as e:
                # Return generic error, log full error
                logger.exception(f"Error processing Excel file: {e}")
                messages.error(request, "An error occurred processing your file. Please contact support.")
                return render(request, self.template_name, {'form': form})
```

---

## 2.4 Generic Error Messages

### **Create error handler middleware:**

```python
# Inventory/middleware.py (add to existing file)

class ErrorResponseMiddleware(MiddlewareMixin):
    """
    Sanitize error messages shown to users.
    Log full errors server-side.
    """
    def process_exception(self, request, exception):
        import traceback
        
        # Log full exception server-side
        logger.exception(
            f"Unhandled exception for {request.user} on {request.path}",
            exc_info=exception
        )
        
        # Don't return the exception details to client in production
        if not settings.DEBUG:
            from django.http import JsonResponse
            if 'application/json' in request.META.get('HTTP_ACCEPT', ''):
                return JsonResponse(
                    {'error': 'An error occurred. Please contact support.'},
                    status=500
                )
        
        return None  # Let Django's default handler take over
```

### **Register in settings.py:**
```python
MIDDLEWARE = [
    # ... existing middleware
    'Inventory.middleware.ErrorResponseMiddleware',  # Add this
]
```

### **Update all exception handlers in views:**

```python
# Before:
except Exception as e:
    messages.error(request, f"Error processing file: {e}")

# After:
except Exception as e:
    logger.exception(f"File upload error for user {request.user}")
    messages.error(request, "An error occurred. Please try again or contact support.")
```

---

## 2.5 Add CSP Headers

### **Update settings.py:**

```python
# Content Security Policy
SECURE_CONTENT_SECURITY_POLICY = {
    "default-src": ("'self'",),
    "script-src": (
        "'self'",
        "cdn.jsdelivr.net",  # For Plotly, Chart.js
        "cdn.plot.ly",       # Plotly CDN
    ),
    "style-src": (
        "'self'",
        "cdn.jsdelivr.net",
        "'unsafe-inline'",  # For inline Bootstrap styles (minimize later)
    ),
    "img-src": ("'self'", "data:", "https:"),
    "font-src": ("'self'", "fonts.gstatic.com"),
    "connect-src": ("'self'",),
    "frame-ancestors": ("'none'",),
    "base-uri": ("'self'",),
    "form-action": ("'self'",),
}
```

---

## **PHASE 2 DELIVERABLES**

- ✅ All API endpoints require authentication
- ✅ Rate limiting configured and tested
- ✅ File upload validation (MIME + magic bytes)
- ✅ Generic error messages in production
- ✅ CSP headers enforced
- ✅ Error logging centralized

**Timeline:** 2 weeks  
**Effort:** ~20 dev hours  
**Testing:** Load test with rate limit limits; malicious file upload tests

---

# PHASE 3: INFRASTRUCTURE & OBSERVABILITY (Weeks 5–6)

## **Objective**
Database migration, secrets management, CI/CD security scanning, audit logging.

---

## 3.1 Migrate SQLite → PostgreSQL

### **Provision PostgreSQL on Azure:**

```bash
# Azure CLI
az postgres server create \
  --resource-group moen-rg \
  --name moen-postgres-prod \
  --location uksouth \
  --admin-user moen_admin \
  --admin-password '<STRONG_PASSWORD>' \
  --sku-name B_Gen5_2 \
  --storage-size 51200
```

### **Update Django settings:**

```python
# settings.py

if not DEBUG:
    database_url = os.getenv('SCHEMATOGO_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise ImproperlyConfigured(
            "SCHEMATOGO_URL or DATABASE_URL required in production"
        )
    DATABASES['default'] = dj_database_url.config(default=database_url)
else:
    # Keep SQLite for local development
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
```

### **Migration steps:**

1. **Dump current SQLite data:**
   ```bash
   python manage.py dumpdata > backup.json
   ```

2. **Update requirements.txt:**
   ```
   psycopg2-binary>=2.9.9
   ```

3. **Migrate on staging first:**
   ```bash
   python manage.py migrate --database=production
   ```

4. **Load data:**
   ```bash
   python manage.py loaddata backup.json --database=production
   ```

5. **Validate data integrity:**
   ```bash
   python manage.py shell
   >>> from Inventory.models import MaterialOrder
   >>> MaterialOrder.objects.count()  # Should match before migration
   ```

---

## 3.2 Secrets Rotation & Environment Management

### **Create `.env.example` (commit to repo):**

```bash
# .env.example — commit this; actual .env goes in deployment only
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<generate-with-django-secret-key-generator>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,moen-ims-prod.azurewebsites.net

# Database
SCHEMATOGO_URL=postgresql://user:pass@moen-postgres-prod.postgres.database.azure.com:5432/moen_db

# Microsoft OAuth
MS_CLIENT_ID=<from-azure-app-registration>
MS_CLIENT_SECRET=<from-azure-key-vault>
MS_TENANT_ID=<your-tenant-id>
MS_REDIRECT_URI=https://moen-ims-prod.azurewebsites.net/auth/callback/

# Encryption
TOKEN_ENCRYPTION_KEY=<generate-with-cryptography>

# Trusted admins (comma-separated, env-var only)
TRUSTED_ADMIN_EMAILS=leslie.adjetey@energymin.gov.gh,another.admin@energymin.gov.gh

# Optional
SENTRY_DSN=<if-using-sentry>
REDIS_URL=redis://localhost:6379/1
```

### **Update settings.py to enforce secrets:**

```python
# settings.py

def _require_env(key, fallback=None):
    """Require environment variable; raise error if missing in production."""
    value = os.environ.get(key, fallback)
    if not value and not DEBUG:
        raise ImproperlyConfigured(
            f"{key} environment variable is required in production. "
            f"Set it in your deployment environment."
        )
    return value

DJANGO_SECRET_KEY = _require_env('DJANGO_SECRET_KEY')
TOKEN_ENCRYPTION_KEY = _require_env('TOKEN_ENCRYPTION_KEY')
MS_CLIENT_SECRET = _require_env('MS_CLIENT_SECRET')
```

### **Rotate secrets in Azure Key Vault:**

```bash
# Generate new TOKEN_ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Update in Key Vault
az keyvault secret set \
  --vault-name moen-kv \
  --name TOKEN-ENCRYPTION-KEY \
  --value "new-key-value"

# Redeploy app (App Service will pull new value)
az webapp deployment slot swap \
  --resource-group moen-rg \
  --name moen-ims-prod \
  --slot staging
```

---

## 3.3 Audit Logging for Sensitive Operations

### **Create audit app:**

```python
# Inventory/services/audit.py

import json
import logging
from django.utils import timezone
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

def audit(user, subject, action, details=None):
    """
    Log a sensitive action for audit trail.
    
    Args:
        user: User performing the action
        subject: User or object being affected
        action: Action code (e.g., 'auth.superuser_auto_promoted')
        details: Dict with additional context
    """
    from Inventory.models import AuditLog  # Assumes model exists
    
    AuditLog.objects.create(
        user=user,
        subject_type='user' if isinstance(subject, User) else 'object',
        subject_id=subject.id if hasattr(subject, 'id') else str(subject),
        action=action,
        details=json.dumps(details or {}),
        timestamp=timezone.now(),
    )
    
    logger.warning(
        f"AUDIT: {user.username} performed {action} on {subject}. "
        f"Details: {details}"
    )
```

### **Add AuditLog model:**

```python
# Inventory/models.py (add to end)

class AuditLog(models.Model):
    """
    Immutable audit trail for sensitive operations.
    """
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    subject_type = models.CharField(max_length=50)  # 'user', 'order', 'release_letter'
    subject_id = models.CharField(max_length=100)
    action = models.CharField(max_length=100)  # 'create', 'approve', 'delete'
    details = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} {self.action} {self.subject_type}:{self.subject_id}"
```

### **Call audit on sensitive operations:**

```python
# Inventory/views/main_views.py

@require_POST
@require_object_access('MaterialOrder', obj_id_kwarg='order_id', permission='edit')
def update_material_status(request, order_id, new_status):
    from Inventory.services.audit import audit
    
    order = request.accessed_object
    old_status = order.status
    order.status = new_status
    order.last_updated_by = request.user
    order.save()
    
    # Log the action
    audit(
        user=request.user,
        subject=order,
        action='material_order.status_updated',
        details={
            'order_id': order.id,
            'old_status': old_status,
            'new_status': new_status,
            'timestamp': str(timezone.now()),
        }
    )
    
    return JsonResponse({'success': True})
```

---

## 3.4 CI/CD Security Scanning

### **Update `.github/workflows/main_moen-ims.yml`:**

```yaml
name: Tests & Security

on: [push, pull_request]

jobs:
  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install bandit safety pip-audit
      
      - name: Run Bandit (code security)
        run: bandit -r Inventory -f json -o bandit-report.json || true
      
      - name: Check for vulnerable dependencies
        run: pip-audit
      
      - name: Check for known CVEs
        run: safety check || true
  
  tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: moen_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-django pytest-cov
      
      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/moen_test
          DJANGO_SECRET_KEY: test-key-only
        run: |
          pytest --cov=Inventory --cov-report=xml
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
```

---

## **PHASE 3 DELIVERABLES**

- ✅ PostgreSQL provisioned and migrated
- ✅ Secrets rotated in Key Vault
- ✅ Audit logging implemented for sensitive ops
- ✅ CI/CD includes Bandit, safety, pip-audit
- ✅ Test coverage tracked in CI

**Timeline:** 2 weeks  
**Effort:** ~30 dev hours (database migration is largest task)  
**Testing:** Run full test suite against PostgreSQL

---

# TESTING & VALIDATION STRATEGY

## **Unit Tests**

All code in Phase 1–3 should have corresponding tests.

```bash
# Run all tests
python manage.py test Inventory -v 2

# Run with coverage
pip install coverage
coverage run --source='Inventory' manage.py test
coverage report
coverage html  # View in htmlcov/index.html
```

## **Integration Tests**

```bash
# Test authorization end-to-end
pytest Inventory/tests/test_authorization.py -v

# Test file upload validation
pytest Inventory/tests/test_file_validation.py -v
```

## **Security Tests**

```bash
# Bandit (SAST)
bandit -r Inventory -f txt

# Safety (dependency check)
safety check

# Type checking
mypy Inventory --strict
```

## **Staging Validation**

Before production deployment:

1. **Smoke test all sensitive workflows:**
   - Create material order → Approve → Release → Transport
   - Upload Excel file (valid + invalid)
   - Access objects as non-superuser (should 404)

2. **Load test rate limits:**
   ```bash
   ab -n 1000 -c 100 https://staging.moen-ims.org/api/boq-data/
   ```

3. **Check logs for errors:**
   ```bash
   az webapp log tail --name moen-ims-staging --resource-group moen-rg
   ```

---

# DEPLOYMENT CHECKLIST

## **Pre-Deployment**

- [ ] All Phase 1–3 code reviewed and tested
- [ ] Tests pass locally (`python manage.py test`)
- [ ] Tests pass in CI pipeline
- [ ] Database backup taken (`pg_dump`)
- [ ] Secrets rotated and verified in Key Vault
- [ ] TRUSTED_ADMIN_EMAILS env var set (remove hardcoded email)
- [ ] DATABASE_URL / SCHEMATOGO_URL configured
- [ ] Staging environment validated

## **Deployment (Azure App Service)**

```bash
# Deploy code
git push origin main  # Triggers GitHub Actions CI/CD

# Verify deployment
az webapp show --name moen-ims-prod --query state

# Check logs
az webapp log tail --name moen-ims-prod --resource-group moen-rg

# Run database migrations
az webapp remote-call --name moen-ims-prod --script-type python --script-location scripts/migrate.py
```

OR manually:

```bash
# SSH into App Service
az webapp create-remote-connection --subscription <sub-id> --resource-group moen-rg --name moen-ims-prod

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Restart app
az webapp restart --name moen-ims-prod --resource-group moen-rg
```

## **Post-Deployment**

- [ ] Verify app loads on production URL
- [ ] Test a few sensitive workflows (order create/approve/release)
- [ ] Check error logs for exceptions
- [ ] Verify Sentry is receiving events
- [ ] Verify rate limiting is active (`X-RateLimit-*` headers)
- [ ] Verify CSP headers present (`curl -I https://moen-ims-prod.azurewebsites.net`)
- [ ] Run security scan: `bandit -r Inventory`
- [ ] Test file upload with valid + invalid files
- [ ] Spot-check audit logs

---

# TIMELINE SUMMARY

| Phase | Duration | Key Deliverables | Effort |
|-------|----------|------------------|--------|
| **1: Authorization** | 2 weeks | Row-level filtering, IDOR fixes, tests | 40h |
| **2: API Security** | 2 weeks | Rate limiting, file validation, error handling | 20h |
| **3: Infrastructure** | 2 weeks | PostgreSQL migration, audit logging, CI/CD | 30h |
| **Testing & Validation** | Ongoing | Coverage tracking, security scanning | 15h |
| **TOTAL** | 6 weeks | **Production-ready system** | **105h** |

---

# SUCCESS CRITERIA

After completing this plan, MOEN-IMS will have:

✅ **Score: 75+/100** (up from 58)  
✅ **Zero IDOR vulnerabilities**  
✅ **Row-level access control on all sensitive data**  
✅ **PostgreSQL in production** (reliable, scalable)  
✅ **Rate limiting** on all APIs  
✅ **Audit trail** for sensitive operations  
✅ **Security scanning** in CI/CD pipeline  
✅ **Type hints** on critical functions  
✅ **Comprehensive test coverage** (>80%)  

---

**Next Step:** Create GitHub issues for each phase. Assign to team members. Start Phase 1 this week.

Need clarification on any section? Ask!
