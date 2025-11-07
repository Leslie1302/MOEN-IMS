# Digital Signature Stamps - Quick Reference Card

## 🚀 Setup (One-Time)

### 1. Add CSS to Base Template
```html
{% load static %}
<link rel="stylesheet" href="{% static 'css/signature_stamp.css' %}">
```

### 2. Load Template Tags
```django
{% load signature_tags %}
```

---

## 💻 Basic Usage

### Display a Stamp
```django
{% signature_stamp user.profile %}
```

### With Size
```django
{% signature_stamp user.profile size='small' %}
{% signature_stamp user.profile size='medium' %}
{% signature_stamp user.profile size='large' %}
```

### Inline Badge
```django
Approved by: {% signature_stamp_inline user.profile %}
```

---

## 🔍 Filters

### Check if Has Stamp
```django
{% if user.profile|has_signature %}
    Has signature!
{% endif %}
```

### Get Username
```django
{{ user.profile|signature_username }}
```

### Get Date
```django
{{ user.profile|signature_date }}
```

---

## 📋 Common Patterns

### Material Order Approval
```django
{% if order.processed_by %}
    <h4>Processed By:</h4>
    {% signature_stamp order.processed_by.profile %}
    <p>{{ order.processed_at|date:"F d, Y" }}</p>
{% endif %}
```

### Multiple Signatures
```django
<div class="signature-stamps-container">
    <div class="stamp-card">
        <div class="stamp-card-header">Requester</div>
        {% signature_stamp order.user.profile %}
    </div>
    <div class="stamp-card">
        <div class="stamp-card-header">Approver</div>
        {% signature_stamp order.processed_by.profile %}
    </div>
</div>
```

### With Conditional
```django
{% if user.profile|has_signature %}
    {% signature_stamp user.profile %}
{% else %}
    <p>No signature available</p>
{% endif %}
```

---

## 🎨 Customization

### Color Variants
Edit `signature_stamp.html`:
```html
<div class="stamp-border stamp-blue">   <!-- Blue -->
<div class="stamp-border stamp-green">  <!-- Green -->
<div class="stamp-border stamp-purple"> <!-- Purple -->
<div class="stamp-border">              <!-- Red (default) -->
```

### Size Classes
- `.signature-small` - 180px wide
- `.signature-medium` - 240px wide (default)
- `.signature-large` - 300px wide

---

## 📁 Files Location

- **CSS:** `Inventory/static/css/signature_stamp.css`
- **Template Tag:** `Inventory/templatetags/signature_tags.py`
- **Template:** `Inventory/templates/Inventory/signature_stamp.html`
- **Demo:** `Inventory/templates/Inventory/signature_demo.html`

---

## 📖 Full Documentation

- **VISUAL_STAMP_USAGE_GUIDE.md** - Complete guide
- **VISUAL_STAMPS_IMPLEMENTATION.md** - Implementation details
- **DIGITAL_SIGNATURE_STAMP_README.md** - Full system docs

---

## ✅ Checklist

- [ ] CSS added to base template
- [ ] Template tags loaded in templates
- [ ] Stamps added to views
- [ ] Tested in browser
- [ ] Customized colors (optional)

---

**Quick Help:** See VISUAL_STAMP_USAGE_GUIDE.md for examples
