# Developer Quick Reference Guide

## Quick Start

### Setup Development Environment

```bash
# Clone repository
git clone https://github.com/[repo]/MOEN-IMS.git
cd MOEN-IMS

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Apply migrations
cd IMS/Inventory_management_system
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run development server
python manage.py runserver
```

### Access Points
- **Admin Panel**: http://localhost:8000/admin/
- **Main Dashboard**: http://localhost:8000/
- **Material Requests**: http://localhost:8000/request-material/
- **Material Orders**: http://localhost:8000/material-orders/

---

## Common Development Tasks

### 1. Adding a New Model

```python
# In /Inventory/models.py or create new file

import auto_prefetch
from django.db import models
from django.contrib.auth.models import User

class YourModel(auto_prefetch.Model):
    """Brief description of the model"""
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    user = auto_prefetch.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-created_at']
        verbose_name = 'Your Model'
        verbose_name_plural = 'Your Models'
    
    def __str__(self):
        return self.name
```

**Then**:
```bash
python manage.py makemigrations
python manage.py migrate
```

### 2. Creating a New View

```python
# In /Inventory/views.py or create specialized file

from django.views.generic import ListView, DetailView, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from .models import YourModel
from .forms import YourForm

# List View
class YourModelListView(LoginRequiredMixin, ListView):
    model = YourModel
    template_name = 'Inventory/your_model_list.html'
    context_object_name = 'items'
    paginate_by = 50
    
    def get_queryset(self):
        queryset = super().get_queryset()
        # Add filtering logic
        return queryset

# Detail View
class YourModelDetailView(LoginRequiredMixin, DetailView):
    model = YourModel
    template_name = 'Inventory/your_model_detail.html'
    context_object_name = 'item'

# Create View
class YourModelCreateView(LoginRequiredMixin, CreateView):
    model = YourModel
    form_class = YourForm
    template_name = 'Inventory/your_model_form.html'
    success_url = reverse_lazy('your_model_list')
    
    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)
```

### 3. Creating a Form

```python
# In /Inventory/forms.py

from django import forms
from .models import YourModel

class YourForm(forms.ModelForm):
    class Meta:
        model = YourModel
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def clean_name(self):
        """Custom validation for name field"""
        name = self.cleaned_data.get('name')
        if YourModel.objects.filter(name=name).exists():
            raise forms.ValidationError("This name already exists.")
        return name
```

### 4. Adding URL Patterns

```python
# In /Inventory/urls.py

from django.urls import path
from .views import (
    YourModelListView,
    YourModelDetailView,
    YourModelCreateView,
)

urlpatterns = [
    # ... existing patterns ...
    
    path('your-models/', YourModelListView.as_view(), name='your_model_list'),
    path('your-models/<int:pk>/', YourModelDetailView.as_view(), name='your_model_detail'),
    path('your-models/create/', YourModelCreateView.as_view(), name='your_model_create'),
]
```

### 5. Creating a Template

```html
<!-- /Inventory/templates/Inventory/your_model_list.html -->

{% extends 'Inventory/base.html' %}
{% load static %}

{% block title %}Your Models{% endblock %}

{% block content %}
<div class="container mt-4">
    <div class="row">
        <div class="col-md-12">
            <h2>Your Models</h2>
            
            <a href="{% url 'your_model_create' %}" class="btn btn-primary mb-3">
                Create New
            </a>
            
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Created</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in items %}
                    <tr>
                        <td>{{ item.name }}</td>
                        <td>{{ item.created_at|date:"Y-m-d" }}</td>
                        <td>
                            <a href="{% url 'your_model_detail' item.pk %}" class="btn btn-sm btn-info">
                                View
                            </a>
                        </td>
                    </tr>
                    {% empty %}
                    <tr>
                        <td colspan="3" class="text-center">No items found.</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            
            <!-- Pagination -->
            {% if is_paginated %}
            <nav>
                <ul class="pagination">
                    {% if page_obj.has_previous %}
                    <li class="page-item">
                        <a class="page-link" href="?page=1">First</a>
                    </li>
                    <li class="page-item">
                        <a class="page-link" href="?page={{ page_obj.previous_page_number }}">Previous</a>
                    </li>
                    {% endif %}
                    
                    <li class="page-item active">
                        <span class="page-link">
                            Page {{ page_obj.number }} of {{ page_obj.paginator.num_pages }}
                        </span>
                    </li>
                    
                    {% if page_obj.has_next %}
                    <li class="page-item">
                        <a class="page-link" href="?page={{ page_obj.next_page_number }}">Next</a>
                    </li>
                    <li class="page-item">
                        <a class="page-link" href="?page={{ page_obj.paginator.num_pages }}">Last</a>
                    </li>
                    {% endif %}
                </ul>
            </nav>
            {% endif %}
        </div>
    </div>
</div>
{% endblock %}
```

### 6. Adding a Signal for Notifications

```python
# In /Inventory/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import YourModel, Notification
from django.contrib.auth.models import User

@receiver(post_save, sender=YourModel)
def notify_on_your_model_create(sender, instance, created, **kwargs):
    """Send notification when YourModel is created"""
    if created:
        # Notify specific users (e.g., admins)
        admins = User.objects.filter(is_staff=True)
        
        for admin in admins:
            Notification.objects.create(
                recipient=admin,
                notification_type='your_model_created',
                title=f'New {instance._meta.verbose_name} Created',
                message=f'{instance.name} was created by {instance.user.username}',
                related_object_id=instance.id
            )
```

### 7. Adding Custom Permissions

```python
# In your model

class YourModel(auto_prefetch.Model):
    # ... fields ...
    
    class Meta(auto_prefetch.Model.Meta):
        permissions = [
            ("can_approve_your_model", "Can approve your model"),
            ("can_export_your_model", "Can export your model data"),
        ]
```

**Then check in views**:
```python
from django.contrib.auth.decorators import permission_required

@permission_required('Inventory.can_approve_your_model')
def approve_view(request, pk):
    # ... your logic ...
    pass
```

### 8. Creating Custom Management Command

```python
# Create: /Inventory/management/commands/your_command.py

from django.core.management.base import BaseCommand
from Inventory.models import YourModel

class Command(BaseCommand):
    help = 'Description of your command'
    
    def add_arguments(self, parser):
        parser.add_argument('--option', type=str, help='Optional argument')
    
    def handle(self, *args, **options):
        self.stdout.write('Starting command...')
        
        # Your logic here
        items = YourModel.objects.all()
        count = items.count()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully processed {count} items')
        )
```

**Run with**:
```bash
python manage.py your_command --option value
```

### 9. Adding Admin Interface

```python
# In /Inventory/admin.py

from django.contrib import admin
from .models import YourModel

@admin.register(YourModel)
class YourModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'created_at', 'updated_at']
    list_filter = ['created_at', 'user']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description')
        }),
        ('Metadata', {
            'fields': ('user', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # New object
            obj.user = request.user
        super().save_model(request, obj, form, change)
```

### 10. Creating AJAX Endpoint

```python
# In views
from django.http import JsonResponse

def your_ajax_view(request):
    if request.method == 'POST':
        # Process data
        data = request.POST.get('data')
        
        # Your logic
        result = process_data(data)
        
        return JsonResponse({
            'success': True,
            'message': 'Data processed successfully',
            'data': result
        })
    
    return JsonResponse({'error': 'Invalid request'}, status=400)
```

**JavaScript**:
```javascript
fetch('/your-ajax-endpoint/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({ data: 'your data' })
})
.then(response => response.json())
.then(data => {
    console.log('Success:', data);
})
.catch(error => {
    console.error('Error:', error);
});
```

---

## Code Patterns & Best Practices

### Model Design

```python
# ✅ GOOD: Use auto_prefetch for performance
class GoodModel(auto_prefetch.Model):
    related = auto_prefetch.ForeignKey(OtherModel, on_delete=models.CASCADE)

# ❌ BAD: Don't use regular Django models
class BadModel(models.Model):
    related = models.ForeignKey(OtherModel, on_delete=models.CASCADE)
```

### Query Optimization

```python
# ✅ GOOD: Use select_related for ForeignKey
items = YourModel.objects.select_related('user', 'category').all()

# ✅ GOOD: Use prefetch_related for reverse FKs
orders = MaterialOrder.objects.prefetch_related('transports').all()

# ❌ BAD: N+1 queries
for order in MaterialOrder.objects.all():
    print(order.user.username)  # Triggers query for each order
```

### Form Validation

```python
# ✅ GOOD: Field-level validation
def clean_quantity(self):
    quantity = self.cleaned_data.get('quantity')
    if quantity <= 0:
        raise forms.ValidationError("Quantity must be positive")
    return quantity

# ✅ GOOD: Multi-field validation
def clean(self):
    cleaned_data = super().clean()
    start = cleaned_data.get('start_date')
    end = cleaned_data.get('end_date')
    
    if start and end and start > end:
        raise forms.ValidationError("Start date must be before end date")
    
    return cleaned_data
```

### Template Best Practices

```django
{# ✅ GOOD: Use template filters #}
{{ material.date_created|date:"Y-m-d H:i" }}
{{ material.name|title }}

{# ✅ GOOD: Handle empty querysets #}
{% for item in items %}
    {{ item.name }}
{% empty %}
    <p>No items found.</p>
{% endfor %}

{# ✅ GOOD: Use URL reversing #}
<a href="{% url 'material_detail' material.pk %}">View</a>

{# ❌ BAD: Hardcoded URLs #}
<a href="/materials/{{ material.pk }}/">View</a>
```

### View Permissions

```python
# ✅ GOOD: Use mixins for class-based views
class YourView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    permission_required = 'Inventory.view_yourmodel'
    model = YourModel

# ✅ GOOD: Use decorators for function views
@login_required
@permission_required('Inventory.view_yourmodel')
def your_view(request):
    pass
```

---

## Database Operations

### Creating Migrations

```bash
# Create migration
python manage.py makemigrations

# Create empty migration (for data migrations)
python manage.py makemigrations Inventory --empty --name your_migration_name

# View SQL without applying
python manage.py sqlmigrate Inventory 0013

# Apply migrations
python manage.py migrate

# Show migration status
python manage.py showmigrations
```

### Data Migration Example

```python
# In migrations/0013_populate_data.py

from django.db import migrations

def populate_warehouses(apps, schema_editor):
    Warehouse = apps.get_model('Inventory', 'Warehouse')
    warehouses = [
        {'name': 'Accra Central', 'code': 'WH-AC', 'location': 'Accra'},
        {'name': 'Kumasi Warehouse', 'code': 'WH-KM', 'location': 'Kumasi'},
    ]
    
    for wh_data in warehouses:
        Warehouse.objects.get_or_create(
            code=wh_data['code'],
            defaults=wh_data
        )

class Migration(migrations.Migration):
    dependencies = [
        ('Inventory', '0012_previous_migration'),
    ]
    
    operations = [
        migrations.RunPython(populate_warehouses, reverse_code=migrations.RunPython.noop),
    ]
```

### Database Shell

```bash
# Open Django shell
python manage.py shell

# Quick queries
>>> from Inventory.models import MaterialOrder, InventoryItem
>>> MaterialOrder.objects.count()
>>> InventoryItem.objects.filter(quantity__lt=10)
>>> item = InventoryItem.objects.first()
>>> item.warehouse.name
```

---

## Testing

### Unit Test Example

```python
# In /Inventory/tests.py

from django.test import TestCase
from django.contrib.auth.models import User
from .models import InventoryItem, Warehouse

class InventoryItemTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password')
        self.warehouse = Warehouse.objects.create(
            name='Test Warehouse',
            code='WH-TEST',
            location='Test Location'
        )
    
    def test_create_inventory_item(self):
        """Test creating an inventory item"""
        item = InventoryItem.objects.create(
            name='Test Item',
            code='TEST-001',
            quantity=100,
            warehouse=self.warehouse,
            user=self.user
        )
        self.assertEqual(item.name, 'Test Item')
        self.assertEqual(item.quantity, 100)
    
    def test_unique_code_warehouse(self):
        """Test unique_together constraint"""
        InventoryItem.objects.create(
            name='Item 1',
            code='TEST-001',
            quantity=50,
            warehouse=self.warehouse,
            user=self.user
        )
        
        with self.assertRaises(Exception):
            InventoryItem.objects.create(
                name='Item 2',
                code='TEST-001',  # Same code
                quantity=75,
                warehouse=self.warehouse,  # Same warehouse
                user=self.user
            )
```

**Run tests**:
```bash
python manage.py test Inventory
python manage.py test Inventory.tests.InventoryItemTestCase
python manage.py test --verbosity=2
```

---

## Debugging Tips

### Django Debug Toolbar

```bash
# Install
pip install django-debug-toolbar

# Add to settings.py
INSTALLED_APPS = [
    # ...
    'debug_toolbar',
]

MIDDLEWARE = [
    # ...
    'debug_toolbar.middleware.DebugToolbarMiddleware',
]

INTERNAL_IPS = ['127.0.0.1']
```

### Logging

```python
# In views.py
import logging

logger = logging.getLogger(__name__)

def your_view(request):
    logger.debug('Debug message')
    logger.info('Info message')
    logger.warning('Warning message')
    logger.error('Error message')
    logger.critical('Critical message')
```

### Print Queries

```python
from django.db import connection

# Your queries here
items = InventoryItem.objects.all()

# Print executed queries
for query in connection.queries:
    print(query['sql'])
```

---

## Deployment

### Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### Environment Variables

```python
# Use python-decouple or django-environ

# settings.py
from decouple import config

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=lambda v: [s.strip() for s in v.split(',')])
```

### Production Checklist

- [ ] Set DEBUG = False
- [ ] Configure SECRET_KEY from environment
- [ ] Set ALLOWED_HOSTS
- [ ] Configure database (PostgreSQL)
- [ ] Configure static files (AWS S3 / CDN)
- [ ] Configure media files storage
- [ ] Set up HTTPS
- [ ] Configure email backend
- [ ] Set up error logging (Sentry)
- [ ] Configure backups
- [ ] Run security checks: `python manage.py check --deploy`

---

## Useful Commands

```bash
# Database
python manage.py dbshell          # Open database shell
python manage.py dumpdata         # Export data
python manage.py loaddata         # Import data

# Users
python manage.py createsuperuser  # Create admin
python manage.py changepassword   # Change user password

# Static files
python manage.py findstatic       # Find static file location
python manage.py collectstatic    # Collect static files

# Development
python manage.py runserver        # Start dev server
python manage.py runserver 0.0.0.0:8000  # Listen on all interfaces
python manage.py shell            # Django shell
python manage.py shell_plus       # Enhanced shell (django-extensions)

# Testing
python manage.py test             # Run tests
python manage.py test --keepdb    # Reuse test database
python manage.py test --parallel  # Parallel testing

# Maintenance
python manage.py clearsessions    # Clear expired sessions
python manage.py check            # Check for problems
python manage.py check --deploy   # Deployment checks
```

---

## Git Workflow

```bash
# Feature development
git checkout -b feature/your-feature-name
# Make changes
git add .
git commit -m "feat: add your feature description"
git push origin feature/your-feature-name

# Bug fixes
git checkout -b fix/bug-description
# Make changes
git commit -m "fix: resolve bug description"

# Pull request
# Create PR on GitHub/GitLab
# Wait for review
# Merge to main
```

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Types**: feat, fix, docs, style, refactor, test, chore

**Examples**:
```
feat: add material barcode scanning
fix: resolve duplicate material lookup error
docs: update API documentation
refactor: optimize query performance
test: add unit tests for inventory model
```

---

## Resources

### Django Documentation
- Official Docs: https://docs.djangoproject.com/
- QuerySet API: https://docs.djangoproject.com/en/stable/ref/models/querysets/
- Template Tags: https://docs.djangoproject.com/en/stable/ref/templates/builtins/

### Project-Specific
- CHANGELOG.md - Feature and bug history
- SYSTEM_DOCUMENTATION.md - Complete system overview
- KNOWN_ISSUES.md - Bug tracker and feature requests
- FIX_SUMMARY_*.md - Specific fix documentation

### Useful Packages
- django-auto-prefetch - Query optimization
- django-extensions - Development utilities
- django-debug-toolbar - Debugging
- pandas - Excel processing
- pillow - Image processing

---

**Last Updated**: October 31, 2025  
**Maintainer**: MOEN Development Team
