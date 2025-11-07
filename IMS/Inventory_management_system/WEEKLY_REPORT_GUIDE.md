# Weekly Development Report - User Guide

## Overview

The Weekly Development Report system automatically generates comprehensive email reports about your project's development activity. It analyzes git commits, documentation, database migrations, and code comments to create professional reports.

## Accessing the Report Generator

### Via Django Admin Portal

1. **Log in to Django Admin**
   - Navigate to: `http://localhost:8000/admin/` (or your production URL)
   - Log in with your admin credentials

2. **Go to Weekly Reports**
   - In the admin sidebar, find **"Weekly Reports"** under the Inventory section
   - Click on it to view all generated reports

3. **Generate New Report**
   - Click the **"📊 Generate New Report"** button at the top right
   - This will take you to the report generation form

## Using the Report Generator

### Report Configuration

**Number of Days to Include:**
- Default: 7 days (one week)
- Range: 1-30 days
- Determines how far back to analyze git commits and changes

**Custom Notes (Optional):**
- Add any additional highlights or notes you want to include
- These appear in a special section of the report
- Useful for adding context that isn't captured by automated analysis

### Email Configuration

**Recipients:**
- Enter comma-separated email addresses
- Example: `manager@example.com, supervisor@example.com`
- Leave empty to use default recipients from settings

**CC Recipients (Optional):**
- Additional people to CC on the email
- Also comma-separated

### Options

**Dry Run (Preview Only):**
- ✅ **Checked (Recommended)**: Generate report without sending email
  - Use this to preview the report first
  - Report is saved in the database but not emailed
  - You can view it in the admin and send it later if needed

- ❌ **Unchecked**: Generate and immediately send email
  - Use this when you're ready to send the actual report
  - Email will be sent to all recipients

## What the Report Includes

The automated report analyzes and includes:

### 1. **Executive Summary**
- Overview of development activity
- Total commits, features, fixes, and migrations
- Code statistics (insertions, deletions, files changed)
- **ELI5 Version**: Simple, easy-to-understand explanation

### 2. **New Features Implemented**
- Lists all commits tagged as features
- Shows author and commit message
- Automatically detected from commit messages containing "feat:", "feature:", etc.
- **ELI5 Version**: Explains new features in simple terms
- **Screenshots**: Automatically includes recent feature screenshots

### 3. **Bug Fixes and Issues Resolved**
- Lists all bug fix commits
- Detected from messages containing "fix:", "bug:", "hotfix:", etc.
- **ELI5 Version**: Simple explanation of what was fixed

### 4. **Database Changes**
- Lists all Django migrations created during the period
- Shows migration names and dates
- **ELI5 Version**: Explains database changes in simple terms

### 5. **Code Improvements and Refactoring**
- Code refactoring commits
- Documentation updates
- Detected from "refactor:", "docs:", "style:", etc.
- **ELI5 Version**: Simple explanation of code improvements

### 6. **Pending Tasks and Known Issues**
- Scans code for TODO and FIXME comments
- Shows file locations
- Limited to 10 most recent items
- **ELI5 Version**: Simple explanation of what's left to do

### 7. **Next Week's Priorities**
- Extracted from README and CHANGELOG files
- Looks for "Next Steps", "Upcoming", "TODO", "Roadmap" sections
- **ELI5 Version**: Simple explanation of next priorities

### 8. **Custom Notes**
- Your manually added notes from the form

### 9. **PDF Attachment** 📄
- Professional PDF document attached to email
- Includes all report sections with ELI5 explanations
- Contains up to 5 screenshots
- Formatted with colors, tables, and proper styling

### 10. **ELI5 README File** 📚
- Automatically generates `WEEKLY_REPORT_ELI5.md` in project root
- Simple, non-technical explanations for all stakeholders
- Perfect for sharing with non-technical team members

## Command Line Usage

You can also generate reports from the command line:

### Basic Usage
```bash
# Generate report with dry run (preview only)
python manage.py generate_weekly_report --dry-run

# Generate and send report
python manage.py generate_weekly_report

# Specify number of days
python manage.py generate_weekly_report --days 14

# Specify recipients
python manage.py generate_weekly_report --recipients manager@example.com supervisor@example.com

# Add custom notes
python manage.py generate_weekly_report --notes "Important milestone reached this week"

# Specify user generating the report
python manage.py generate_weekly_report --user admin
```

### All Options
- `--days N`: Number of days to include (default: 7)
- `--dry-run`: Generate without sending email
- `--recipients email1 email2`: Space-separated recipient emails
- `--cc email1 email2`: Space-separated CC emails
- `--notes "text"`: Custom notes to include
- `--user username`: Username of person generating report

## Viewing Generated Reports

1. Go to **Admin → Weekly Reports**
2. You'll see a list of all generated reports with:
   - Report ID
   - Date range
   - Status (Draft, Sent, Failed)
   - Generated by
   - Generated at
   - Number of recipients

3. Click on any report to view:
   - Full report content
   - HTML and plain text previews
   - Statistics (commits analyzed, files scanned, etc.)
   - Error messages (if failed)

## Admin Actions

### Resend Failed Reports
1. Select one or more failed reports from the list
2. Choose **"Resend failed reports"** from the Actions dropdown
3. Click **"Go"**
4. The system will attempt to resend the emails

## Email Configuration

For the email system to work, ensure your `settings.py` has proper email configuration:

```python
# Email Settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # Your SMTP server
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@example.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'noreply@example.com'

# Weekly Report Recipients (optional)
WEEKLY_REPORT_RECIPIENTS = [
    'manager@example.com',
    'supervisor@example.com',
]
```

### Gmail Configuration
If using Gmail:
1. Enable 2-factor authentication
2. Generate an App Password
3. Use the App Password in `EMAIL_HOST_PASSWORD`

## Automating Reports (Cron Jobs)

To send reports automatically every week:

### Linux/Mac (Crontab)
```bash
# Edit crontab
crontab -e

# Add this line to send reports every Monday at 9 AM
0 9 * * 1 cd /path/to/project && /path/to/venv/bin/python manage.py generate_weekly_report
```

### Windows (Task Scheduler)
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: Weekly, Monday, 9:00 AM
4. Action: Start a program
5. Program: `C:\path\to\venv\Scripts\python.exe`
6. Arguments: `manage.py generate_weekly_report`
7. Start in: `C:\path\to\project`

## Troubleshooting

### Report Generation Fails
- Check that git is installed and accessible
- Ensure the project is a git repository
- Verify file permissions for reading project files

### Email Sending Fails
- Verify email settings in `settings.py`
- Check SMTP credentials
- Ensure firewall allows SMTP connections
- Check spam folder if emails aren't received

### No Commits Found
- Ensure git repository has commits in the specified date range
- Check that git is properly configured
- Verify the project root path is correct

### Missing Data in Report
- Commits must follow conventional commit format for categorization
- Example: `feat: Add new feature`, `fix: Resolve bug`
- Documentation files should have clear section headers

## Screenshot Management

The system automatically scans for screenshots in the following locations:
- `screenshots/`
- `docs/screenshots/`
- `docs/images/`
- `documentation/images/`
- `static/images/screenshots/`
- `media/screenshots/`
- `assets/screenshots/`

### Screenshot Naming Conventions

For better categorization, name your screenshots descriptively:
- **Features**: `feature_*.png`, `new_*.png`
- **Bug Fixes**: `bug_*.png`, `fix_*.png`, `error_*.png`
- **UI Changes**: `ui_*.png`, `interface_*.png`, `design_*.png`
- **Dashboard**: `dashboard_*.png`, `home_*.png`
- **Reports**: `report_*.png`, `chart_*.png`, `graph_*.png`

### Adding Screenshots

1. Save screenshots to one of the designated folders
2. Use descriptive filenames
3. Screenshots modified within the report period are automatically included
4. Up to 5 screenshots are included in the PDF attachment

## Best Practices

1. **Always do a dry run first** to preview the report
2. **Use conventional commit messages** for better categorization:
   - `feat:` or `feature:` for new features
   - `fix:` or `bug:` for bug fixes
   - `docs:` for documentation
   - `refactor:` for code improvements
   - `test:` for tests

3. **Keep README and CHANGELOG updated** with upcoming priorities
4. **Add meaningful TODO/FIXME comments** in code
5. **Review generated reports** before sending to stakeholders
6. **Schedule reports** to run automatically on a consistent day/time
7. **Save screenshots** in designated folders with descriptive names
8. **Share the ELI5 README** with non-technical stakeholders

## Support

For issues or questions:
- Check Django logs for error details
- Review the report's error message in the admin
- Ensure all dependencies are installed
- Verify git and email configurations
