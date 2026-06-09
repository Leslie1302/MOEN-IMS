# MOEN IMS Scaling Implementation Plan

> **Document Version:** 1.0  
> **Created:** 2025-06-07  
> **Scope:** Production scaling from single-instance SQLite to multi-instance PostgreSQL architecture  
> **Estimated Timeline:** 4–6 weeks (phased rollout)  
> **Risk Level:** Medium (database migration is the critical path)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Phase 1: Database Migration (Week 1)](#2-phase-1-database-migration-week-1)
3. [Phase 2: Redis & Shared State (Week 1–2)](#3-phase-2-redis--shared-state-week-12)
4. [Phase 3: Azure Blob Storage for Media (Week 2)](#4-phase-3-azure-blob-storage-for-media-week-2)
5. [Phase 4: Celery Background Tasks (Week 3–4)](#5-phase-4-celery-background-tasks-week-34)
6. [Phase 5: Query Optimization (Week 5)](#6-phase-5-query-optimization-week-5)
7. [Phase 6: CDN & Static Assets (Week 5–6)](#7-phase-6-cdn--static-assets-week-56)
8. [Phase 7: Monitoring & Alerting (Ongoing)](#8-phase-7-monitoring--alerting-ongoing)
9. [Rollback Procedures](#9-rollback-procedures)
10. [Appendix A: Azure Resource Provisioning](#appendix-a-azure-resource-provisioning)
11. [Appendix B: Environment Variable Reference](#appendix-b-environment-variable-reference)

---

## 1. Executive Summary

### Current Architecture

| Component | Current | Limitation |
|-----------|---------|------------|
| Database | SQLite (file-based) | Single-writer lock; concurrent users → "database is locked" |
| Cache | LocMemCache (in-process) | No sharing across App Service instances |
| File Storage | Local filesystem (`/home/site/data/`) | Tied to single instance; no CDN |
| Task Processing | Synchronous (request thread) | PDF/Excel generation blocks user |
| Static Assets | WhiteNoise (Python-served) | Consumes worker threads for CSS/JS |

### Target Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Azure App Service (2+ instances)           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │  Django G1  │  │  Django G2  │  │  Django G3  │           │
│  │  (gunicorn) │  │  (gunicorn) │  │  (gunicorn) │           │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘           │
└─────────┼────────────────┼────────────────┼─────────────────┘
          │                │                │
          └────────────────┴────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌────────────┐  ┌──────────────┐  ┌──────────────┐
   │  Azure     │  │  Azure Cache │  │  Azure Blob  │
   │  PostgreSQL│  │  for Redis   │  │  Storage     │
   │  (Primary) │  │  (Sessions + │  │  (Media +    │
   │            │  │   Cache +    │  │   Backups)   │
   │  [Read     │  │   Celery     │  │              │
   │   Replica] │  │   Broker]    │  │              │
   └────────────┘  └──────────────┘  └──────────────┘
                           │
                    ┌──────┴──────┐
                    ▼             ▼
            ┌────────────┐  ┌────────────┐
            │  Celery    │  │  Celery    │
            │  Worker 1  │  │  Worker 2  │
            │  (PDF/     │  │  (Reports/ │
            │   Excel)   │  │   Imports) │
            └────────────┘  └────────────┘
```

### Success Criteria

- [ ] Support 50+ concurrent users without "database is locked" errors
- [ ] PDF/Excel generation completes in <30 seconds (background) without blocking UI
- [ ] Zero-downtime deployments with persistent media
- [ ] Session state survives instance restart / scaling event
- [ ] Dashboard page load <2 seconds (95th percentile)

---

## 2. Phase 1: Database Migration (Week 1)

> **Critical Path.** Everything else depends on this.  
> **Risk:** Data loss if migration fails. **Test on staging first.**

### 2.1 Provision Azure Database for PostgreSQL Flexible Server

```bash
# Azure CLI (run from Azure Cloud Shell or local with az login)
RESOURCE_GROUP="moen-ims-prod"
LOCATION="uksouth"
SERVER_NAME="moen-ims-db-$(date +%s)"  # unique

az group create --name $RESOURCE_GROUP --location $LOCATION

az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $SERVER_NAME \
  --location $LOCATION \
  --admin-user moenadmin \
  --admin-password "$(openssl rand -base64 24)" \
  --sku-name Standard_B2s \
  --tier Burstable \
  --storage-size 32 \
  --version 15 \
  --public-access 0.0.0.0 \
  --database-name moenims \
  --yes

# Allow Azure App Service subnet (or all Azure IPs for simplicity)
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $SERVER_NAME \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

> **Note:** `Standard_B2s` is the minimum. For 50+ users, upgrade to `Standard_D2s_v3` or higher.

### 2.2 Update `requirements.txt`

```diff
  django-crispy-forms>=2.0
  crispy-bootstrap5>=0.7
  gunicorn>=23.0.0
  whitenoise>=6.0.0
  Pillow>=9.0.0
  pandas>=2.0.0
  openpyxl>=3.0.0
  plotly>=5.18.0
  seaborn>=0.13.0
  reportlab>=4.0.0
  matplotlib>=3.9.0
  dj-database-url>=1.0.0,<2.0.0
  psycopg2-binary>=2.9.9
  python-dotenv>=1.0.0
  django-auto-prefetch>=1.14.0
  qrcode[pil]>=7.4.2
  PyMuPDF>=1.24.0
  opencv-python-headless>=4.8.0
  django-otp>=1.3.0
  pyotp>=2.9.0
  Django==5.1.5
  msal>=1.31.0
  requests>=2.32.3
  cryptography>=44.0.0
+ 
+ # --- Scaling additions ---
+ django-storages[azure]>=1.14.0    # Azure Blob Storage
+ azure-identity>=1.15.0           # Managed identity auth
+ celery[redis]>=5.3.0             # Background tasks
+ django-celery-results>=2.5.0       # Celery result backend in DB
+ django-celery-beat>=2.5.0        # Scheduled tasks
+ redis>=5.0.0                     # Redis client
+ hiredis>=2.2.0                   # Faster Redis parser
+ django-debug-toolbar>=4.3.0      # Dev only: query profiling
```

### 2.3 Create Staging Environment

**Duplicate your App Service slot or create a new one:**

```bash
az webapp deployment slot create \
  --resource-group $RESOURCE_GROUP \
  --name moen-ims-app \
  --slot staging
```

Set staging environment variables:

| Variable | Value | Slot |
|----------|-------|------|
| `DATABASE_URL` | `postgres://moenadmin:PASSWORD@moen-ims-db.postgres.database.azure.com:5432/moenims` | staging |
| `ALLOW_SQLITE_IN_PROD` | *(unset)* | staging |
| `DJANGO_DEBUG` | `False` | staging |

### 2.4 Database Migration Script

Create `IMS/Inventory_management_system/migrate_to_postgres.py`:

```python
#!/usr/bin/env python
"""
One-shot migration script: SQLite → PostgreSQL.
Run on staging first. Requires both databases configured.
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.core.management import call_command
from django.db import connections

def migrate_data():
    """
    Strategy: Use Django's dumpdata/loaddata with natural keys.
    For large datasets, use pgloader or custom SQL.
    """
    print("Step 1: Verify PostgreSQL connection...")
    pg = connections['default']
    pg.ensure_connection()
    print(f"  ✓ Connected to: {pg.settings_dict['HOST']}")

    print("\nStep 2: Run migrations on PostgreSQL...")
    call_command('migrate', '--run-syncdb', verbosity=1)

    print("\nStep 3: Dump data from SQLite (excluding contenttypes)...")
    # Exclude contenttypes and auth.permission — they conflict on loaddata
    call_command(
        'dumpdata',
        '--exclude', 'contenttypes',
        '--exclude', 'auth.permission',
        '--exclude', 'sessions',
        '--natural-primary',
        '--natural-foreign',
        '--indent', '2',
        '--output', '/tmp/moen_ims_dump.json'
    )
    print("  ✓ Dump saved to /tmp/moen_ims_dump.json")

    print("\nStep 4: Load data into PostgreSQL...")
    call_command('loaddata', '/tmp/moen_ims_dump.json')

    print("\nStep 5: Verify row counts...")
    from django.contrib.auth.models import User
    from Inventory.models import ReleaseLetter, InventoryItem, Project
    print(f"  Users: {User.objects.count()}")
    print(f"  ReleaseLetters: {ReleaseLetter.objects.count()}")
    print(f"  InventoryItems: {InventoryItem.objects.count()}")
    print(f"  Projects: {Project.objects.count()}")

    print("\n✅ Migration complete. Test the staging app now.")

if __name__ == '__main__':
    migrate_data()
```

**Run on staging:**

```bash
cd IMS/Inventory_management_system
python migrate_to_postgres.py
```

### 2.5 Alternative: pgloader (For Large Datasets >1GB)

If `dumpdata` is too slow, use `pgloader` (runs in minutes):

```bash
# Install pgloader (Ubuntu/Debian)
sudo apt-get install pgloader

# Create target schema first
createdb moenims

# Run migration
pgloader \
  sqlite:///home/site/data/db.sqlite3 \
  pgsql://moenadmin:PASSWORD@moen-ims-db.postgres.database.azure.com:5432/moenims
```

### 2.6 Update `settings.py` — Database Section

Your `settings.py` already has the correct structure. Just ensure these env vars are set in production:

```bash
# Azure App Service → Configuration → Application settings
DATABASE_URL=postgres://moenadmin:PASSWORD@moen-ims-db.postgres.database.azure.com:5432/moenims?sslmode=require
DB_CONN_MAX_AGE=60
DB_SSL_REQUIRE=True
# REMOVE: ALLOW_SQLITE_IN_PROD (or set to empty)
```

### 2.7 Verification Checklist

- [ ] Staging app loads without errors
- [ ] Login works (user passwords migrated)
- [ ] Release letter list displays correctly
- [ ] PDF download works (files still local for now)
- [ ] Admin dashboard loads
- [ ] Run `python manage.py test` — all tests pass

---

## 3. Phase 2: Redis & Shared State (Week 1–2)

### 3.1 Provision Azure Cache for Redis

```bash
az redis create \
  --resource-group $RESOURCE_GROUP \
  --name moen-ims-redis \
  --location $LOCATION \
  --sku Basic \
  --vm-size c0 \
  --enable-non-ssl-port false

# Get connection string
az redis list-keys \
  --resource-group $RESOURCE_GROUP \
  --name moen-ims-redis
```

> **Upgrade to `Standard` SKU for production SLA and clustering.**

### 3.2 Update Environment Variables

```bash
REDIS_URL=rediss://:PRIMARY_KEY@moen-ims-redis.redis.cache.windows.net:6380/0
```

### 3.3 Update `settings.py` — Cache & Sessions

Add to `settings.py` (after existing cache block):

```python
# =============================================================================
# SESSIONS — Use Redis in production (required for multi-instance)
# =============================================================================
if _redis_url:
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
    # Optional: longer session for inventory officers
    SESSION_COOKIE_AGE = 8 * 60 * 60  # 8 hours

# =============================================================================
# AXES (brute-force protection) — Use cache in production
# =============================================================================
AXES_CACHE = 'default'  # Already set via RATELIMIT_USE_CACHE

# =============================================================================
# RATELIMIT — Already configured, now backed by Redis
# =============================================================================
# No changes needed — RATELIMIT_USE_CACHE = 'default' already works
```

### 3.4 Verification

```python
# Django shell
python manage.py shell
>>> from django.core.cache import cache
>>> cache.set('test_key', 'hello', 30)
>>> cache.get('test_key')
'hello'
```

Check Azure Portal → Redis → Metrics → `Cache Hits` / `Cache Misses`.

---

## 4. Phase 3: Azure Blob Storage for Media (Week 2)

### 4.1 Provision Storage Account

```bash
az storage account create \
  --name moenimsmedia \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS \
  --kind StorageV2 \
  --access-tier Hot \
  --allow-blob-public-access false

# Create container
az storage container create \
  --name media \
  --account-name moenimsmedia \
  --auth-mode login

# Get connection string
az storage account show-connection-string \
  --name moenimsmedia \
  --resource-group $RESOURCE_GROUP
```

### 4.2 Update `settings.py` — Storage Backend

Add to `settings.py`:

```python
# =============================================================================
# AZURE BLOB STORAGE — Media files (release letters, stamps, QR scans)
# =============================================================================
AZURE_STORAGE_CONNECTION_STRING = os.environ.get('AZURE_STORAGE_CONNECTION_STRING', '')

if AZURE_STORAGE_CONNECTION_STRING and not DEBUG:
    DEFAULT_FILE_STORAGE = 'storages.backends.azure_storage.AzureStorage'
    AZURE_CONTAINER = 'media'
    AZURE_CONNECTION_STRING = AZURE_STORAGE_CONNECTION_STRING
    # Optional: custom domain with CDN later
    # AZURE_CUSTOM_DOMAIN = 'cdn.moen-ims.org'
else:
    # Local dev fallback
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
```

### 4.3 Migrate Existing Media Files

Create `IMS/Inventory_management_system/migrate_media_to_azure.py`:

```python
#!/usr/bin/env python
"""Upload existing local media files to Azure Blob Storage."""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.core.files.storage import default_storage
from django.conf import settings
from pathlib import Path

def migrate_media():
    media_root = Path(settings.MEDIA_ROOT)
    if not media_root.exists():
        print("No local media to migrate.")
        return

    for file_path in media_root.rglob('*'):
        if file_path.is_file():
            relative = file_path.relative_to(media_root).as_posix()
            print(f"Uploading: {relative}")
            with open(file_path, 'rb') as f:
                default_storage.save(relative, f)

    print("\n✅ Media migration complete.")

if __name__ == '__main__':
    migrate_media()
```

### 4.4 Update Model FileField Paths (Optional Cleanup)

Your current `upload_to` paths are fine — `django-storages` handles the abstraction. Just verify:

```python
# In models/orders.py — no change needed
pdf_file = models.FileField(
    upload_to='release_letters/%Y/%m/%d/',
    ...
)
```

### 4.5 Verification

- [ ] Upload a new release letter → appears in Azure Portal → Storage Account → Containers → media
- [ ] Download existing release letter → serves from Azure
- [ ] Delete local `/home/site/data/media/` → app still works

---

## 5. Phase 4: Celery Background Tasks (Week 3–4)

> **Highest user-impact phase.** PDF generation currently blocks the request thread for 5–30 seconds.

### 5.1 Add Celery Configuration

Create `IMS/Inventory_management_system/Inventory_management_system/celery.py`:

```python
import os
from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')

app = Celery('Inventory_management_system')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Use Django's logging setup instead of Celery's default
@setup_logging.connect
def config_loggers(*args, **kwargs):
    from django.conf import settings
    from logging.config import dictConfig
    dictConfig(settings.LOGGING)
```

Update `IMS/Inventory_management_system/Inventory_management_system/__init__.py`:

```python
from .celery import app as celery_app

__all__ = ('celery_app',)
```

### 5.2 Add Celery Settings to `settings.py`

```python
# =============================================================================
# CELERY — Background task processing
# =============================================================================
CELERY_BROKER_URL = os.environ.get('REDIS_URL', '')
CELERY_RESULT_BACKEND = 'django-db'  # Uses django-celery-results
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes max per task
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Fair task distribution

# Beat schedule (weekly reports, cleanup)
CELERY_BEAT_SCHEDULE = {
    'generate-weekly-reports': {
        'task': 'Inventory.tasks.weekly_report.generate_all_reports',
        'schedule': 60 * 60 * 24 * 7,  # Every 7 days
    },
    'cleanup-old-tasks': {
        'task': 'Inventory.tasks.maintenance.cleanup_task_results',
        'schedule': 60 * 60 * 24,  # Daily
    },
}
```

### 5.3 Create Task Modules

Create directory structure:

```
IMS/Inventory_management_system/Inventory/tasks/
├── __init__.py
├── pdf_generation.py
├── excel_export.py
├── report_rendering.py
├── weekly_report.py
├── maintenance.py
└── notifications.py
```

#### `IMS/Inventory_management_system/Inventory/tasks/pdf_generation.py`

```python
from celery import shared_task
from django.core.files.base import ContentFile
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_release_letter_pdf(self, release_letter_id, user_id=None):
    """
    Generate PDF for a release letter asynchronously.
    Called from view: generate_release_letter_pdf.delay(letter.id, request.user.id)
    """
    from Inventory.models import ReleaseLetter
    from Inventory.utils.pdf_generator import ReleaseLetterPDFGenerator

    try:
        letter = ReleaseLetter.objects.select_related('uploaded_by').get(id=release_letter_id)
    except ReleaseLetter.DoesNotExist:
        logger.error(f"ReleaseLetter {release_letter_id} not found")
        return {'status': 'error', 'message': 'Release letter not found'}

    try:
        generator = ReleaseLetterPDFGenerator()
        pdf_bytes = generator.generate(letter)

        filename = f"release_letters/{letter.reference_number or letter.id}.pdf"
        letter.pdf_file.save(filename, ContentFile(pdf_bytes), save=True)

        logger.info(f"PDF generated for ReleaseLetter {release_letter_id}")
        return {
            'status': 'success',
            'file_url': letter.pdf_file.url,
            'letter_id': release_letter_id,
        }
    except Exception as exc:
        logger.exception(f"PDF generation failed for {release_letter_id}")
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2)
def generate_bulk_release_letters(self, letter_ids, user_id):
    """
    Generate multiple release letters in batch.
    Returns a zip file or individual URLs.
    """
    from Inventory.models import ReleaseLetter
    import zipfile
    import io

    results = []
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for letter_id in letter_ids:
            try:
                letter = ReleaseLetter.objects.get(id=letter_id)
                if letter.pdf_file:
                    zf.writestr(
                        f"{letter.reference_number or letter_id}.pdf",
                        letter.pdf_file.read()
                    )
                    results.append({'id': letter_id, 'status': 'included'})
                else:
                    results.append({'id': letter_id, 'status': 'missing_pdf'})
            except ReleaseLetter.DoesNotExist:
                results.append({'id': letter_id, 'status': 'not_found'})

    # Save zip to storage
    from django.core.files.storage import default_storage
    zip_filename = f"bulk_exports/release_letters_{self.request.id}.zip"
    default_storage.save(zip_filename, ContentFile(zip_buffer.getvalue()))

    return {
        'status': 'success',
        'download_url': default_storage.url(zip_filename),
        'processed': len(results),
        'results': results,
    }
```

#### `IMS/Inventory_management_system/Inventory/tasks/excel_export.py`

```python
from celery import shared_task
from django.core.files.base import ContentFile
import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=2)
def export_inventory_report(self, filters=None, user_id=None):
    """
    Export inventory data to Excel asynchronously.
    filters: dict with keys like 'warehouse_id', 'category', 'low_stock'
    """
    from Inventory.models import InventoryItem, Warehouse
    from django.contrib.auth.models import User

    queryset = InventoryItem.objects.select_related('warehouse', 'category')

    if filters:
        if filters.get('warehouse_id'):
            queryset = queryset.filter(warehouse_id=filters['warehouse_id'])
        if filters.get('category'):
            queryset = queryset.filter(category__name=filters['category'])
        if filters.get('low_stock'):
            queryset = queryset.filter(quantity__lte=models.F('low_quantity_threshold'))

    # Convert to DataFrame
    data = list(queryset.values(
        'name', 'code', 'category__name', 'warehouse__name',
        'quantity', 'unit__name', 'last_updated'
    ))

    df = pd.DataFrame(data)
    df.columns = ['Name', 'Code', 'Category', 'Warehouse', 'Quantity', 'Unit', 'Last Updated']

    # Write to Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Inventory', index=False)

    filename = f"exports/inventory_report_{self.request.id}.xlsx"
    from django.core.files.storage import default_storage
    default_storage.save(filename, ContentFile(output.getvalue()))

    # Notify user
    if user_id:
        from Inventory.tasks.notifications import notify_user
        notify_user.delay(
            user_id=user_id,
            title="Export Ready",
            message=f"Your inventory report is ready: {filename}",
            link=default_storage.url(filename)
        )

    return {
        'status': 'success',
        'download_url': default_storage.url(filename),
        'row_count': len(data),
    }
```

#### `IMS/Inventory_management_system/Inventory/tasks/notifications.py`

```python
from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task
def notify_user(user_id, title, message, link=None):
    """
    Create in-app notification for a user.
    Can be extended to send email/push later.
    """
    from Inventory.models import Notification
    from django.contrib.auth.models import User

    try:
        user = User.objects.get(id=user_id)
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            link=link or '',
            is_read=False,
        )
        logger.info(f"Notification sent to user {user_id}: {title}")
    except User.DoesNotExist:
        logger.warning(f"Cannot notify: user {user_id} not found")


@shared_task
def send_bulk_notification(user_ids, title, message):
    """Send notification to multiple users."""
    for user_id in user_ids:
        notify_user.delay(user_id, title, message)
```

#### `IMS/Inventory_management_system/Inventory/tasks/maintenance.py`

```python
from celery import shared_task
from django_celery_results.models import TaskResult
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

@shared_task
def cleanup_task_results(days=7):
    """Remove old Celery task results to prevent DB bloat."""
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = TaskResult.objects.filter(date_done__lt=cutoff).delete()
    logger.info(f"Cleaned up {deleted} old task results")
    return {'deleted': deleted}


@shared_task
def cleanup_expired_media(days=30):
    """Remove temporary export files older than N days."""
    from django.core.files.storage import default_storage
    from django.conf import settings
    import os

    # Implement based on your storage backend
    # For Azure: list blobs with prefix 'exports/' and delete old ones
    logger.info("Media cleanup task placeholder — implement per storage backend")
```

### 5.4 Update Views to Use Async Tasks

Example: Update release letter download view

```python
# In views/release_document_views.py (or wherever the current view lives)
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from Inventory.tasks.pdf_generation import generate_release_letter_pdf

@require_POST
@login_required
def async_generate_release_letter(request, letter_id):
    """
    Queue PDF generation and return task ID for polling.
    Frontend polls /api/tasks/<task_id>/status/ until complete.
    """
    task = generate_release_letter_pdf.delay(
        release_letter_id=letter_id,
        user_id=request.user.id,
    )
    return JsonResponse({
        'status': 'queued',
        'task_id': task.id,
        'poll_url': f'/api/tasks/{task.id}/status/',
    })


# Add to urls.py
# path('api/release-letter/<int:letter_id>/generate/', async_generate_release_letter, name='async_generate_rl'),
# path('api/tasks/<str:task_id>/status/', task_status, name='task_status'),
```

Add task status endpoint:

```python
# In a new file: views/task_views.py
from django.http import JsonResponse
from celery.result import AsyncResult

def task_status(request, task_id):
    result = AsyncResult(task_id)
    response = {
        'task_id': task_id,
        'status': result.status,
        'ready': result.ready(),
    }
    if result.ready():
        if result.successful():
            response['result'] = result.result
        else:
            response['error'] = str(result.result)
    return JsonResponse(response)
```

### 5.5 Deploy Celery Workers on Azure

**Option A: Separate App Service (Recommended)**

Create a second App Service Plan (cheaper, no HTTP needed):

```bash
# Create Worker App Service
az webapp create \
  --resource-group $RESOURCE_GROUP \
  --plan moen-ims-worker-plan \
  --name moen-ims-worker \
  --runtime "PYTHON:3.11"

# Set startup command to run Celery instead of Gunicorn
az webapp config set \
  --resource-group $RESOURCE_GROUP \
  --name moen-ims-worker \
  --startup-file "celery -A Inventory_management_system worker -l info --concurrency=2"
```

**Option B: Container Instance (Simpler)**

```bash
az container create \
  --resource-group $RESOURCE_GROUP \
  --name moen-ims-celery \
  --image moenims.azurecr.io/moen-ims:latest \
  --command-line "celery -A Inventory_management_system worker -l info" \
  --environment-variables REDIS_URL=$REDIS_URL DATABASE_URL=$DATABASE_URL \
  --cpu 1 --memory 2
```

**Option C: Run on same App Service (Quick, not ideal)**

Use a custom startup script:

```bash
# startup.sh
#!/bin/bash
gunicorn Inventory_management_system.wsgi:application --bind 0.0.0.0:8000 &
celery -A Inventory_management_system worker -l info --concurrency=1 &
wait
```

> **Warning:** Option C shares CPU/memory with web requests. Use only for testing.

### 5.6 Frontend Polling Pattern

Add to your base template or a shared JS file:

```javascript
// static/js/task_polling.js
function pollTaskStatus(taskId, pollUrl, onComplete, onError) {
    const poll = () => {
        fetch(pollUrl)
            .then(r => r.json())
            .then(data => {
                if (data.ready) {
                    if (data.status === 'SUCCESS') {
                        onComplete(data.result);
                    } else {
                        onError(data.error || 'Task failed');
                    }
                } else {
                    setTimeout(poll, 2000);  // Poll every 2 seconds
                }
            })
            .catch(err => onError(err));
    };
    poll();
}

// Usage:
// pollTaskStatus(taskId, pollUrl,
//     result => window.location.href = result.download_url,
//     error => alert('Error: ' + error)
// );
```

---

## 6. Phase 5: Query Optimization (Week 5)

### 6.1 Install Django Debug Toolbar (Dev Only)

```python
# settings.py — add only in DEBUG
if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
    INTERNAL_IPS = ['127.0.0.1']
```

### 6.2 Audit Heavy Views

Run these queries in Django shell to find N+1 problems:

```python
from django.db import connection, reset_queries
from Inventory.models import ReleaseLetter

reset_queries()
letters = ReleaseLetter.objects.all()[:50]
for letter in letters:
    print(letter.uploaded_by.username)  # N+1 if not select_related
print(f"Queries: {len(connection.queries)}")  # Should be ~2, not 51
```

### 6.3 Add `select_related` / `prefetch_related`

Common patterns in your app:

```python
# Release letter list view
ReleaseLetter.objects.select_related(
    'uploaded_by', 'material_order', 'project'
).prefetch_related(
    'site_receipts', 'audits'
)

# Inventory dashboard
InventoryItem.objects.select_related(
    'category', 'unit', 'warehouse', 'supplier'
).prefetch_related(
    'orders', 'release_letters'
)

# Project with BoQ
Project.objects.select_related('project_type').prefetch_related(
    'phases', 'bill_of_quantities__items'
)
```

### 6.4 Add Missing Database Indexes

Review your models for fields used in `.filter()`, `.order_by()`, or `.exclude()`:

```python
# In models/orders.py — add indexes to heavily queried fields
class ReleaseLetter(auto_prefetch.Model):
    class Meta:
        indexes = [
            models.Index(fields=['request_code', 'status']),
            models.Index(fields=['upload_time']),
            models.Index(fields=['project', 'material_type']),
        ]

class MaterialOrder(auto_prefetch.Model):
    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['project', 'status']),
        ]
```

Generate and run migrations:

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6.5 Add Database Views for Reports

For complex dashboard queries, create a PostgreSQL materialized view:

```sql
-- Run in psql or Django RunSQL migration
CREATE MATERIALIZED VIEW inventory_dashboard_summary AS
SELECT 
    w.id as warehouse_id,
    w.name as warehouse_name,
    c.name as category_name,
    COUNT(i.id) as item_count,
    SUM(i.quantity) as total_quantity,
    COUNT(CASE WHEN i.quantity <= i.low_quantity_threshold THEN 1 END) as low_stock_count
FROM inventory_warehouse w
LEFT JOIN inventory_inventoryitem i ON i.warehouse_id = w.id
LEFT JOIN inventory_category c ON c.id = i.category_id
GROUP BY w.id, w.name, c.name;

CREATE UNIQUE INDEX idx_dashboard_summary ON inventory_dashboard_summary(warehouse_id, category_name);

-- Refresh every 5 minutes (or via Celery beat)
REFRESH MATERIALIZED VIEW CONCURRENTLY inventory_dashboard_summary;
```

---

## 7. Phase 6: CDN & Static Assets (Week 5–6)

### 7.1 Azure CDN Profile

```bash
az cdn profile create \
  --resource-group $RESOURCE_GROUP \
  --name moen-ims-cdn \
  --sku Standard_Microsoft

az cdn endpoint create \
  --resource-group $RESOURCE_GROUP \
  --profile-name moen-ims-cdn \
  --name moen-ims-static \
  --origin moenimsmedia.blob.core.windows.net \
  --origin-path "/static"
```

### 7.2 Update `settings.py`

```python
# Production: serve static via CDN
if not DEBUG and os.environ.get('CDN_DOMAIN'):
    STATIC_URL = f"https://{os.environ['CDN_DOMAIN']}/static/"
    # WhiteNoise still handles collectstatic and compression
```

### 7.3 Collect Static on Deploy

Ensure your deployment pipeline runs:

```bash
python manage.py collectstatic --noinput
```

Azure App Service Kudu should do this automatically if configured.

---

## 8. Phase 7: Monitoring & Alerting (Ongoing)

### 8.1 Azure Application Insights

```bash
az extension add -n application-insights
az monitor app-insights component create \
  --resource-group $RESOURCE_GROUP \
  --app moen-ims-insights \
  --location $LOCATION
```

Add to `settings.py`:

```python
# Application Insights (optional, requires opencensus-ext-django)
APPINSIGHTS_CONNECTION_STRING = os.environ.get('APPINSIGHTS_CONNECTION_STRING', '')
if APPINSIGHTS_CONNECTION_STRING:
    try:
        from opencensus.ext.django.middleware import OpenCensusMiddleware
        MIDDLEWARE.insert(0, 'opencensus.ext.django.middleware.OpenCensusMiddleware')
        OPENCENSUS = {
            'TRACE': {
                'SAMPLER': 'opencensus.trace.samplers.ProbabilitySampler(rate=0.1)',
                'EXPORTER': f'opencensus.ext.azure.trace_exporter.AzureExporter(connection_string="{APPINSIGHTS_CONNECTION_STRING}")',
            }
        }
    except ImportError:
        pass
```

### 8.2 Sentry (Already Configured)

Your `settings.py` already has Sentry. Ensure `SENTRY_DSN` is set in production.

### 8.3 Custom Health Check Endpoint

Add to `urls.py`:

```python
path('health/', include('health_check.urls')),
```

Install `django-health-check`:

```bash
pip install django-health-check
```

Add to `INSTALLED_APPS`:

```python
'health_check',
'health_check.db',
'health_check.cache',
'health_check.storage',
```

### 8.4 Azure Alerts

Set up alerts for:

| Metric | Threshold | Action |
|--------|-----------|--------|
| App Service — HTTP 5xx | >5 in 5 min | Email + SMS |
| PostgreSQL — CPU | >80% for 10 min | Scale up SKU |
| PostgreSQL — Storage | >85% | Email |
| Redis — Memory | >80% | Eviction policy check |
| Celery — Queue depth | >100 tasks | Add worker instance |

---

## 9. Rollback Procedures

### 9.1 Database Rollback

If PostgreSQL fails, revert to SQLite **temporarily**:

```bash
# Azure App Service Configuration
ALLOW_SQLITE_IN_PROD=1
# Unset DATABASE_URL
```

> **Warning:** This loses concurrent write safety. Use only for emergency recovery.

### 9.2 Media Rollback

If Azure Blob Storage fails, local files are still in `/home/site/data/media/` (until you clean them). Switch back:

```python
# settings.py — comment out Azure storage
# DEFAULT_FILE_STORAGE = 'storages.backends.azure_storage.AzureStorage'
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
```

### 9.3 Celery Rollback

If workers fail, tasks fall back to synchronous execution:

```python
# In views, add fallback:
from django.conf import settings

if not settings.CELERY_BROKER_URL:
    # Run synchronously
    result = generate_release_letter_pdf(release_letter_id, user_id)
else:
    task = generate_release_letter_pdf.delay(release_letter_id, user_id)
```

---

## Appendix A: Azure Resource Provisioning

### Complete Resource Script

Save as `provision-azure.sh`:

```bash
#!/bin/bash
set -e

RESOURCE_GROUP="moen-ims-prod"
LOCATION="uksouth"
APP_NAME="moen-ims-app"
DB_NAME="moen-ims-db-$(date +%s)"
REDIS_NAME="moen-ims-redis"
STORAGE_NAME="moenimsmedia$(date +%s | tail -c 5)"

echo "=== Creating Resource Group ==="
az group create --name $RESOURCE_GROUP --location $LOCATION

echo "=== Creating PostgreSQL ==="
DB_PASS=$(openssl rand -base64 24)
az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $DB_NAME \
  --location $LOCATION \
  --admin-user moenadmin \
  --admin-password "$DB_PASS" \
  --sku-name Standard_B2s \
  --tier Burstable \
  --storage-size 32 \
  --version 15 \
  --public-access 0.0.0.0 \
  --database-name moenims \
  --yes

echo "=== Creating Redis ==="
az redis create \
  --resource-group $RESOURCE_GROUP \
  --name $REDIS_NAME \
  --location $LOCATION \
  --sku Basic \
  --vm-size c0

REDIS_KEY=$(az redis list-keys --resource-group $RESOURCE_GROUP --name $REDIS_NAME --query primaryKey -o tsv)

echo "=== Creating Storage Account ==="
az storage account create \
  --name $STORAGE_NAME \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS \
  --kind StorageV2

STORAGE_CONN=$(az storage account show-connection-string --name $STORAGE_NAME --resource-group $RESOURCE_GROUP --query connectionString -o tsv)

echo "=== Creating Container ==="
az storage container create --name media --account-name $STORAGE_NAME --auth-mode login

echo ""
echo "=== CONFIGURATION VALUES ==="
echo "DATABASE_URL=postgres://moenadmin:${DB_PASS}@${DB_NAME}.postgres.database.azure.com:5432/moenims?sslmode=require"
echo "REDIS_URL=rediss://:${REDIS_KEY}@${REDIS_NAME}.redis.cache.windows.net:6380/0"
echo "AZURE_STORAGE_CONNECTION_STRING=${STORAGE_CONN}"
echo ""
echo "Add these to your Azure App Service Configuration."
```

---

## Appendix B: Environment Variable Reference

### Required in Production

| Variable | Example | Phase |
|----------|---------|-------|
| `DATABASE_URL` | `postgres://...` | 1 |
| `REDIS_URL` | `rediss://...` | 2 |
| `AZURE_STORAGE_CONNECTION_STRING` | `DefaultEndpointsProtocol=...` | 3 |
| `DJANGO_SECRET_KEY` | `django-insecure-...` | Existing |
| `TOKEN_ENCRYPTION_KEY` | `Fernet key` | Existing |
| `SENTRY_DSN` | `https://...` | Existing |
| `MS_CLIENT_ID` | `...` | Existing |
| `MS_CLIENT_SECRET` | `...` | Existing |
| `MS_TENANT_ID` | `...` | Existing |

### Optional

| Variable | Default | Purpose |
|----------|---------|---------|
| `DB_CONN_MAX_AGE` | `60` | Persistent DB connections |
| `DB_SSL_REQUIRE` | `True` | Force TLS to DB |
| `AXES_FAILURE_LIMIT` | `5` | Login attempts before lockout |
| `AXES_COOLOFF_HOURS` | `1` | Lockout duration |
| `CDN_DOMAIN` | *(none)* | Static asset CDN domain |
| `APPINSIGHTS_CONNECTION_STRING` | *(none)* | Azure monitoring |
| `CELERY_WORKER_CONCURRENCY` | `2` | Tasks per worker |

---

## Appendix C: Updated `requirements.txt` (Final)

```
django-crispy-forms>=2.0
crispy-bootstrap5>=0.7
gunicorn>=23.0.0
whitenoise>=6.0.0
Pillow>=9.0.0
pandas>=2.0.0
openpyxl>=3.0.0
plotly>=5.18.0
seaborn>=0.13.0
reportlab>=4.0.0
matplotlib>=3.9.0
dj-database-url>=1.0.0,<2.0.0
psycopg2-binary>=2.9.9
python-dotenv>=1.0.0
django-auto-prefetch>=1.14.0
qrcode[pil]>=7.4.2
PyMuPDF>=1.24.0
opencv-python-headless>=4.8.0
django-otp>=1.3.0
pyotp>=2.9.0
Django==5.1.5
msal>=1.31.0
requests>=2.32.3
cryptography>=44.0.0

# --- Scaling: Storage ---
django-storages[azure]>=1.14.0
azure-identity>=1.15.0

# --- Scaling: Background Tasks ---
celery[redis]>=5.3.0
django-celery-results>=2.5.0
django-celery-beat>=2.5.0
redis>=5.0.0
hiredis>=2.2.0

# --- Scaling: Monitoring ---
django-health-check>=3.18.0
sentry-sdk>=1.40.0

# --- Dev Only ---
django-debug-toolbar>=4.3.0
```

---

## Next Steps

1. **Review this plan** with your team and identify any domain-specific constraints
2. **Set up a staging environment** that mirrors production
3. **Run Phase 1 (Database)** on staging first — this is the riskiest step
4. **Schedule a maintenance window** for production database migration (30–60 min downtime expected)
5. **Implement Celery tasks** one at a time — start with PDF generation (highest user impact)

**Questions or need help with a specific phase?** Each section can be expanded into a detailed implementation guide with exact file changes.
