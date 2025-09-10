#!/usr/bin/env python
"""Test database connection and configuration."""
import os
import sys
import django
from django.conf import settings

def test_database():
    """Test database connection and configuration."""
    # Set up Django environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
    django.setup()
    
    from django.db import connection
    
    print("Testing database connection...")
    print(f"Database Engine: {settings.DATABASES['default']['ENGINE']}")
    print(f"Database Name: {settings.DATABASES['default'].get('NAME', 'N/A')}")
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version();")
            db_version = cursor.fetchone()
            print(f"✓ Database connection successful!")
            print(f"Database version: {db_version[0]}")
            
            # Test if we can query the database
            cursor.execute("SELECT 1")
            print("✓ Basic query test passed!")
            
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_database()
