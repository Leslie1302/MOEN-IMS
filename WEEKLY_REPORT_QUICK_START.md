# Weekly Report Generator - Quick Start Guide

## 🚀 Quick Setup (5 Minutes)

### Step 1: Run Migrations
```bash
cd IMS/Inventory_management_system
python manage.py makemigrations
python manage.py migrate
```

### Step 2: Configure Email in settings.py
```python
# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'MOEN IMS <your-email@gmail.com>'

# Report Recipients
WEEKLY_REPORT_RECIPIENTS = ['supervisor@example.com']
```

### Step 3: Test It
```bash
# Dry run (no email sent)
python manage.py generate_weekly_report --dry-run
```

### Step 4: Use Admin Interface
1. Go to: `http://localhost:8000/admin/`
2. Click "Weekly Reports"
3. Click "Generate Weekly Report" button
4. Fill form and click "Generate Report"

---

## 📧 Gmail Setup (Most Common)

1. **Enable 2-Factor Authentication**
   - Go to: https://myaccount.google.com/security
   - Enable 2-Step Verification

2. **Create App Password**
   - Go to: https://myaccount.google.com/apppasswords
   - Select "Mail" and your device
   - Copy the 16-character password

3. **Update settings.py**
   ```python
   EMAIL_HOST_USER = 'your-email@gmail.com'
   EMAIL_HOST_PASSWORD = 'xxxx xxxx xxxx xxxx'  # App password
   ```

---

## 💻 Usage Options

### Option 1: Admin Interface (Easiest)
```
http://localhost:8000/admin/Inventory/weeklyreport/
Click "Generate Weekly Report" button
```

### Option 2: Command Line
```bash
# Preview only
python manage.py generate_weekly_report --dry-run

# Send email
python manage.py generate_weekly_report

# Custom recipients
python manage.py generate_weekly_report --recipients boss@example.com
```

### Option 3: Schedule Weekly (Cron)
```bash
# Edit crontab
crontab -e

# Add this line (runs every Monday at 9 AM)
0 9 * * 1 cd /path/to/project && python manage.py generate_weekly_report
```

---

## 📊 What Gets Included

The report automatically analyzes:
- ✅ Git commits (last 7 days)
- ✅ README and CHANGELOG files
- ✅ Database migrations
- ✅ TODO/FIXME comments
- ✅ Code statistics

Report sections:
- Executive Summary
- New Features
- Bug Fixes
- Database Changes
- Code Improvements
- Pending Tasks
- Next Week's Priorities

---

## 🐛 Quick Troubleshooting

### Email not sending?
```bash
# Test email configuration
python manage.py shell
>>> from django.core.mail import send_mail
>>> send_mail('Test', 'Body', 'from@example.com', ['to@example.com'])
```

### Git not found?
```bash
# Check git is installed
git --version

# If not, install from: https://git-scm.com/downloads
```

### No commits found?
- Normal if no development in last 7 days
- Try: `--days 14` for longer period

---

## 📝 Example Commands

```bash
# Dry run with custom notes
python manage.py generate_weekly_report --dry-run --notes "Great progress this week!"

# Send to multiple recipients
python manage.py generate_weekly_report --recipients boss@example.com manager@example.com

# Last 14 days
python manage.py generate_weekly_report --days 14

# With CC
python manage.py generate_weekly_report --cc team@example.com
```

---

## ✅ Checklist

- [ ] Migrations run successfully
- [ ] Email settings configured
- [ ] Test email sent successfully
- [ ] Dry run generates report
- [ ] Admin interface accessible
- [ ] Recipients configured

---

## 📚 Full Documentation

See **WEEKLY_REPORT_SETUP_GUIDE.md** for:
- Detailed setup instructions
- Email provider configurations
- Customization options
- Advanced features
- Complete troubleshooting guide

---

**Need Help?** Check the full setup guide or Django logs at `logs/django.log`
