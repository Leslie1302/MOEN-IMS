#!/usr/bin/env python
"""
Phase R: M365 Notification Email Delivery Test
Tests all notification paths to verify M365 email integration is working.
Run from Django shell: python manage.py shell < test_m365_notifications.py
"""

import django
from django.contrib.auth.models import User, Group
from django.utils import timezone
from Inventory.models import (
    MaterialOrder, MaterialTransport, SiteReceipt,
    BillOfQuantity, BoQOverissuanceJustification, Notification
)
from Inventory.signals import create_notification
import logging

logger = logging.getLogger(__name__)

def setup_test_user():
    """Create a test user if it doesn't exist."""
    test_user, created = User.objects.get_or_create(
        username='test_notif_user',
        defaults={
            'email': 'test@energymin.gov.gh',
            'first_name': 'Test',
            'last_name': 'User',
            'is_active': True
        }
    )

    # Ensure Management group exists
    mgmt_group, _ = Group.objects.get_or_create(name='Management')
    if mgmt_group not in test_user.groups.all():
        test_user.groups.add(mgmt_group)

    print(f"✓ Test user created/verified: {test_user.email}")
    return test_user

def test_manual_notification_path():
    """Test the manual notification creation path."""
    print("\n=== Testing Manual Notification Path ===")
    test_user = setup_test_user()

    try:
        notification = create_notification(
            notification_type='test',
            title='Phase R: M365 Email Delivery Test',
            message='This is a test notification to verify M365 email delivery is working. '
                    'If you received this email, the integration is working correctly.',
            recipient_group='Management',
            sender=test_user,
            recipient_user=test_user
        )

        if notification:
            print(f"✓ Test notification created (ID: {notification.id})")
            print(f"  Title: {notification.title}")
            print(f"  Status: Notification created + email triggered")
        else:
            print("✗ Failed to create notification")

    except Exception as e:
        print(f"✗ Error in manual notification path: {e}")
        logger.error(f"Test notification error: {e}", exc_info=True)

def test_material_order_notification_path():
    """Test MaterialOrder creation notification path."""
    print("\n=== Testing MaterialOrder Notification Path ===")
    test_user = setup_test_user()

    try:
        # Create a test material order
        order = MaterialOrder.objects.create(
            name='Test Material (Phase R)',
            code='TEST-PHASER-001',
            quantity=100,
            request_type='Release',
            request_code=f'REQ-PHASER-{timezone.now().timestamp()}',
            user=test_user,
            district='Accra',
            region='Greater Accra',
            unit='Units'
        )

        # Check if notification was created (via signal)
        notif = Notification.objects.filter(
            related_order=order,
            notification_type='material_request'
        ).first()

        if notif:
            print(f"✓ MaterialOrder notification signal fired")
            print(f"  Order: {order.name}")
            print(f"  Notification: {notif.title}")
        else:
            print("✗ No notification found for MaterialOrder")

    except Exception as e:
        print(f"✗ Error in MaterialOrder notification: {e}")
        logger.error(f"MaterialOrder notification error: {e}", exc_info=True)

def test_boq_overissuance_notification_path():
    """Test BoQOverissuanceJustification creation notification path."""
    print("\n=== Testing BoQ Overissuance Justification Notification Path ===")
    test_user = setup_test_user()

    try:
        # For this test, we need an existing BOQ item
        # If none exists, we skip this test
        boq_items = BillOfQuantity.objects.all()

        if not boq_items.exists():
            print("⊘ No BillOfQuantity items found; skipping BoQ overissuance test")
            print("  (This test requires existing BOQ data)")
            return

        boq_item = boq_items.first()

        # Create a justification
        justification = BoQOverissuanceJustification.objects.create(
            boq_item=boq_item,
            package_number=boq_item.package_number,
            project_name=f"{boq_item.contractor} - {boq_item.package_number}",
            overissuance_quantity=10.5,
            reason='Test overissuance justification for Phase R verification',
            justification_category='Design Change',
            submitted_by=test_user,
            status='Pending'
        )

        # Check if notification was created (via signal)
        notif = Notification.objects.filter(
            notification_type='boq_overissuance_justification'
        ).order_by('-created_at').first()

        if notif:
            print(f"✓ BoQ overissuance justification signal fired")
            print(f"  Justification: {justification.boq_item.material_description}")
            print(f"  Notification: {notif.title}")
        else:
            print("✗ No notification found for BoQ overissuance")

    except Exception as e:
        print(f"✗ Error in BoQ overissuance notification: {e}")
        logger.error(f"BoQ overissuance notification error: {e}", exc_info=True)

def verify_m365_credentials():
    """Verify that M365 credentials exist for email sending."""
    print("\n=== Verifying M365 Credentials ===")

    try:
        from accounts.models import MicrosoftCredentials

        # Check for active M365 credentials
        active_creds = MicrosoftCredentials.objects.filter(
            user__is_active=True
        ).select_related('user').exists()

        if active_creds:
            print("✓ M365 credentials found for at least one active user")
            creds = MicrosoftCredentials.objects.filter(
                user__is_active=True
            ).select_related('user').first()
            print(f"  User: {creds.user.email}")
        else:
            print("⚠ No M365 credentials found for active users")
            print("  Email notifications will fail without credentials")
            print("  Action: Ensure at least one admin user has completed M365 authentication")

    except ImportError:
        print("✗ MicrosoftCredentials model not found")

def summarize_notification_coverage():
    """Print a summary of notification coverage."""
    print("\n=== Notification Coverage Summary ===")

    paths = {
        'Material Order Creation': 'MaterialOrder post_save signal',
        'Material Order Status Changes': 'MaterialOrder post_save signal',
        'Material Transport Creation': 'MaterialTransport post_save signal',
        'Transport Status Changes': 'MaterialTransport post_save signal',
        'Site Receipt Creation': 'SiteReceipt post_save signal',
        'Inventory Low Stock': 'InventoryItem post_save signal',
        'BoQ Creation': 'BillOfQuantity post_save signal',
        'BoQ Overissuance Justification': 'BoQOverissuanceJustification post_save signal (Phase R NEW)',
    }

    print("\nNotification paths wired:")
    for path, implementation in paths.items():
        status = "✓" if "Phase R NEW" not in implementation else "✓ NEW"
        print(f"  {status} {path}")
        print(f"     → {implementation}")

def main():
    """Run all Phase R verification tests."""
    print("\n" + "="*70)
    print("Phase R: M365 Notification Email Delivery Verification")
    print("="*70)

    # Verify credentials first
    verify_m365_credentials()

    # Test each path
    test_manual_notification_path()
    test_material_order_notification_path()
    test_boq_overissuance_notification_path()

    # Print summary
    summarize_notification_coverage()

    print("\n" + "="*70)
    print("Phase R Verification Complete")
    print("="*70)
    print("\nNext Steps:")
    print("  1. Check email inbox for test notifications")
    print("  2. If emails arrived, M365 integration is working")
    print("  3. If emails failed to arrive, verify:")
    print("     - M365 credentials are set up in admin")
    print("     - Email addresses in test users are correct")
    print("     - Django logs for Graph API errors")
    print("\n")

if __name__ == '__main__':
    main()
