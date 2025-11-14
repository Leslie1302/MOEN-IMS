"""
Simple test script to verify Excel user import functionality.
Run this script to test the user import system.

Usage:
    python test_user_import.py
"""

import os
import sys
import django
import pandas as pd
from io import BytesIO

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
django.setup()

from django.contrib.auth.models import User, Group
from Inventory.user_import import ExcelUserImporter


def create_test_excel_file():
    """Create a test Excel file with sample user data."""
    test_data = [
        {'username': 'test_user1', 'name': 'Test User One', 'email': 'test1@example.com'},
        {'username': 'test_user2', 'name': 'Test User Two', 'email': 'test2@example.com'},
        {'username': 'test_user3', 'name': 'Test User Three', 'email': 'test3@example.com'},
    ]
    
    df = pd.DataFrame(test_data)
    
    # Save to temporary file
    test_file = 'test_users.xlsx'
    df.to_excel(test_file, index=False)
    
    print(f"✓ Created test Excel file: {test_file}")
    return test_file


def test_user_import():
    """Test the user import functionality."""
    print("=== TESTING EXCEL USER IMPORT FUNCTIONALITY ===\n")
    
    # Create test Excel file
    test_file = create_test_excel_file()
    
    try:
        # Get initial user count
        initial_count = User.objects.count()
        print(f"Initial user count: {initial_count}")
        
        # Create importer and test
        importer = ExcelUserImporter()
        
        # Test file validation
        print("\n1. Testing file validation...")
        try:
            df = importer.validate_excel_file(test_file)
            print(f"✓ File validation passed. Found {len(df)} rows to process.")
        except Exception as e:
            print(f"✗ File validation failed: {e}")
            return
        
        # Test user import
        print("\n2. Testing user import...")
        results = importer.import_users_from_excel(test_file)
        
        # Display results
        print(f"\n=== IMPORT RESULTS ===")
        print(f"Success count: {results['success_count']}")
        print(f"Error count: {results['error_count']}")
        print(f"Skipped count: {results['skipped_count']}")
        
        if results['created_users']:
            print(f"\nCreated users:")
            for user_info in results['created_users']:
                print(f"  - {user_info['username']} ({user_info['email']}) - Password: {user_info['password']}")
        
        if results['errors']:
            print(f"\nErrors:")
            for error in results['errors']:
                print(f"  - {error}")
        
        # Verify users were created
        final_count = User.objects.count()
        print(f"\nFinal user count: {final_count}")
        print(f"Users added: {final_count - initial_count}")
        
        # Test report generation
        print("\n3. Testing report generation...")
        report = importer.generate_import_report()
        print("✓ Report generated successfully")
        
        # Save report to file
        with open('import_test_report.txt', 'w') as f:
            f.write(report)
        print("✓ Report saved to: import_test_report.txt")
        
        print(f"\n=== TEST COMPLETED SUCCESSFULLY ===")
        
        # Clean up test users (optional)
        cleanup = input("\nDo you want to delete the test users? (y/N): ").lower().strip()
        if cleanup == 'y':
            test_usernames = ['test_user1', 'test_user2', 'test_user3']
            deleted_count = User.objects.filter(username__in=test_usernames).delete()[0]
            print(f"Deleted {deleted_count} test users.")
        
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Clean up test file
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"✓ Cleaned up test file: {test_file}")


def test_password_generation():
    """Test password generation functionality."""
    print("\n=== TESTING PASSWORD GENERATION ===")
    
    importer = ExcelUserImporter()
    
    # Generate multiple passwords and check characteristics
    passwords = [importer.generate_secure_password() for _ in range(5)]
    
    print("Generated passwords:")
    for i, password in enumerate(passwords, 1):
        print(f"  {i}. {password} (length: {len(password)})")
        
        # Check password characteristics
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*" for c in password)
        
        print(f"     Upper: {has_upper}, Lower: {has_lower}, Digit: {has_digit}, Special: {has_special}")
        
        if not all([has_upper, has_lower, has_digit, has_special]):
            print(f"     ⚠️  Password may not meet all requirements")
    
    print("✓ Password generation test completed")


def main():
    """Main test function."""
    try:
        # Test password generation
        test_password_generation()
        
        # Test user import
        test_user_import()
        
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
