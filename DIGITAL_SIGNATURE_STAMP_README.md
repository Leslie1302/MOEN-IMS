# Digital Signature Stamp System

## Overview

This document describes the digital signature stamp system implemented for the MOEN Inventory Management System. The system automatically generates unique digital signature stamps for all users, which can be used for audit trails, document signing, and user verification.

## Table of Contents

1. [How It Works](#how-it-works)
2. [Architecture](#architecture)
3. [Migration Steps](#migration-steps)
4. [Usage Guide](#usage-guide)
5. [API Reference](#api-reference)
6. [Troubleshooting](#troubleshooting)
7. [Security Considerations](#security-considerations)

---

## How It Works

### Signature Stamp Format

Each signature stamp follows this format:
```
SIGNED_BY:{username}|TIMESTAMP:{iso_timestamp}|ID:{unique_id}
```

**Example:**
```
SIGNED_BY:john_doe|TIMESTAMP:2024-11-06T09:40:23.456789+00:00|ID:A1B2C3D4E5F6
```

### Components

1. **SIGNED_BY**: The username of the user
2. **TIMESTAMP**: ISO 8601 formatted timestamp of when the stamp was created
3. **ID**: A 12-character unique identifier generated using UUID4

### Automatic Generation

Signature stamps are automatically generated in two scenarios:

1. **New User Creation**: When a new user is created, a Profile is automatically created with a signature stamp
2. **Profile Creation**: When a Profile is created (manually or automatically), a signature stamp is generated if the profile has an associated user

### Safety Features

- **Null Checks**: The system validates that a user exists and has a username before generating a stamp
- **Error Handling**: All errors are logged but don't break the user creation process
- **Idempotent**: The system won't overwrite existing stamps unless explicitly requested
- **Database-Level Constraints**: The field allows null values during migration to prevent data loss

---

## Architecture

### Models

#### Profile Model (`Inventory/models.py`)

```python
class Profile(auto_prefetch.Model):
    user = auto_prefetch.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    signature_stamp = models.CharField(
        max_length=500, 
        blank=True, 
        null=True,
        help_text="Unique digital signature stamp for this user"
    )
```

#### Key Methods

- `generate_signature_stamp()`: Creates a new signature stamp
- `get_or_create_signature_stamp()`: Returns existing stamp or creates a new one
- `display_signature_stamp()`: Returns a parsed dictionary of stamp components
- `regenerate_signature_stamp(force=False)`: Regenerates the stamp (requires force=True to overwrite)

### Signals

#### User Profile Creation (`Inventory/signals.py`)

```python
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create a Profile for new users."""
```

#### Signature Stamp Generation (`Inventory/signals.py`)

```python
@receiver(post_save, sender=Profile)
def generate_signature_stamp_for_profile(sender, instance, created, **kwargs):
    """Automatically generate a digital signature stamp for new profiles."""
```

### Migrations

1. **0014_add_signature_stamp_to_profile.py**: Adds the `signature_stamp` field to the Profile model
2. **0015_backfill_signature_stamps.py**: Backfills signature stamps for all existing profiles

---

## Migration Steps

### Prerequisites

1. **Backup Your Database**: Always backup your database before running migrations
   ```bash
   # For PostgreSQL
   pg_dump -U username -d database_name > backup_$(date +%Y%m%d_%H%M%S).sql
   
   # For SQLite
   cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d_%H%M%S)
   ```

2. **Test on a Copy**: Run migrations on a copy of your database first
   ```bash
   # Copy production database to test environment
   # Run migrations on test environment
   # Verify everything works
   ```

### Step-by-Step Migration Process

#### Step 1: Review the Changes

```bash
cd IMS/Inventory_management_system
python manage.py showmigrations Inventory
```

You should see:
```
Inventory
  [X] 0001_initial
  [X] 0002_alter_billofquantity_group_alter_billofquantity_user_and_more
  ...
  [X] 0013_add_consignment_number
  [ ] 0014_add_signature_stamp_to_profile
  [ ] 0015_backfill_signature_stamps
```

#### Step 2: Run the Schema Migration

This adds the `signature_stamp` field to the database:

```bash
python manage.py migrate Inventory 0014_add_signature_stamp_to_profile
```

**Expected Output:**
```
Running migrations:
  Applying Inventory.0014_add_signature_stamp_to_profile... OK
```

**What This Does:**
- Adds a new `signature_stamp` column to the `Inventory_profile` table
- The column is nullable and allows blank values
- No data is modified at this stage

#### Step 3: Run the Data Migration

This backfills signature stamps for existing users:

```bash
python manage.py migrate Inventory 0015_backfill_signature_stamps
```

**Expected Output:**
```
Running migrations:
  Applying Inventory.0015_backfill_signature_stamps... 
  
Signature Stamp Backfill Complete:
  Created: 25
  Skipped: 3
  Errors: 0
  OK
```

**What This Does:**
- Iterates through all existing Profile records
- Generates signature stamps for profiles that:
  - Don't already have a stamp
  - Have an associated user
  - Have a user with a username
- Logs detailed information about the process
- Skips profiles without users or usernames (with warnings)

#### Step 4: Verify the Migration

Check that stamps were created:

```bash
python manage.py shell
```

```python
from Inventory.models import Profile

# Count profiles with stamps
profiles_with_stamps = Profile.objects.filter(signature_stamp__isnull=False).count()
print(f"Profiles with stamps: {profiles_with_stamps}")

# Check a specific profile
profile = Profile.objects.filter(user__isnull=False).first()
if profile:
    print(f"User: {profile.user.username}")
    print(f"Stamp: {profile.signature_stamp}")
    print(f"Parsed: {profile.display_signature_stamp()}")
```

#### Step 5: Monitor Logs

Check your application logs for any warnings or errors:

```bash
# Check Django logs
tail -f logs/django.log

# Look for signature stamp related messages
grep "signature stamp" logs/django.log
```

### Rolling Back (If Needed)

If you encounter issues, you can roll back the migrations:

```bash
# Roll back the data migration only
python manage.py migrate Inventory 0014_add_signature_stamp_to_profile

# Roll back both migrations
python manage.py migrate Inventory 0013_add_consignment_number
```

**Warning**: Rolling back the schema migration (0014) will delete the `signature_stamp` column and all stamp data.

---

## Usage Guide

### In Views

#### Accessing a User's Signature Stamp

```python
from django.contrib.auth.decorators import login_required
from Inventory.models import Profile

@login_required
def my_view(request):
    # Get or create the user's profile
    profile, created = Profile.objects.get_or_create(user=request.user)
    
    # Get the signature stamp (creates one if it doesn't exist)
    stamp = profile.get_or_create_signature_stamp()
    
    # Use the stamp
    context = {
        'signature_stamp': stamp,
        'stamp_details': profile.display_signature_stamp()
    }
    return render(request, 'my_template.html', context)
```

#### Adding Stamps to Audit Trails

```python
from Inventory.models import MaterialOrder, Profile

def process_material_order(request, order_id):
    order = MaterialOrder.objects.get(pk=order_id)
    profile = Profile.objects.get(user=request.user)
    
    # Get the signature stamp
    stamp = profile.get_or_create_signature_stamp()
    
    # Add to audit log or notes
    order.notes += f"\n\nProcessed by: {stamp}"
    order.processed_by = request.user
    order.save()
```

### In Templates

#### Displaying the Signature Stamp

```django
{% if user.profile.signature_stamp %}
    <div class="signature-stamp">
        <h4>Digital Signature</h4>
        <p class="stamp-text">{{ user.profile.signature_stamp }}</p>
    </div>
{% endif %}
```

#### Displaying Parsed Stamp Components

```django
{% with stamp_data=user.profile.display_signature_stamp %}
    {% if stamp_data %}
        <div class="signature-details">
            <p><strong>Signed By:</strong> {{ stamp_data.SIGNED_BY }}</p>
            <p><strong>Timestamp:</strong> {{ stamp_data.TIMESTAMP }}</p>
            <p><strong>ID:</strong> {{ stamp_data.ID }}</p>
        </div>
    {% endif %}
{% endwith %}
```

### In Django Admin

The signature stamp field is automatically available in the Django admin:

```python
# admin.py
from django.contrib import admin
from .models import Profile

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'signature_stamp']
    readonly_fields = ['signature_stamp']  # Make it read-only
    search_fields = ['user__username', 'signature_stamp']
```

### Programmatic Usage

#### Generate a New Stamp

```python
profile = Profile.objects.get(user=some_user)

# Generate a new stamp (only if one doesn't exist)
stamp = profile.get_or_create_signature_stamp()

# Force regenerate (overwrites existing stamp)
new_stamp = profile.regenerate_signature_stamp(force=True)
```

#### Parse an Existing Stamp

```python
profile = Profile.objects.get(user=some_user)
stamp_data = profile.display_signature_stamp()

if stamp_data:
    username = stamp_data.get('SIGNED_BY')
    timestamp = stamp_data.get('TIMESTAMP')
    unique_id = stamp_data.get('ID')
```

---

## API Reference

### Profile Model Methods

#### `generate_signature_stamp()`

Generates a new signature stamp for the user.

**Returns:** `str` - The generated signature stamp

**Raises:** 
- `ValueError` - If profile has no user or user has no username

**Example:**
```python
profile = Profile.objects.get(user=request.user)
try:
    stamp = profile.generate_signature_stamp()
    print(f"Generated: {stamp}")
except ValueError as e:
    print(f"Error: {e}")
```

---

#### `get_or_create_signature_stamp()`

Returns the existing signature stamp or creates a new one if it doesn't exist. Safe to call multiple times.

**Returns:** `str` or `None` - The signature stamp, or None if generation failed

**Example:**
```python
profile = Profile.objects.get(user=request.user)
stamp = profile.get_or_create_signature_stamp()
if stamp:
    print(f"Stamp: {stamp}")
else:
    print("Could not generate stamp")
```

---

#### `display_signature_stamp()`

Parses the signature stamp into its components.

**Returns:** `dict` or `None` - Dictionary with keys: SIGNED_BY, TIMESTAMP, ID

**Example:**
```python
profile = Profile.objects.get(user=request.user)
stamp_data = profile.display_signature_stamp()
if stamp_data:
    print(f"User: {stamp_data['SIGNED_BY']}")
    print(f"Time: {stamp_data['TIMESTAMP']}")
    print(f"ID: {stamp_data['ID']}")
```

---

#### `regenerate_signature_stamp(force=False)`

Regenerates the signature stamp. Use with caution.

**Parameters:**
- `force` (bool): If True, overwrites existing stamp. Default: False

**Returns:** `str` - The newly generated signature stamp

**Raises:**
- `ValueError` - If force=False and a stamp already exists

**Example:**
```python
profile = Profile.objects.get(user=request.user)

# This will raise ValueError if stamp exists
try:
    new_stamp = profile.regenerate_signature_stamp()
except ValueError:
    # Force regeneration
    new_stamp = profile.regenerate_signature_stamp(force=True)
```

---

## Troubleshooting

### Common Issues

#### Issue 1: "NoneType object has no attribute 'username'" Error

**Cause:** A Profile exists without an associated User, or the User has no username.

**Solution:**
```python
# Check for profiles without users
from Inventory.models import Profile

orphaned_profiles = Profile.objects.filter(user__isnull=True)
print(f"Found {orphaned_profiles.count()} profiles without users")

# Option 1: Delete orphaned profiles
orphaned_profiles.delete()

# Option 2: Assign users to profiles
for profile in orphaned_profiles:
    # Manually assign a user or handle appropriately
    pass
```

---

#### Issue 2: Migration Fails with "Profile has no user"

**Cause:** Some profiles in the database don't have associated users.

**Solution:** The data migration (0015) is designed to skip these profiles with a warning. Check the migration output:

```bash
python manage.py migrate Inventory 0015_backfill_signature_stamps --verbosity 2
```

Look for warnings like:
```
WARNING: Profile 123 has no associated user - skipping
```

These profiles will not get signature stamps until they're associated with a user.

---

#### Issue 3: Signature Stamps Not Generated for New Users

**Cause:** Signals might not be properly connected.

**Solution:**

1. Check that signals are imported in `apps.py`:
```python
# Inventory/apps.py
class InventoryConfig(AppConfig):
    def ready(self):
        import Inventory.signals  # This line is crucial
```

2. Verify signals are working:
```python
from django.contrib.auth.models import User
from Inventory.models import Profile

# Create a test user
user = User.objects.create_user('testuser', 'test@example.com', 'password')

# Check if profile was created
profile = Profile.objects.get(user=user)
print(f"Profile created: {profile}")
print(f"Stamp: {profile.signature_stamp}")

# Clean up
user.delete()
```

---

#### Issue 4: Want to Regenerate All Stamps

**Cause:** Need to regenerate stamps (e.g., format change, corruption).

**Solution:**

```python
from Inventory.models import Profile

# Regenerate all stamps
for profile in Profile.objects.filter(user__isnull=False):
    try:
        profile.regenerate_signature_stamp(force=True)
        print(f"Regenerated stamp for {profile.user.username}")
    except Exception as e:
        print(f"Error for profile {profile.pk}: {e}")
```

Or use Django management command:

```bash
python manage.py shell < regenerate_stamps.py
```

Where `regenerate_stamps.py` contains:
```python
from Inventory.models import Profile
count = 0
for profile in Profile.objects.filter(user__isnull=False):
    try:
        profile.regenerate_signature_stamp(force=True)
        count += 1
    except Exception as e:
        print(f"Error: {e}")
print(f"Regenerated {count} stamps")
```

---

#### Issue 5: Stamp Field Shows as Blank in Admin

**Cause:** Stamp wasn't generated or generation failed.

**Solution:**

1. Check if the profile has a user:
```python
from Inventory.models import Profile
profile = Profile.objects.get(pk=PROFILE_ID)
print(f"User: {profile.user}")
```

2. Manually generate the stamp:
```python
if profile.user:
    stamp = profile.get_or_create_signature_stamp()
    print(f"Generated: {stamp}")
```

3. Check logs for errors:
```bash
grep "signature stamp" logs/django.log
```

---

### Debugging Tips

#### Enable Verbose Logging

Add to your `settings.py`:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'logs/django.log',
        },
    },
    'loggers': {
        'Inventory.signals': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'Inventory.models': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
```

#### Check Signal Execution

```python
# In Django shell
from django.db.models.signals import post_save
from Inventory.models import Profile

# Check registered receivers
receivers = post_save._live_receivers(Profile)
print(f"Registered receivers for Profile: {len(receivers)}")
for receiver in receivers:
    print(f"  - {receiver}")
```

#### Verify Database State

```sql
-- Check profiles without stamps
SELECT COUNT(*) FROM Inventory_profile WHERE signature_stamp IS NULL;

-- Check profiles with stamps
SELECT COUNT(*) FROM Inventory_profile WHERE signature_stamp IS NOT NULL;

-- View sample stamps
SELECT user_id, signature_stamp FROM Inventory_profile LIMIT 10;
```

---

## Security Considerations

### Stamp Integrity

1. **Read-Only in Production**: Make the signature_stamp field read-only in forms and admin
2. **Audit Changes**: Log any modifications to signature stamps
3. **Validation**: Validate stamp format before accepting

```python
import re

def validate_signature_stamp(stamp):
    """Validate signature stamp format."""
    pattern = r'^SIGNED_BY:.+\|TIMESTAMP:.+\|ID:[A-F0-9]{12}$'
    return bool(re.match(pattern, stamp))
```

### Best Practices

1. **Don't Expose Raw Stamps**: Parse and display components separately in UI
2. **Log Stamp Usage**: Track when and where stamps are used
3. **Backup Stamps**: Include in database backups
4. **Version Control**: Keep migration files in version control

### Compliance

- **GDPR**: Signature stamps contain usernames (personal data). Include in data export/deletion requests
- **Audit Trails**: Stamps provide non-repudiation for user actions
- **Data Retention**: Consider retention policies for stamps

---

## Advanced Usage

### Custom Stamp Format

To customize the stamp format, modify the `generate_signature_stamp()` method:

```python
def generate_signature_stamp(self):
    """Custom format example."""
    timestamp = timezone.now().isoformat()
    unique_id = uuid.uuid4().hex[:12].upper()
    
    # Custom format with additional fields
    stamp = (
        f"USER:{self.user.username}|"
        f"EMAIL:{self.user.email}|"
        f"TIME:{timestamp}|"
        f"UUID:{unique_id}"
    )
    return stamp
```

### Integration with Document Signing

```python
from reportlab.pdfgen import canvas
from Inventory.models import Profile

def add_signature_to_pdf(pdf_path, user):
    """Add digital signature stamp to PDF."""
    profile = Profile.objects.get(user=user)
    stamp = profile.get_or_create_signature_stamp()
    
    # Add stamp to PDF
    c = canvas.Canvas(pdf_path)
    c.drawString(100, 100, f"Digitally Signed: {stamp}")
    c.save()
```

### Webhook Integration

```python
import requests
from django.db.models.signals import post_save
from django.dispatch import receiver
from Inventory.models import Profile

@receiver(post_save, sender=Profile)
def notify_stamp_creation(sender, instance, created, **kwargs):
    """Notify external system when stamp is created."""
    if created and instance.signature_stamp:
        requests.post('https://api.example.com/stamps', json={
            'user': instance.user.username,
            'stamp': instance.signature_stamp,
            'timestamp': timezone.now().isoformat()
        })
```

---

## Support

For issues or questions:

1. Check this documentation
2. Review the troubleshooting section
3. Check application logs
4. Contact the development team

---

## Changelog

### Version 1.0.0 (2024-11-06)

- Initial implementation of digital signature stamp system
- Added `signature_stamp` field to Profile model
- Implemented automatic stamp generation via signals
- Created schema migration (0014)
- Created data migration for backfilling (0015)
- Added comprehensive documentation

---

## License

This feature is part of the MOEN Inventory Management System.

---

**Last Updated:** November 6, 2024  
**Author:** Development Team  
**Version:** 1.0.0
