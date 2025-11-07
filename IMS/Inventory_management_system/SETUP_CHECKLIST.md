# Setup Checklist for Weekly Report System

## ✅ Steps to Make Weekly Reports Appear in Admin

### 1. **Restart Django Development Server** (REQUIRED)

The admin interface is loaded when Django starts. You must restart the server to see new admin registrations.

**Stop the server:**
- Press `Ctrl+C` in the terminal running the server

**Start the server again:**
```bash
cd c:\Users\Leslie\Documents\GitHub\MOEN-IMS\IMS\Inventory_management_system
python manage.py runserver
```

### 2. **Verify Admin Access**

After restarting, navigate to:
```
http://localhost:8000/admin/
```

You should now see **"Weekly Reports"** in the admin sidebar under the **INVENTORY** section.

### 3. **Check for Migration Issues** (if still not visible)

Run migrations to ensure the WeeklyReport model is in the database:

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. **Verify Installation**

Check that all files are in place:

**Admin Files:**
- ✅ `Inventory/admin_weekly_report.py` - Admin configuration
- ✅ `Inventory/templates/admin/Inventory/weeklyreport_changelist.html` - List view template
- ✅ `Inventory/templates/admin/Inventory/generate_weekly_report.html` - Generation form

**Utility Files:**
- ✅ `Inventory/utils/report_generator.py` - Report generation logic
- ✅ `Inventory/utils/pdf_generator.py` - PDF creation
- ✅ `Inventory/utils/screenshot_scanner.py` - Screenshot scanning & ELI5

**Model:**
- ✅ `WeeklyReport` model exists in `Inventory/models.py` (line 1311)

**Import:**
- ✅ `admin.py` imports `WeeklyReportAdmin` (line 8)

## 🎯 What You Should See After Restart

### In Admin Sidebar:
```
INVENTORY
├── Bill of quantitys
├── Boq overissuance justifications
├── Categorys
├── Inventory items
├── Material orders
├── Notifications
├── Profiles
├── Suppliers
├── Units
├── Warehouses
└── Weekly reports  ← NEW!
```

### When You Click "Weekly Reports":
- List of all generated reports (may be empty initially)
- **"📊 Generate New Report"** button in top right
- Filters for status, date, etc.

### When You Click "Generate New Report":
- Form with configuration options
- Number of days
- Custom notes
- Email recipients
- Dry run checkbox

## 🐛 Troubleshooting

### Issue: "Weekly Reports" Not Showing in Admin

**Solution 1: Restart Server**
```bash
# Stop server (Ctrl+C)
# Start again
python manage.py runserver
```

**Solution 2: Check for Errors**
```bash
# Look for import errors
python manage.py check
```

**Solution 3: Clear Python Cache**
```bash
# Delete __pycache__ directories
python manage.py shell
>>> import sys
>>> sys.path
>>> exit()
```

**Solution 4: Verify Model Registration**
```bash
python manage.py shell
>>> from Inventory.models import WeeklyReport
>>> from Inventory.admin_weekly_report import WeeklyReportAdmin
>>> from django.contrib import admin
>>> admin.site.is_registered(WeeklyReport)
True  # Should return True
```

### Issue: Import Errors

**Check Dependencies:**
```bash
pip install reportlab Pillow
```

**Check for Syntax Errors:**
```bash
python manage.py check
```

### Issue: Template Not Found

**Verify Template Paths:**
```
Inventory/templates/admin/Inventory/
├── weeklyreport_changelist.html
└── generate_weekly_report.html
```

## 📝 Quick Test

After restarting, test the system:

1. **Navigate to Admin:**
   ```
   http://localhost:8000/admin/Inventory/weeklyreport/
   ```

2. **Click "Generate New Report"**

3. **Fill Form:**
   - Days: 7
   - Custom notes: "Test report"
   - Recipients: your-email@example.com
   - ✅ Check "Dry Run"

4. **Click "Generate Report"**

5. **Verify:**
   - Report appears in list
   - Status: Draft
   - Can view report details
   - PDF would be generated (but not sent in dry run)
   - `WEEKLY_REPORT_ELI5.md` created in project root

## 🎉 Success Indicators

You'll know it's working when:

- ✅ "Weekly Reports" appears in admin sidebar
- ✅ Can access `/admin/Inventory/weeklyreport/`
- ✅ "Generate New Report" button is visible
- ✅ Can fill out and submit the generation form
- ✅ Reports appear in the list after generation
- ✅ Can view report details
- ✅ ELI5 README file is created

## 🚀 Next Steps After Setup

1. **Configure Email Settings** in `settings.py`
2. **Add Screenshots** to `screenshots/` directory
3. **Test with Dry Run** first
4. **Generate Real Report** (uncheck dry run)
5. **Share ELI5 README** with stakeholders

## 📞 Still Having Issues?

If the admin still doesn't appear after restarting:

1. Check Django logs for errors
2. Verify Python version (3.8+)
3. Ensure all migrations are applied
4. Check file permissions
5. Try clearing browser cache
6. Check if another app is conflicting

---

**Most Common Issue:** Forgetting to restart the Django server!

**Quick Fix:** `Ctrl+C` then `python manage.py runserver`
