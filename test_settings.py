import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from IMS.Inventory_management_system.Inventory_management_system import settings
    print("Successfully imported settings!")
    print(f"DEBUG = {settings.DEBUG}")
    print(f"ALLOWED_HOSTS = {settings.ALLOWED_HOSTS}")
except Exception as e:
    print(f"Error importing settings: {e}")
    import traceback
    traceback.print_exc()
