# User Groups Setup Guide for MOEN-IMS

This guide explains how to set up and use user groups in your Inventory Management System.

## Overview

The system uses Django's built-in user groups to control access to different features. Each group has specific permissions that determine what users can see and do.

## Available Groups

### 1. Schedule Officer
- **Purpose**: Users who request materials and view orders
- **Permissions**: 
  - View material orders
  - Create material orders
  - Edit material orders
  - View transport information
  - View site receipts

### 2. Storekeeper
- **Purpose**: Users who manage inventory and process orders
- **Permissions**: 
  - All Schedule Officer permissions
  - Create and manage material transports
  - Upload and manage release letters
  - Create and edit site receipts

### 3. Transport Officer
- **Purpose**: Users who manage transportation and logistics
- **Permissions**:
  - View material orders
  - Create and manage material transports
  - View release letters
  - View site receipts

### 4. Consultant
- **Purpose**: Users who work on site and log receipts
- **Permissions**:
  - View material orders and transports
  - Create and edit site receipts

### 5. Management
- **Purpose**: Users with oversight and reporting access
- **Permissions**:
  - View all data
  - Manage bills of quantity
  - Access enhanced dashboard

## Setup Instructions

### Step 1: Create Groups and Permissions

Run the management command to automatically create all groups with proper permissions:

```bash
cd IMS/Inventory_management_system
python manage.py setup_groups
```

This command will:
- Create all necessary groups
- Assign appropriate permissions to each group
- Show you what was created

### Step 2: Assign Users to Groups

#### Option A: Using Django Admin Interface
1. Go to `/admin/` in your browser
2. Navigate to "Authentication and Authorization" → "Groups"
3. Click on a group name
4. Add users to the group

#### Option B: Using Django Shell
```python
python manage.py shell

# In the shell:
from django.contrib.auth.models import User, Group

# Get a user
user = User.objects.get(username='your_username')

# Get a group
group = Group.objects.get(name='Schedule Officer')

# Add user to group
user.groups.add(group)

# Check user's groups
print(user.groups.all())
```

#### Option C: Using Management Command
You can also create a custom command to assign users to groups:

```python
# In Django shell
user = User.objects.get(username='username')
group = Group.objects.get(name='Schedule Officer')
user.groups.add(group)
```

### Step 3: Test the Setup

1. Log in as a user assigned to a specific group
2. Check that the navigation menu shows the appropriate options
3. Verify that the user can access the features they should have access to

## Troubleshooting

### Common Issues

1. **Groups not showing in navigation**
   - Make sure the user is assigned to a group
   - Check that the group name matches exactly (case-sensitive)
   - Verify the user is authenticated

2. **Permissions not working**
   - Run `python manage.py setup_groups` to ensure permissions are set
   - Check that the user is in the correct group
   - Verify the group has the necessary permissions

3. **Template errors**
   - Make sure the `inventory_tags` template tags are loaded
   - Check that the template syntax is correct

### Debug Commands

Check user groups and permissions:
```python
python manage.py shell

# Check a user's groups
user = User.objects.get(username='username')
print(f"User: {user.username}")
print(f"Groups: {[g.name for g in user.groups.all()]}")

# Check group permissions
group = Group.objects.get(name='Schedule Officer')
print(f"Group: {group.name}")
print(f"Permissions: {[p.codename for p in group.permissions.all()]}")
```

## Customization

### Adding New Groups

To add a new group, edit the `setup_groups.py` command and add your group to the `groups_data` list.

### Modifying Permissions

Edit the permissions list for each group in the `setup_groups.py` command, then run it again.

### Custom Template Tags

The system includes custom template tags in `templatetags/inventory_tags.py`:
- `{% if user|has_group:"Group Name" %}` - Check if user is in a specific group
- `{% if user|is_in_group:"Group Name" %}` - Alternative group check

## Security Notes

- Superusers automatically have access to all features
- Users without groups see a limited "Awaiting Authorization" menu
- Group permissions are enforced at both template and view levels
- Always test permissions thoroughly before deploying to production

## Support

If you encounter issues:
1. Check the Django debug logs
2. Verify group assignments in Django admin
3. Test with a superuser account first
4. Check that all required models and permissions exist
