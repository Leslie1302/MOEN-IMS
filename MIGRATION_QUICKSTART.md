# Digital Signature Stamp - Quick Migration Guide

## ⚠️ IMPORTANT: Read Before Proceeding

This guide provides quick steps to apply the digital signature stamp migrations. For detailed information, see `DIGITAL_SIGNATURE_STAMP_README.md`.

---

## Pre-Migration Checklist

- [ ] **Backup your database** (CRITICAL!)
- [ ] Test on a copy of your database first
- [ ] Ensure you're on a clean commit (no pending changes)
- [ ] Review the changes in the migration files

---

## Quick Migration Steps

### 1. Backup Your Database

```bash
# For PostgreSQL
pg_dump -U username -d database_name > backup_$(date +%Y%m%d_%H%M%S).sql

# For SQLite
cp db.sqlite3 db.sqlite3.backup_$(date +%Y%m%d_%H%M%S)
```

### 2. Navigate to Project Directory

```bash
cd IMS/Inventory_management_system
```

### 3. Check Current Migration Status

```bash
python manage.py showmigrations Inventory
```

You should see:
```
[ ] 0014_add_signature_stamp_to_profile
[ ] 0015_backfill_signature_stamps
```

### 4. Apply Schema Migration

```bash
python manage.py migrate Inventory 0014_add_signature_stamp_to_profile
```

**Expected:** `OK` message

### 5. Apply Data Migration

```bash
python manage.py migrate Inventory 0015_backfill_signature_stamps
```

**Expected:** Summary showing stamps created

### 6. Verify Success

```bash
python manage.py shell
```

```python
from Inventory.models import Profile

# Check stamps were created
count = Profile.objects.filter(signature_stamp__isnull=False).count()
print(f"✓ {count} profiles have signature stamps")

# View a sample
profile = Profile.objects.filter(user__isnull=False).first()
if profile:
    print(f"✓ Sample: {profile.signature_stamp}")
    
exit()
```

---

## What Was Changed

### Files Modified:
1. `Inventory/models.py` - Added `signature_stamp` field and utility methods to Profile model
2. `Inventory/signals.py` - Added signal handlers for automatic stamp generation

### Files Created:
1. `Inventory/migrations/0014_add_signature_stamp_to_profile.py` - Schema migration
2. `Inventory/migrations/0015_backfill_signature_stamps.py` - Data migration
3. `DIGITAL_SIGNATURE_STAMP_README.md` - Comprehensive documentation
4. `MIGRATION_QUICKSTART.md` - This file

---

## Rollback (If Needed)

If something goes wrong:

```bash
# Rollback data migration only
python manage.py migrate Inventory 0014_add_signature_stamp_to_profile

# Rollback everything (WARNING: Deletes stamp data)
python manage.py migrate Inventory 0013_add_consignment_number
```

Then restore from backup:

```bash
# PostgreSQL
psql -U username -d database_name < backup_file.sql

# SQLite
cp db.sqlite3.backup db.sqlite3
```

---

## Testing the System

### Test 1: Create a New User

```python
from django.contrib.auth.models import User
from Inventory.models import Profile

# Create user
user = User.objects.create_user('testuser', 'test@example.com', 'testpass123')

# Check profile was created with stamp
profile = Profile.objects.get(user=user)
print(f"✓ Profile created: {profile}")
print(f"✓ Stamp: {profile.signature_stamp}")

# Cleanup
user.delete()
```

### Test 2: Parse a Stamp

```python
from Inventory.models import Profile

profile = Profile.objects.filter(user__isnull=False).first()
stamp_data = profile.display_signature_stamp()

print(f"✓ User: {stamp_data['SIGNED_BY']}")
print(f"✓ Time: {stamp_data['TIMESTAMP']}")
print(f"✓ ID: {stamp_data['ID']}")
```

### Test 3: Get or Create Stamp

```python
from Inventory.models import Profile

profile = Profile.objects.filter(user__isnull=False).first()
stamp = profile.get_or_create_signature_stamp()
print(f"✓ Stamp retrieved: {stamp}")
```

---

## Common Issues & Quick Fixes

### Issue: "Profile has no user" warnings during migration

**Fix:** This is expected for orphaned profiles. They'll be skipped safely.

### Issue: Stamps not generated for new users

**Fix:** Restart Django server to reload signals:
```bash
# Stop server (Ctrl+C)
python manage.py runserver
```

### Issue: Need to regenerate a stamp

**Fix:**
```python
from Inventory.models import Profile

profile = Profile.objects.get(user__username='username')
new_stamp = profile.regenerate_signature_stamp(force=True)
print(f"✓ New stamp: {new_stamp}")
```

---

## Next Steps

After successful migration:

1. ✓ Verify all existing users have stamps
2. ✓ Test creating new users
3. ✓ Update any views/templates that should display stamps
4. ✓ Add stamps to audit trails where needed
5. ✓ Review the full documentation in `DIGITAL_SIGNATURE_STAMP_README.md`

---

## Usage Examples

### In Views

```python
@login_required
def my_view(request):
    profile = Profile.objects.get(user=request.user)
    stamp = profile.get_or_create_signature_stamp()
    
    context = {'signature': stamp}
    return render(request, 'template.html', context)
```

### In Templates

```django
<p>Signed by: {{ user.profile.signature_stamp }}</p>
```

### For Audit Trails

```python
order.notes += f"\nProcessed by: {request.user.profile.signature_stamp}"
order.save()
```

---

## Support

- **Full Documentation:** `DIGITAL_SIGNATURE_STAMP_README.md`
- **Troubleshooting:** See README troubleshooting section
- **Logs:** Check `logs/django.log` for detailed information

---

**Last Updated:** November 6, 2024  
**Version:** 1.0.0
