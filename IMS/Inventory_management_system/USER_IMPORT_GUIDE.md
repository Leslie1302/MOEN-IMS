# Excel User Import Guide

This guide explains how to use the Excel user import functionality to create multiple user accounts at once with automatically generated passwords.

## 🚀 Quick Start

1. **Access the Import Interface**
   - Log in as a superuser
   - Go to Django Admin → Users
   - Click "Import users from Excel" (or navigate to `/admin/auth/user/import-users/`)

2. **Prepare Your Excel File**
   - Use the required columns: `username`, `name`, `email`
   - Save as `.xlsx` or `.xls` format
   - Maximum 1000 users per import

3. **Import Users**
   - Upload your Excel file
   - Optionally select a default group
   - Click "Import Users"
   - **Save the generated passwords securely!**

## 📋 Excel File Requirements

### Required Columns

| Column | Description | Requirements |
|--------|-------------|--------------|
| `username` | Login username | • 3+ characters<br>• Must be unique<br>• No spaces or special characters |
| `name` | Full name | • Will be split into first/last name<br>• Cannot be empty |
| `email` | Email address | • Must be valid email format<br>• Must be unique across system |

### File Specifications

- **Format**: Excel (.xlsx or .xls)
- **Size Limit**: 10MB maximum
- **Row Limit**: 1000 users per import
- **Encoding**: UTF-8 recommended

### Sample Excel Format

```
username     | name          | email
-------------|---------------|----------------------
john.doe     | John Doe      | john.doe@company.com
jane.smith   | Jane Smith    | jane.smith@company.com
mike.wilson  | Mike Wilson   | mike.wilson@company.com
```

## 🔐 Password Generation

The system automatically generates secure passwords with these characteristics:

- **Length**: 12 characters
- **Composition**: 
  - Uppercase letters (A-Z)
  - Lowercase letters (a-z)
  - Numbers (0-9)
  - Special characters (!@#$%^&*)
- **Security**: Cryptographically secure random generation
- **Uniqueness**: Each password is unique

### Example Generated Passwords
```
K9m#Xp2vL$8w
Qr5@Nt9kF#3j
Bx7!Yz4mP&6s
```

## 🎯 Import Methods

### Method 1: Django Admin Interface (Recommended)

1. Navigate to `/admin/auth/user/import-users/`
2. Upload Excel file
3. Select optional default group
4. Click "Import Users"
5. Review results and save passwords

### Method 2: Management Command

```bash
# Basic import
python manage.py import_users_excel path/to/users.xlsx

# Import with default group assignment
python manage.py import_users_excel path/to/users.xlsx --group=default

# Generate detailed report
python manage.py import_users_excel path/to/users.xlsx --report-file=import_report.txt

# Dry run (validation only)
python manage.py import_users_excel path/to/users.xlsx --dry-run
```

### Method 3: Python API

```python
from Inventory.user_import import ExcelUserImporter

# Create importer
importer = ExcelUserImporter()

# Import users
results = importer.import_users_from_excel('users.xlsx', 'default_group')

# Generate report
report = importer.generate_import_report()
```

## 📊 Import Results

After import, you'll receive:

### Success Information
- Number of users created
- Username, email, and generated password for each user
- Group assignments (if applicable)

### Error Information
- Validation errors (duplicate usernames/emails)
- File format issues
- Data validation failures

### Detailed Report
- Complete import summary
- List of created users with passwords
- Error details and recommendations

## 🛡️ Security Considerations

### Password Management
- **Save passwords immediately** - they're only shown once
- Share passwords through secure channels (encrypted email, secure messaging)
- Encourage users to change passwords on first login
- Consider implementing password reset functionality

### Access Control
- Only superusers can import users
- All imports are logged in Django admin logs
- User creation is tracked with timestamps

### Data Validation
- Duplicate usernames/emails are rejected
- Email format validation
- Username length and character validation
- File size and row limits prevent abuse

## 🔧 Troubleshooting

### Common Issues

**"Missing required columns" Error**
```
Solution: Ensure your Excel file has exactly these column headers:
- username
- name  
- email
```

**"Username already exists" Error**
```
Solution: Check for duplicate usernames in:
- Your Excel file
- Existing users in the system
```

**"Invalid email format" Error**
```
Solution: Ensure all emails are valid:
✓ user@domain.com
✗ user@domain
✗ user.domain.com
```

**"File too large" Error**
```
Solution: 
- Split large files into smaller batches (max 1000 users)
- Compress images if included
- Remove unnecessary columns
```

### Validation Tips

1. **Test with small batches first** (5-10 users)
2. **Use the dry-run option** to validate before importing
3. **Check for duplicates** in your Excel file
4. **Verify email formats** before upload
5. **Remove empty rows** from Excel file

## 📁 File Templates

### Download Template
- Access: `/download-user-import-template/`
- Includes: Sample data, empty template, detailed instructions

### Manual Template Creation
```excel
Column A: username
Column B: name
Column C: email

Row 2: john.doe | John Doe | john.doe@company.com
Row 3: jane.smith | Jane Smith | jane.smith@company.com
```

## 🔄 Workflow Integration

### Typical Import Workflow

1. **Preparation**
   - Collect user information
   - Prepare Excel file with required columns
   - Validate data format

2. **Import**
   - Upload file through admin interface
   - Select appropriate default group
   - Execute import

3. **Post-Import**
   - Save generated passwords securely
   - Download detailed report
   - Distribute credentials to users
   - Monitor first-time logins

### Group Management

Users can be automatically assigned to groups during import:

- **Schedule Officers**: For project scheduling staff
- **Store Officers**: For inventory management staff  
- **Transporters**: For logistics staff
- **Consultants**: For external consultants
- **default**: For general users

## 📈 Best Practices

### Data Preparation
- Use consistent naming conventions for usernames
- Verify email addresses before import
- Remove test/dummy data
- Sort data alphabetically for easier review

### Security
- Import during off-peak hours
- Notify users about account creation
- Provide secure password distribution method
- Set up password change requirements

### Monitoring
- Review import logs regularly
- Monitor failed login attempts
- Track password change compliance
- Audit user access patterns

## 🆘 Support

### Getting Help

1. **Check the validation messages** - they usually indicate the exact issue
2. **Use dry-run mode** to test without creating users
3. **Review the detailed import report** for specific error information
4. **Test with a small sample** before large imports

### Contact Information

For technical support or questions about the user import functionality, contact your system administrator or development team.

---

## 📝 Changelog

### Version 1.0
- Initial Excel user import functionality
- Automatic password generation
- Django admin integration
- Management command interface
- Comprehensive validation and error handling
