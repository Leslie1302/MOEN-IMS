import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
django.setup()

from django_otp.plugins.otp_totp.models import TOTPDevice
from django.contrib.auth.models import User
from django_otp.util import random_hex

# Create a test user
user, _ = User.objects.get_or_create(username="testuser_debug")

# Create a TOTP device
device, _ = TOTPDevice.objects.get_or_create(user=user, name="test_device")
if not device.key:
    device.key = random_hex(20)
    device.save()

print(f"Device Key (Hex): {device.key}")
print(f"Config URL: {device.config_url}")
