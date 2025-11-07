

# Weekly Development Report Generator - Complete Setup Guide

## Overview

An automated weekly development report generator that intelligently parses project documentation, git commits, and code changes to create comprehensive professional reports sent via email.

---

## 🎯 Features

### **Intelligent Documentation Parsing**
- ✅ Scans README files across the project
- ✅ Analyzes CHANGELOG and HISTORY files
- ✅ Parses git commit messages (last 7 days)
- ✅ Extracts docstrings from modified functions
- ✅ Detects new database migrations
- ✅ Finds TODO/FIXME comments

### **Comprehensive Report Sections**
- ✅ Executive Summary (auto-generated)
- ✅ New Features Implemented
- ✅ Bug Fixes and Issues Resolved
- ✅ Database Changes (migrations)
- ✅ Code Improvements and Refactoring
- ✅ Pending Tasks/Known Issues
- ✅ Next Week's Priorities

### **Professional Email Delivery**
- ✅ HTML and plain text versions
- ✅ Beautiful, responsive email template
- ✅ Configurable recipients and CC
- ✅ Custom notes support
- ✅ Automatic date range formatting

### **Admin Interface Integration**
- ✅ "Generate Report" button in Django admin
- ✅ Preview before sending (dry-run mode)
- ✅ View report history
- ✅ Resend failed reports
- ✅ Detailed statistics

### **CLI Support**
- ✅ Management command for automation
- ✅ Cron job compatible
- ✅ Flexible command-line options

---

## 📦 What Was Created

### **1. Models**
- `WeeklyReport` - Stores report history and content

### **2. Utilities**
- `report_parser.py` - Documentation and file parsing
- `report_generator.py` - Report composition and email sending

### **3. Management Command**
- `generate_weekly_report.py` - CLI interface

### **4. Admin Interface**
- `admin_weekly_report.py` - Admin integration
- `generate_weekly_report.html` - Report generation form

### **5. Email Templates**
- `weekly_report.html` - Beautiful HTML email
- `weekly_report.txt` - Plain text version

### **6. Documentation**
- This setup guide
- Inline code documentation
- Troubleshooting guide

---

## 🚀 Setup Instructions

### **Step 1: Run Migrations**

The WeeklyReport model needs to be added to your database:

```bash
cd IMS/Inventory_management_system
python manage.py makemigrations
python manage.py migrate
```

### **Step 2: Configure Email Settings**

Add to your `settings.py`:

```python
# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # Or your SMTP server
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'  # Use app password for Gmail
DEFAULT_FROM_EMAIL = 'MOEN IMS <your-email@gmail.com>'

# Weekly Report Recipients (default)
WEEKLY_REPORT_RECIPIENTS = [
    'supervisor@example.com',
    'manager@example.com',
]
```

**For Gmail:**
1. Enable 2-Factor Authentication
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the app password in `EMAIL_HOST_PASSWORD`

**For Other Providers:**
- **Outlook/Office365:** `smtp.office365.com`, port 587
- **Yahoo:** `smtp.mail.yahoo.com`, port 587
- **Custom SMTP:** Contact your email provider

### **Step 3: Verify Git is Installed**

The report generator uses git to analyze commits:

```bash
git --version
```

If not installed, download from: https://git-scm.com/downloads

### **Step 4: Test Email Configuration**

Test your email settings:

```bash
python manage.py shell
```

```python
from django.core.mail import send_mail

send_mail(
    'Test Email',
    'This is a test email from Django.',
    'your-email@gmail.com',
    ['recipient@example.com'],
    fail_silently=False,
)
```

If you receive the email, configuration is correct!

---

## 💻 Usage

### **Method 1: Django Admin (Recommended)**

1. **Access Admin:**
   ```
   http://localhost:8000/admin/
   ```

2. **Navigate to Weekly Reports:**
   - Click on "Weekly Reports" in the Inventory section
   - Click the "Generate Weekly Report" button

3. **Configure Report:**
   - Set number of days (default: 7)
   - Add custom notes (optional)
   - Configure recipients
   - Check "Dry Run" for preview

4. **Generate:**
   - Click "Generate Report"
   - Review the generated report
   - Uncheck "Dry Run" and regenerate to send

### **Method 2: Command Line**

```bash
# Dry run (preview only)
python manage.py generate_weekly_report --dry-run

# Generate and send
python manage.py generate_weekly_report

# Custom options
python manage.py generate_weekly_report \
    --days 7 \
    --recipients manager@example.com supervisor@example.com \
    --cc team@example.com \
    --notes "Special highlights this week..." \
    --user admin

# See all options
python manage.py generate_weekly_report --help
```

---

## 📧 Email Template Preview

### **HTML Email Includes:**
- Professional header with gradient
- Executive summary in highlighted box
- Color-coded sections:
  - 🟢 Green: New Features
  - 🔴 Red: Bug Fixes
  - 🟣 Purple: Database Changes
  - 🟠 Orange: Code Improvements
  - ⚫ Gray: Pending Tasks
  - 🔵 Teal: Next Priorities
- Statistics dashboard
- Custom notes section
- Report metadata

### **Plain Text Email:**
- Clean, formatted text
- All sections clearly separated
- Easy to read in any email client

---

## 🔄 Scheduling Automatic Reports

### **Option 1: Cron Job (Linux/Mac)**

Edit crontab:
```bash
crontab -e
```

Add this line (runs every Monday at 9 AM):
```cron
0 9 * * 1 cd /path/to/MOEN-IMS/IMS/Inventory_management_system && /path/to/python manage.py generate_weekly_report
```

### **Option 2: Task Scheduler (Windows)**

1. Open Task Scheduler
2. Create Basic Task
3. Trigger: Weekly, Monday, 9:00 AM
4. Action: Start a program
5. Program: `C:\path\to\python.exe`
6. Arguments: `manage.py generate_weekly_report`
7. Start in: `C:\path\to\MOEN-IMS\IMS\Inventory_management_system`

### **Option 3: Django-Cron (Cross-platform)**

Install:
```bash
pip install django-cron
```

Add to `INSTALLED_APPS`:
```python
INSTALLED_APPS = [
    ...
    'django_cron',
]
```

Create `Inventory/cron.py`:
```python
from django_cron import CronJobBase, Schedule
from .utils.report_generator import WeeklyReportGenerator

class WeeklyReportCronJob(CronJobBase):
    RUN_EVERY_MINS = 10080  # 7 days
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'Inventory.weekly_report'
    
    def do(self):
        generator = WeeklyReportGenerator()
        generator.generate_report()
```

Run:
```bash
python manage.py runcrons
```

---

## 📊 Report Sections Explained

### **1. Executive Summary**
Auto-generated overview including:
- Total commits
- Number of features/fixes
- Database migrations
- Code statistics (insertions/deletions)

### **2. New Features**
Lists commits with keywords: add, implement, create, new, feature

### **3. Bug Fixes**
Lists commits with keywords: fix, bug, issue, resolve, patch

### **4. Database Changes**
Lists all migration files created in the period

### **5. Code Improvements**
Lists commits with keywords: refactor, improve, optimize, clean, update

### **6. Pending Tasks**
Lists TODO/FIXME comments found in recently modified files

### **7. Next Priorities**
Extracted from README "Next Steps" or "Upcoming" sections

---

## 🎨 Customization

### **Modify Report Sections**

Edit `Inventory/utils/report_generator.py`:

```python
def _generate_features_section(self, feature_commits):
    # Customize how features are displayed
    features = []
    for commit in feature_commits:
        features.append(f"✨ {commit['message']}")
    return "\n".join(features)
```

### **Change Email Template**

Edit `Inventory/templates/Inventory/emails/weekly_report.html`:

```html
<!-- Customize colors, layout, sections -->
<div class="section">
    <h2>Your Custom Section</h2>
    <div class="content-box">{{ custom_content }}</div>
</div>
```

### **Add Custom Categorization**

Edit `report_parser.py`:

```python
def categorize_commits(self, commits):
    categories = {
        'features': [],
        'fixes': [],
        'security': [],  # Add new category
        # ...
    }
    
    security_keywords = ['security', 'vulnerability', 'CVE']
    
    for commit in commits:
        if any(kw in commit['message'].lower() for kw in security_keywords):
            categories['security'].append(commit)
```

### **Modify Default Recipients**

In `settings.py`:

```python
WEEKLY_REPORT_RECIPIENTS = [
    'primary@example.com',
    'secondary@example.com',
]

# Or use ADMINS
ADMINS = [
    ('Manager Name', 'manager@example.com'),
]
```

---

## 🔍 Admin Interface Features

### **Report List View**
- Report ID
- Date range
- Status badge (Draft/Sent/Failed)
- Generated by
- Number of recipients
- View report button

### **Report Detail View**
- Full report content
- HTML preview
- Plain text preview
- Statistics
- Error messages (if failed)
- Resend option

### **Generate Report Form**
- Days to include
- Custom notes
- Recipients configuration
- Dry run option
- Help documentation

### **Admin Actions**
- Resend failed reports
- View report history
- Filter by status/date

---

## 🐛 Troubleshooting

### **Issue: "SMTPAuthenticationError"**

**Cause:** Incorrect email credentials or 2FA not configured

**Solution:**
1. Verify `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD`
2. For Gmail, use App Password (not regular password)
3. Enable "Less secure app access" (not recommended) OR use App Password

### **Issue: "Git command not found"**

**Cause:** Git is not installed or not in PATH

**Solution:**
1. Install git: https://git-scm.com/downloads
2. Add git to system PATH
3. Restart terminal/IDE

### **Issue: "No commits found"**

**Cause:** No git commits in the last 7 days

**Solution:**
- This is normal if no development activity
- Report will show "No commits" in sections
- Try increasing days: `--days 14`

### **Issue: "Permission denied" when scanning files**

**Cause:** Insufficient file permissions

**Solution:**
1. Check file permissions
2. Run with appropriate user
3. Exclude problematic directories in parser

### **Issue: "Email not sending"**

**Cause:** Email configuration issues

**Solution:**
1. Test email settings (see Step 4 in Setup)
2. Check firewall/antivirus blocking SMTP
3. Verify SMTP server and port
4. Check email provider's SMTP documentation

### **Issue: "Report sections are empty"**

**Cause:** No matching documentation or commits

**Solution:**
- Ensure git repository is initialized
- Check commit messages use recognized keywords
- Add README files with proper sections
- Increase days parameter

---

## 📝 Example Report Output

```
================================================================================
                      WEEKLY DEVELOPMENT REPORT
================================================================================

Report Period: November 1 - November 7, 2024
Report ID: WR-20241107-A3F9

Statistics: 15 Commits | 23 Files Scanned | 2 Migrations

================================================================================
EXECUTIVE SUMMARY
================================================================================

This week saw 15 commits to the codebase. 5 new features implemented. 3 bug
fixes applied. 2 database migrations created. Code changes included 1,247
insertions and 523 deletions across 45 files.

================================================================================
NEW FEATURES IMPLEMENTED
================================================================================

• Add digital signature stamp system for user authentication (by Leslie)
• Implement visual signature stamps with admin integration (by Leslie)
• Create signature lookup and verification page (by Leslie)
• Add automated weekly development report generator (by Leslie)
• Implement email notification system for reports (by Leslie)

================================================================================
BUG FIXES AND ISSUES RESOLVED
================================================================================

• Fix NoneType error in signature stamp generation (by Leslie)
• Resolve email sending issues in report generator (by Leslie)
• Patch migration dependency conflicts (by Leslie)

================================================================================
DATABASE CHANGES
================================================================================

• 0014_add_signature_stamp_to_profile - Modified Nov 06, 2024
• 0016_weeklyreport - Modified Nov 07, 2024

... (continues with all sections)
```

---

## 🔒 Security Considerations

### **Email Credentials**
- ✅ Never commit `EMAIL_HOST_PASSWORD` to git
- ✅ Use environment variables:
  ```python
  import os
  EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_PASSWORD')
  ```
- ✅ Use `.env` file with `python-dotenv`

### **Recipient Validation**
- ✅ Validate email addresses before sending
- ✅ Limit recipients to prevent spam
- ✅ Log all sent reports

### **Access Control**
- ✅ Only staff users can generate reports
- ✅ Admin interface requires authentication
- ✅ CLI requires appropriate permissions

---

## 📈 Advanced Features

### **Add GitHub Integration**

```python
# In report_generator.py
import requests

def get_github_issues(self):
    """Fetch closed issues from GitHub"""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    params = {'state': 'closed', 'since': self.start_date.isoformat()}
    response = requests.get(url, params=params)
    return response.json()
```

### **Include Code Statistics**

```python
def get_code_stats(self):
    """Get detailed code statistics"""
    stats = {
        'python_files': len(list(self.project_root.rglob('*.py'))),
        'total_lines': 0,
        'test_files': len(list(self.project_root.rglob('test_*.py'))),
    }
    return stats
```

### **Attach Screenshots**

```python
from django.core.mail import EmailMessage

def _send_email_with_attachments(self, report):
    email = EmailMessage(...)
    
    # Attach screenshot
    screenshot_path = self.project_root / 'docs' / 'screenshot.png'
    if screenshot_path.exists():
        email.attach_file(str(screenshot_path))
    
    email.send()
```

---

## ✅ Testing Checklist

- [ ] Email configuration tested
- [ ] Git is installed and accessible
- [ ] Migrations applied successfully
- [ ] Dry run generates report
- [ ] Email sends successfully
- [ ] HTML email displays correctly
- [ ] Plain text email is readable
- [ ] Admin interface accessible
- [ ] Report history viewable
- [ ] CLI command works
- [ ] Scheduled job configured (optional)

---

## 📚 Additional Resources

- **Django Email Documentation:** https://docs.djangoproject.com/en/stable/topics/email/
- **Git Documentation:** https://git-scm.com/doc
- **Cron Tutorial:** https://crontab.guru/
- **SMTP Settings:** Check your email provider's documentation

---

## 🆘 Support

For issues or questions:
1. Check this documentation
2. Review troubleshooting section
3. Check Django logs: `logs/django.log`
4. Test email configuration
5. Verify git installation

---

**Created:** November 7, 2024  
**Version:** 1.0.0  
**Status:** ✅ Production Ready
