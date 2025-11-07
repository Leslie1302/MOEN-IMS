# Digital Signature Lookup System - Complete Guide

## Overview

A comprehensive signature lookup and verification system that allows you to search, view, and verify digital signatures by user ID, username, email, or signature ID.

---

## 🎯 Features

### **Signature Lookup Page**
- ✅ Search by username or email
- ✅ Search by signature ID
- ✅ View all signatures at once
- ✅ Beautiful visual stamp display
- ✅ Statistics dashboard
- ✅ User information cards
- ✅ Verification badges

### **Signature Verification Page**
- ✅ Detailed signature information
- ✅ Validation status
- ✅ Raw signature data
- ✅ User account details
- ✅ Timestamp information
- ✅ Direct admin link

### **API Endpoint**
- ✅ JSON response for AJAX requests
- ✅ Quick search functionality
- ✅ Limited results for performance

---

## 📦 Files Created

### 1. **Lookup Template** ✅
**File:** `Inventory/templates/Inventory/signature_lookup.html`

Features:
- Search form with multiple fields
- Statistics cards (total users, signatures, active, staff)
- Grid layout of signature cards
- User avatars and badges
- Detailed information display
- Responsive design

### 2. **Verification Template** ✅
**File:** `Inventory/templates/Inventory/signature_verify.html`

Features:
- Validation status indicator
- Large signature stamp display
- Comprehensive user details
- Raw signature data
- Account status
- Action buttons

### 3. **Views** ✅
**File:** `Inventory/signature_lookup_view.py`

Three views:
- `signature_lookup()` - Main lookup page
- `signature_verify()` - Individual verification
- `signature_api_lookup()` - JSON API endpoint

---

## 🚀 Setup Instructions

### Step 1: Add URLs

Add to your `urls.py`:

```python
from .signature_lookup_view import signature_lookup, signature_verify, signature_api_lookup

urlpatterns = [
    # ... your existing URLs
    
    # Signature lookup and verification
    path('signatures/', signature_lookup, name='signature_lookup'),
    path('signatures/verify/<int:user_id>/', signature_verify, name='signature_verify'),
    path('api/signatures/lookup/', signature_api_lookup, name='signature_api_lookup'),
]
```

### Step 2: Update Navigation (Optional)

Add to your navigation menu:

```html
<li>
    <a href="{% url 'signature_lookup' %}">
        🔍 Signature Lookup
    </a>
</li>
```

### Step 3: Ensure CSS is Loaded

Make sure `signature_stamp.css` is in your base template:

```html
{% load static %}
<link rel="stylesheet" href="{% static 'css/signature_stamp.css' %}">
```

---

## 💡 Usage Examples

### Access the Lookup Page

```
http://localhost:8000/signatures/
```

### Search by Username

```
http://localhost:8000/signatures/?q=nii
```

### Search by Signature ID

```
http://localhost:8000/signatures/?sig_id=A7F3E9D2B1C4
```

### Verify Specific User

```
http://localhost:8000/signatures/verify/1/
```

### API Lookup

```
http://localhost:8000/api/signatures/lookup/?q=nii
```

---

## 🔍 Search Capabilities

### What You Can Search By:

1. **Username** - Partial match
   - Example: "nii" finds "Nii", "Dennis"
   
2. **Email** - Partial match
   - Example: "energymin" finds all @energymin.gov.gh users
   
3. **First Name** - Partial match
   - Example: "john" finds "John Doe"
   
4. **Last Name** - Partial match
   - Example: "smith" finds "Jane Smith"
   
5. **Signature ID** - Partial match
   - Example: "A7F3" finds signatures containing that ID

### Search Features:

- ✅ Case-insensitive
- ✅ Partial matching
- ✅ Multiple field search
- ✅ Real-time results
- ✅ Clear filters option

---

## 📊 Statistics Dashboard

The lookup page displays:

### **Total Users**
- Count of all registered users

### **With Signatures**
- Users who have digital signatures

### **Active Users**
- Currently active user accounts

### **Staff Members**
- Users with staff privileges

---

## 🎨 User Interface

### Lookup Page Layout

```
┌─────────────────────────────────────────────┐
│         🔍 Digital Signature Lookup         │
│   Search and verify digital signatures      │
└─────────────────────────────────────────────┘

┌──────────┬──────────┬──────────┬──────────┐
│  Total   │   With   │  Active  │  Staff   │
│  Users   │Signatures│  Users   │ Members  │
│    10    │    9     │    10    │    3     │
└──────────┴──────────┴──────────┴──────────┘

┌─────────────────────────────────────────────┐
│  🔎 Search Signatures                       │
│  [Username/Email] [Signature ID] [Search]   │
└─────────────────────────────────────────────┘

┌─────────┬─────────┬─────────┐
│  Card 1 │ Card 2  │ Card 3  │
│  [Nii]  │[Leslie] │ [Jet]   │
│  Stamp  │ Stamp   │ Stamp   │
└─────────┴─────────┴─────────┘
```

### Signature Card Components

Each card shows:
- User avatar (first letter of username)
- Username and email
- User role badge (Superuser/Staff/User)
- Visual signature stamp
- Verification badge
- Detailed information:
  - User ID
  - Username
  - Creation date
  - Full name
  - Account status
  - Raw signature

---

## 🔐 Verification Page

### What It Shows:

1. **Validation Status**
   - ✓ Valid Signature (green)
   - ✗ No Signature (red)

2. **Signature Stamp**
   - Large visual display
   - All stamp components

3. **User Details**
   - User ID
   - Username
   - Full name
   - Email
   - Signature created date
   - Signature ID
   - Account status
   - User role
   - Date joined
   - Last login

4. **Raw Data**
   - Complete signature string
   - Monospace font display
   - Copy-friendly format

---

## 🔧 Integration Examples

### Link to Verification from Material Order

```django
{% load signature_tags %}

<div class="order-approval">
    <h4>Processed By:</h4>
    {% signature_stamp order.processed_by.profile %}
    
    <a href="{% url 'signature_verify' order.processed_by.id %}">
        Verify Signature →
    </a>
</div>
```

### Add Lookup Link to Profile Page

```django
<div class="profile-actions">
    <a href="{% url 'signature_lookup' %}?q={{ user.username }}">
        View in Signature Lookup
    </a>
</div>
```

### AJAX Search Implementation

```javascript
// Quick signature search
function searchSignatures(query) {
    fetch(`/api/signatures/lookup/?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
            console.log(`Found ${data.count} signatures`);
            data.results.forEach(sig => {
                console.log(`${sig.username}: ${sig.signature_stamp}`);
            });
        });
}

// Usage
searchSignatures('nii');
```

---

## 📱 Responsive Design

The lookup system is fully responsive:

### Desktop (> 768px)
- 3-column signature grid
- Side-by-side search fields
- Full statistics dashboard

### Tablet (768px)
- 2-column signature grid
- Stacked search fields
- Compact statistics

### Mobile (< 576px)
- Single column layout
- Stacked search fields
- Simplified cards

---

## 🎯 Use Cases

### Use Case 1: Verify Document Signature

**Scenario:** You receive a signed document and need to verify the signature.

**Steps:**
1. Go to Signature Lookup
2. Search by username
3. Click on user card
4. Verify signature details match document

### Use Case 2: Find All Staff Signatures

**Scenario:** Need to see all staff member signatures.

**Steps:**
1. Go to Signature Lookup
2. View all signatures
3. Filter by "Staff" badge
4. Export or document as needed

### Use Case 3: Audit Trail Verification

**Scenario:** Auditing material orders and need to verify approver signatures.

**Steps:**
1. Get approver username from order
2. Search in Signature Lookup
3. Verify signature ID matches order records
4. Check timestamp aligns with approval date

### Use Case 4: User Onboarding Check

**Scenario:** Verify new users have signatures.

**Steps:**
1. Go to Signature Lookup
2. Search by new user's username
3. Verify signature exists
4. If not, regenerate via admin

---

## 🔍 API Usage

### Endpoint

```
GET /api/signatures/lookup/?q=<search_query>
```

### Request Example

```bash
curl http://localhost:8000/api/signatures/lookup/?q=nii
```

### Response Format

```json
{
    "count": 1,
    "results": [
        {
            "user_id": 1,
            "username": "Nii",
            "email": "nii@example.com",
            "full_name": "Nii Administrator",
            "is_active": true,
            "is_staff": true,
            "signature_stamp": "SIGNED_BY:Nii|TIMESTAMP:2024-11-06T10:09:45.123456+00:00|ID:A7F3E9D2B1C4",
            "stamp_data": {
                "SIGNED_BY": "Nii",
                "TIMESTAMP": "2024-11-06T10:09:45.123456+00:00",
                "ID": "A7F3E9D2B1C4"
            }
        }
    ]
}
```

### Integration Example

```python
import requests

def verify_signature_api(username):
    """Verify a signature via API"""
    response = requests.get(
        'http://localhost:8000/api/signatures/lookup/',
        params={'q': username}
    )
    
    if response.status_code == 200:
        data = response.json()
        if data['count'] > 0:
            return data['results'][0]
    
    return None

# Usage
sig = verify_signature_api('Nii')
if sig:
    print(f"Found signature for {sig['username']}")
    print(f"ID: {sig['stamp_data']['ID']}")
```

---

## 🎨 Customization

### Change Color Scheme

Edit `signature_lookup.html` CSS:

```css
.page-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    /* Change to your colors */
}
```

### Add Custom Filters

Edit `signature_lookup_view.py`:

```python
# Add role filter
role = request.GET.get('role', '')
if role == 'staff':
    profiles = profiles.filter(user__is_staff=True)
elif role == 'superuser':
    profiles = profiles.filter(user__is_superuser=True)
```

### Modify Card Layout

Edit `signature_lookup.html`:

```html
<!-- Add more details to cards -->
<div class="signature-card">
    <!-- Existing content -->
    <div class="additional-info">
        <p>Groups: {{ profile.user.groups.all|join:", " }}</p>
    </div>
</div>
```

---

## 🔒 Security Considerations

### Access Control

The lookup system requires login:
```python
@login_required
def signature_lookup(request):
    # Only authenticated users can access
```

### Recommendations:

1. **Restrict to Staff** (Optional):
   ```python
   from django.contrib.admin.views.decorators import staff_member_required
   
   @staff_member_required
   def signature_lookup(request):
       # Only staff can access
   ```

2. **Add Permission Check**:
   ```python
   from django.contrib.auth.decorators import permission_required
   
   @permission_required('Inventory.view_profile')
   def signature_lookup(request):
       # Only users with permission
   ```

3. **Log Access**:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   
   def signature_lookup(request):
       logger.info(f"Signature lookup by {request.user.username}")
       # Rest of view
   ```

---

## 📊 Performance

### Optimization Tips:

1. **Use select_related**:
   ```python
   profiles = Profile.objects.select_related('user')
   ```

2. **Limit Results**:
   ```python
   profiles = profiles[:50]  # First 50 only
   ```

3. **Add Pagination**:
   ```python
   from django.core.paginator import Paginator
   
   paginator = Paginator(profiles, 20)
   page = request.GET.get('page')
   profiles = paginator.get_page(page)
   ```

4. **Cache Statistics**:
   ```python
   from django.core.cache import cache
   
   stats = cache.get('signature_stats')
   if not stats:
       stats = calculate_stats()
       cache.set('signature_stats', stats, 300)  # 5 minutes
   ```

---

## 🐛 Troubleshooting

### Issue: "No signatures found"

**Cause:** Users don't have signatures yet.

**Solution:**
1. Go to Django admin
2. Navigate to Profiles
3. Use "Generate stamps for profiles without one" action

### Issue: Search returns no results

**Cause:** Search query doesn't match any users.

**Solution:**
- Try partial username
- Check spelling
- Try email instead
- Use "Clear" to see all signatures

### Issue: Verification page shows error

**Cause:** Invalid user ID or profile doesn't exist.

**Solution:**
- Verify user ID is correct
- Check user has a profile
- Create profile if missing

---

## 📚 Related Documentation

- **VISUAL_STAMP_USAGE_GUIDE.md** - How to use visual stamps
- **DIGITAL_SIGNATURE_STAMP_README.md** - Complete system docs
- **ADMIN_STAMP_MANAGEMENT.md** - Admin portal guide
- **STAMPS_QUICK_REFERENCE.md** - Quick reference card

---

## ✅ Quick Checklist

- [ ] URLs added to `urls.py`
- [ ] CSS loaded in base template
- [ ] Navigation link added (optional)
- [ ] Tested lookup page
- [ ] Tested verification page
- [ ] Tested API endpoint
- [ ] Customized colors (optional)
- [ ] Added security restrictions (optional)

---

**Created:** November 6, 2024  
**Version:** 1.0.0  
**Status:** ✅ Ready to Use!
