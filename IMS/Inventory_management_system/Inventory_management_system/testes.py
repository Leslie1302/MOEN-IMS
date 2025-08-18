# In the Python shell
from django.contrib.auth import get_user_model
from Inventory_management_system.Inventory.models import InventoryItem, Unit, Category

# Get the first user (should be 'leslie')
user = get_user_model().objects.first()

# Create a test unit if none exists
unit = Unit.objects.first()
if not unit:
    unit = Unit.objects.create(name='Test Unit')

# Create a test category if none exists
category = Category.objects.first()
if not category:
    category = Category.objects.create(name='Test Category')

# Try to create an inventory item
try:
    item = InventoryItem.objects.create(
        name='Test Item',
        quantity=1,
        code='TEST001',
        unit=unit,
        category=category,
        user=user
    )
    print("Item created successfully!")
    print(f"Item details: {item.name}, User: {item.user}, Group: {item.group}")
except Exception as e:
    print(f"Error creating item: {e}")