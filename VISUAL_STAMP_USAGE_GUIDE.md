# Visual Digital Signature Stamp - Usage Guide

## Overview

The digital signature stamp system now includes beautiful visual stamps that look like official authorization stamps, similar to the example you provided.

---

## 🎨 What It Looks Like

### Visual Stamp Example

```
┌─────────────────────────────────────┐
│     AUTHORIZED SIGNATURE            │
│                                     │
│            nii                      │
│        Administrator                │
│                                     │
│  Since 2024  |  ID: C54C340F5A3B    │
└─────────────────────────────────────┘
```

**Features:**
- Red double border (like official stamps)
- Username prominently displayed
- User role/title
- Year stamp was created
- Unique ID for verification
- Hover effects and shadows
- Responsive sizing

---

## 📦 Files Created

### 1. Template Tag
**File:** `Inventory/templatetags/signature_tags.py`
- Custom template tags for rendering stamps
- Filters for checking signatures
- Inline signature badges

### 2. Stamp Template
**File:** `Inventory/templates/Inventory/signature_stamp.html`
- HTML structure for the visual stamp
- Handles missing signatures gracefully

### 3. CSS Styling
**File:** `Inventory/static/css/signature_stamp.css`
- Beautiful stamp styling
- Multiple size variants (small, medium, large)
- Color schemes (red, blue, green, purple)
- Responsive design
- Print-friendly styles

---

## 🚀 How to Use

### Step 1: Load the CSS

Add to your base template (e.g., `base.html`):

```html
{% load static %}
<!DOCTYPE html>
<html>
<head>
    <!-- Other CSS files -->
    <link rel="stylesheet" href="{% static 'css/signature_stamp.css' %}">
</head>
<body>
    {% block content %}{% endblock %}
</body>
</html>
```

### Step 2: Use in Templates

#### Basic Usage

```django
{% load signature_tags %}

<!-- Display a signature stamp -->
{% signature_stamp user.profile %}
```

#### With Size Options

```django
{% load signature_tags %}

<!-- Small stamp -->
{% signature_stamp user.profile size='small' %}

<!-- Medium stamp (default) -->
{% signature_stamp user.profile size='medium' %}

<!-- Large stamp -->
{% signature_stamp user.profile size='large' %}
```

#### Inline Badge

```django
{% load signature_tags %}

<!-- Compact inline signature -->
Approved by: {% signature_stamp_inline user.profile %}
```

---

## 📋 Complete Examples

### Example 1: Material Order Approval

```django
{% load signature_tags %}

<div class="order-details">
    <h3>Material Order #{{ order.request_code }}</h3>
    
    <div class="order-info">
        <p><strong>Material:</strong> {{ order.name }}</p>
        <p><strong>Quantity:</strong> {{ order.quantity }} {{ order.unit }}</p>
        <p><strong>Status:</strong> {{ order.status }}</p>
    </div>
    
    {% if order.processed_by %}
    <div class="approval-section">
        <h4>Processed By:</h4>
        {% signature_stamp order.processed_by.profile size='medium' %}
        <p class="process-date">{{ order.processed_at|date:"F d, Y at g:i A" }}</p>
    </div>
    {% endif %}
</div>
```

### Example 2: Document Signing

```django
{% load signature_tags %}

<div class="document-signatures">
    <h4>Authorized Signatures</h4>
    
    <div class="signature-stamps-container">
        <!-- Requester -->
        <div class="stamp-card">
            <div class="stamp-card-header">Requested By</div>
            {% signature_stamp order.user.profile %}
            <div class="stamp-card-footer">
                {{ order.date_requested|date:"M d, Y" }}
            </div>
        </div>
        
        <!-- Processor -->
        {% if order.processed_by %}
        <div class="stamp-card">
            <div class="stamp-card-header">Processed By</div>
            {% signature_stamp order.processed_by.profile %}
            <div class="stamp-card-footer">
                {{ order.processed_at|date:"M d, Y" }}
            </div>
        </div>
        {% endif %}
    </div>
</div>
```

### Example 3: User Profile Page

```django
{% load signature_tags %}

<div class="profile-page">
    <h2>User Profile</h2>
    
    <div class="profile-info">
        <div class="profile-picture">
            <img src="{{ user.profile.profile_picture_url }}" alt="Profile">
        </div>
        
        <div class="profile-details">
            <h3>{{ user.get_full_name }}</h3>
            <p>{{ user.email }}</p>
        </div>
    </div>
    
    <div class="profile-signature">
        <h4>Digital Signature</h4>
        {% signature_stamp user.profile size='large' %}
        
        {% if user.profile|has_signature %}
        <p class="signature-info">
            This signature was created on {{ user.profile|signature_date }}
        </p>
        {% endif %}
    </div>
</div>
```

### Example 4: Audit Trail

```django
{% load signature_tags %}

<div class="audit-trail">
    <h3>Approval History</h3>
    
    <div class="timeline">
        {% for action in audit_actions %}
        <div class="timeline-item">
            <div class="timeline-marker"></div>
            <div class="timeline-content">
                <div class="action-header">
                    <strong>{{ action.action }}</strong>
                    <span class="action-date">{{ action.date|date:"M d, Y g:i A" }}</span>
                </div>
                
                {% if action.performed_by %}
                <div class="action-signature">
                    {% signature_stamp action.performed_by.profile size='small' %}
                </div>
                {% endif %}
                
                <p class="action-notes">{{ action.notes }}</p>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
```

### Example 5: PDF/Print View

```django
{% load signature_tags %}

<div class="printable-document">
    <div class="document-header">
        <h1>Material Release Authorization</h1>
        <p>Request Code: {{ order.request_code }}</p>
    </div>
    
    <div class="document-body">
        <!-- Document content -->
    </div>
    
    <div class="document-footer">
        <div class="signature-section">
            <div class="signature-block">
                <p><strong>Requested By:</strong></p>
                {% signature_stamp order.user.profile %}
                <p class="signature-date">{{ order.date_requested|date:"F d, Y" }}</p>
            </div>
            
            <div class="signature-block">
                <p><strong>Approved By:</strong></p>
                {% signature_stamp order.processed_by.profile %}
                <p class="signature-date">{{ order.processed_at|date:"F d, Y" }}</p>
            </div>
        </div>
    </div>
</div>
```

---

## 🎨 Customization Options

### Size Variants

```django
<!-- Small (180px wide) -->
{% signature_stamp profile size='small' %}

<!-- Medium (240px wide) - Default -->
{% signature_stamp profile size='medium' %}

<!-- Large (300px wide) -->
{% signature_stamp profile size='large' %}
```

### Color Schemes

Modify the template to add color classes:

```html
<!-- In signature_stamp.html -->
<div class="digital-signature-stamp signature-{{ size }}">
    <div class="stamp-border stamp-blue">  <!-- Add color class here -->
        <!-- Rest of stamp -->
    </div>
</div>
```

**Available colors:**
- `stamp-blue` - Blue border
- `stamp-green` - Green border
- `stamp-purple` - Purple border
- Default (no class) - Red border

### With Animation

```html
<div class="digital-signature-stamp signature-medium stamp-animated">
    <!-- Stamp content -->
</div>
```

---

## 🔧 Template Filters

### Check if Profile Has Signature

```django
{% load signature_tags %}

{% if user.profile|has_signature %}
    <p>User has a valid signature</p>
{% else %}
    <p>No signature found</p>
{% endif %}
```

### Get Username from Signature

```django
{% load signature_tags %}

<p>Signed by: {{ user.profile|signature_username }}</p>
```

### Get Formatted Date

```django
{% load signature_tags %}

<p>Signed on: {{ user.profile|signature_date }}</p>
```

---

## 📱 Responsive Behavior

The stamps automatically adjust for different screen sizes:

- **Desktop:** Full size as specified
- **Tablet:** Slightly smaller
- **Mobile:** Compact version
- **Print:** Optimized for printing

---

## 🖨️ Print Styling

Stamps are automatically print-friendly:

```css
@media print {
    .digital-signature-stamp {
        box-shadow: none;
        page-break-inside: avoid;
    }
}
```

---

## 💡 Advanced Usage

### Multiple Stamps in a Grid

```django
{% load signature_tags %}

<div class="stamp-grid">
    {% for approver in approvers %}
        <div class="stamp-card">
            <div class="stamp-card-header">{{ approver.role }}</div>
            {% signature_stamp approver.profile %}
            <div class="stamp-card-footer">
                {{ approver.approved_at|date:"M d, Y" }}
            </div>
        </div>
    {% endfor %}
</div>
```

### Stamp with Tooltip

```django
<div class="stamp-with-tooltip">
    {% signature_stamp user.profile %}
    <div class="stamp-tooltip">
        Verified signature created on {{ user.profile|signature_date }}
    </div>
</div>
```

### Conditional Stamp Display

```django
{% load signature_tags %}

{% if order.status == 'Approved' and order.processed_by %}
    <div class="approval-stamp">
        <h4>Approved</h4>
        {% signature_stamp order.processed_by.profile size='large' %}
    </div>
{% elif order.status == 'Pending' %}
    <div class="pending-notice">
        <p>Awaiting approval signature...</p>
    </div>
{% endif %}
```

---

## 🎯 Integration with Existing Views

### Update Material Order Detail View

```python
# views.py
from django.shortcuts import render
from .models import MaterialOrder

def material_order_detail(request, pk):
    order = MaterialOrder.objects.get(pk=pk)
    
    context = {
        'order': order,
        # Profiles are automatically accessible via user.profile
    }
    
    return render(request, 'Inventory/material_order_detail.html', context)
```

```django
<!-- material_order_detail.html -->
{% extends 'base.html' %}
{% load signature_tags %}

{% block content %}
<div class="order-detail">
    <h2>Material Order Details</h2>
    
    <!-- Order information -->
    
    {% if order.processed_by %}
    <div class="signatures">
        <h3>Authorization</h3>
        {% signature_stamp order.processed_by.profile %}
    </div>
    {% endif %}
</div>
{% endblock %}
```

---

## 🔍 Testing the Stamps

### Quick Test in Django Shell

```python
python manage.py shell
```

```python
from Inventory.models import Profile
from django.contrib.auth.models import User

# Get a user
user = User.objects.first()
profile = user.profile

# Check stamp data
print(profile.signature_stamp)
print(profile.display_signature_stamp())

# Test in template
from django.template import Template, Context
template = Template("""
{% load signature_tags %}
{% signature_stamp profile %}
""")
context = Context({'profile': profile})
print(template.render(context))
```

### View in Browser

1. Add to any existing template
2. Navigate to that page
3. See the beautiful stamp!

---

## 🎨 Example Layouts

### Side-by-Side Stamps

```html
<div style="display: flex; gap: 20px;">
    <div>
        <h4>Requester</h4>
        {% signature_stamp requester.profile %}
    </div>
    <div>
        <h4>Approver</h4>
        {% signature_stamp approver.profile %}
    </div>
</div>
```

### Centered Stamp

```html
<div style="text-align: center; margin: 30px 0;">
    <h3>Authorized By</h3>
    {% signature_stamp user.profile size='large' %}
</div>
```

### Stamp in Card

```html
<div class="card">
    <div class="card-header">
        <h4>Digital Signature</h4>
    </div>
    <div class="card-body" style="text-align: center;">
        {% signature_stamp user.profile %}
    </div>
    <div class="card-footer text-muted">
        Created: {{ user.profile|signature_date }}
    </div>
</div>
```

---

## 📊 Real Example from Your System

Based on your users, here's how stamps will look:

### User: Nii (Administrator)
```
┌─────────────────────────────────────┐
│     AUTHORIZED SIGNATURE            │
│                                     │
│            Nii                      │
│        Administrator                │
│                                     │
│  Since 2024  |  ID: A7F3E9D2B1C4    │
└─────────────────────────────────────┘
```

### User: Dennis.wilson@energymin.gov.gh
```
┌─────────────────────────────────────────────────┐
│          AUTHORIZED SIGNATURE                   │
│                                                 │
│     Dennis.wilson@energymin.gov.gh              │
│              User                               │
│                                                 │
│  Since 2024  |  ID: C9H5G1F4D3E6                │
└─────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start Checklist

- [ ] CSS file created: `signature_stamp.css`
- [ ] Template tag created: `signature_tags.py`
- [ ] Stamp template created: `signature_stamp.html`
- [ ] Add CSS to base template
- [ ] Load `signature_tags` in your templates
- [ ] Use `{% signature_stamp user.profile %}` where needed
- [ ] Test in browser

---

## 📞 Support

For customization or issues:
- Check the CSS file for styling options
- Review template tag documentation
- See examples in this guide

---

**Created:** November 6, 2024  
**Version:** 1.0.0
