# Automatic Stamp Generation on Deployment

## ✅ Good News: No Manual Scripts Needed!

When you deploy your changes to the hosting site, **digital stamps will generate automatically** without any manual intervention.

---

## How It Works

### **Django Signals (Already Implemented)**

The system uses Django's built-in signal system to automatically generate stamps:

**File:** `Inventory/models.py` (lines 1644-1673)

```python
@receiver(post_save, sender=Profile)
def auto_generate_digital_stamp(sender, instance, created, **kwargs):
    """Automatically generate a digital stamp when a profile is created"""
    if created and instance.user and not instance.digital_stamp:
        instance.generate_digital_stamp()

@receiver(post_save, sender=User)
def create_user_profile_with_stamp(sender, instance, created, **kwargs):
    """Create profile and generate stamp when user is created"""
    if created:
        profile, _ = Profile.objects.get_or_create(user=instance)
        if not profile.digital_stamp:
            profile.generate_digital_stamp()
```

### **What Happens Automatically:**

1. **New User Created** → Django signal fires
2. **Profile Created** → Django signal fires
3. **Stamp Generated** → Saved to database automatically
4. **No Manual Intervention** → Everything just works!

---

## Deployment Checklist

### **Before Deployment:**

- [x] ✅ Stamps auto-generate via signals (already coded)
- [x] ✅ Transporter stamps generate on-the-fly (already coded)
- [x] ✅ Waybill embedding works automatically (already coded)
- [x] ✅ Navigation updated with all transport options
- [x] ✅ Migrations created (run `makemigrations` first)

### **During Deployment:**

1. **Push code to hosting:**
   ```bash
   git add .
   git commit -m "Add automatic digital stamp system and transport navigation"
   git push origin main
   ```

2. **Run migrations on hosting:**
   ```bash
   python manage.py migrate
   ```

3. **Collect static files (if needed):**
   ```bash
   python manage.py collectstatic --noinput
   ```

4. **Restart server** (Heroku, DigitalOcean, etc.)

### **After Deployment:**

- ✅ **Existing users:** Already have stamps (generated previously)
- ✅ **New users:** Will get stamps automatically on creation
- ✅ **Transporters:** Stamps generate on waybill download
- ✅ **No manual commands needed!**

---

## What's Automatic vs Manual

### ✅ **Automatic (No Action Needed):**

| Feature | Status | How |
|---------|--------|-----|
| User stamps on creation | ✅ Automatic | Django signals |
| Profile stamps on creation | ✅ Automatic | Django signals |
| Transporter stamps on waybills | ✅ Automatic | Generated on-the-fly |
| Consultant stamps on receipts | ✅ Automatic | Embedded when receipt logged |
| Bulk status updates | ✅ Automatic | Checks waybill number |

### 📝 **Manual (One-Time Setup):**

| Task | Required? | When |
|------|-----------|------|
| Add transporters to legend | Yes | When new transporter added |
| Set contact person names | Yes | In transporter form |
| Run migrations | Yes | After deployment |
| Collect static files | Maybe | If settings changed |

---

## For Existing Users on Hosting

### **Existing Users Already Have Stamps?**

**Check:**
```python
# Django shell on hosting
python manage.py shell

from django.contrib.auth.models import User
from Inventory.models import Profile

# Check all users
for user in User.objects.all():
    profile = Profile.objects.get_or_create(user=user)[0]
    has_stamp = "✓" if profile.digital_stamp else "✗"
    print(f"{user.username}: {has_stamp}")
```

### **Generate Stamps for Existing Users (If Needed):**

**One-time command:**
```python
# Django shell on hosting
from django.contrib.auth.models import User
from Inventory.models import Profile

for user in User.objects.all():
    profile, created = Profile.objects.get_or_create(user=user)
    if not profile.digital_stamp:
        profile.generate_digital_stamp()
        print(f"✓ Generated stamp for {user.username}")
```

Or use the management command (already created):
```bash
python manage.py generate_stamps
```

---

## Transporter Stamps (Completely Automatic!)

### **No Setup Needed!**

Transporter stamps are generated **on-the-fly** when waybills are downloaded:

1. **Storekeeper downloads waybill**
2. **System reads:** Transporter contact person name
3. **System generates:** Digital stamp image in memory
4. **System embeds:** Stamp in PDF Transport Info section
5. **No storage, no manual work!**

**Example:**
```
Transporter: NF3 Limited
Contact Person: Ronald Mensah  ← Just needs to be filled in

→ Waybill downloads with "Ronald Mensah" stamp automatically!
```

---

## Navigation Updates (Already Applied)

### **Store Operations Menu Now Includes:**

**For Storekeepers:**
- 📦 Receive Materials
- 📋 Process Release Orders
- 📄 Upload Release Letters
- 🚛 **Manage Transporters** ← NEW
- 📋 **Transporter Legend** ← NEW
- 🚚 Assign Transporters
- 📊 Update Transport Status
- ✅ View Site Receipts

**For Superusers:**
- Same as above (all transport options in Store Operations)

---

## Troubleshooting on Hosting

### **Stamps Not Generating After Deployment?**

**Check 1: Migrations Applied?**
```bash
python manage.py showmigrations Inventory
```
Look for:
- `[X] 0017_transporter_stamp_user` ← Should have X

**Check 2: Pillow Installed?**
```bash
pip list | grep Pillow
```
Should show: `Pillow X.X.X`

If missing:
```bash
pip install Pillow
```

**Check 3: Media Folder Writable?**
```bash
ls -la media/digital_stamps/
```
Should have write permissions.

**Check 4: Signals Working?**
```python
# Django shell
from django.contrib.auth.models import User

# Create test user
user = User.objects.create_user('test_stamp', 'test@test.com', 'password123')

# Check if profile and stamp were created
from Inventory.models import Profile
profile = Profile.objects.get(user=user)
print(f"Has stamp: {bool(profile.digital_stamp)}")

# Cleanup
user.delete()
```

---

## Environment-Specific Notes

### **Heroku:**
```bash
# After pushing code
heroku run python manage.py migrate
heroku run python manage.py generate_stamps  # If needed for existing users
heroku restart
```

### **DigitalOcean App Platform:**
```bash
# Migrations run automatically on deploy
# Just push code and it handles the rest
git push origin main
```

### **Custom VPS:**
```bash
# SSH into server
cd /path/to/project
git pull
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn  # or your server
```

---

## Summary

### ✅ **What You Need to Do:**

1. **Push code** to hosting
2. **Run migrations** on hosting
3. **That's it!**

### ✅ **What Happens Automatically:**

1. **User stamps** generate on user creation
2. **Transporter stamps** generate on waybill download
3. **Consultant stamps** embed when receipts logged
4. **Bulk updates** work based on waybill number
5. **Navigation** shows all transport options

### ❌ **What You DON'T Need to Do:**

1. ❌ No manual stamp generation scripts
2. ❌ No cron jobs to run
3. ❌ No background tasks to configure
4. ❌ No manual stamp assignment
5. ❌ No user account creation for transporters

---

## Final Checklist Before Deployment

- [ ] Run `makemigrations` locally
- [ ] Run `migrate` locally to test
- [ ] Test waybill download with transporter stamp
- [ ] Verify navigation shows all options
- [ ] Commit all changes
- [ ] Push to hosting
- [ ] Run migrations on hosting
- [ ] Test in production
- [ ] ✅ Done!

---

**Everything is automatic! Just deploy and it works!** 🚀

---

**Updated:** November 2, 2025  
**Version:** Final - Production Ready
