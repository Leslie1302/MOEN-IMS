#!/usr/bin/env python
"""
Utility script to regenerate signature stamps for all profiles.

Usage:
    python regenerate_stamps.py [--force] [--dry-run]

Options:
    --force     Regenerate stamps even for profiles that already have one
    --dry-run   Show what would be done without making changes

Examples:
    # Dry run to see what would happen
    python regenerate_stamps.py --dry-run
    
    # Regenerate only missing stamps
    python regenerate_stamps.py
    
    # Force regenerate all stamps
    python regenerate_stamps.py --force
"""

import os
import sys
import django
import argparse

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
django.setup()

from Inventory.models import Profile
from django.contrib.auth.models import User


def regenerate_stamps(force=False, dry_run=False):
    """
    Regenerate signature stamps for profiles.
    
    Args:
        force (bool): If True, regenerate stamps even if they already exist
        dry_run (bool): If True, don't make any changes
    """
    print("=" * 70)
    print("SIGNATURE STAMP REGENERATION UTILITY")
    print("=" * 70)
    print()
    
    if dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()
    
    # Get all profiles
    all_profiles = Profile.objects.all()
    total_profiles = all_profiles.count()
    
    print(f"📊 Total profiles in database: {total_profiles}")
    print()
    
    # Statistics
    stats = {
        'processed': 0,
        'created': 0,
        'regenerated': 0,
        'skipped_no_user': 0,
        'skipped_no_username': 0,
        'skipped_has_stamp': 0,
        'errors': 0
    }
    
    # Process each profile
    for profile in all_profiles:
        stats['processed'] += 1
        
        try:
            # Check if profile has a user
            if not profile.user:
                print(f"⚠️  Profile {profile.pk}: No user - SKIPPED")
                stats['skipped_no_user'] += 1
                continue
            
            # Check if user has a username
            if not hasattr(profile.user, 'username') or not profile.user.username:
                print(f"⚠️  Profile {profile.pk}: User has no username - SKIPPED")
                stats['skipped_no_username'] += 1
                continue
            
            # Check if profile already has a stamp
            if profile.signature_stamp and not force:
                print(f"ℹ️  Profile {profile.pk} ({profile.user.username}): Already has stamp - SKIPPED")
                stats['skipped_has_stamp'] += 1
                continue
            
            # Generate/regenerate stamp
            if not dry_run:
                if profile.signature_stamp:
                    # Regenerate existing stamp
                    new_stamp = profile.regenerate_signature_stamp(force=True)
                    print(f"🔄 Profile {profile.pk} ({profile.user.username}): REGENERATED")
                    stats['regenerated'] += 1
                else:
                    # Create new stamp
                    new_stamp = profile.get_or_create_signature_stamp()
                    print(f"✅ Profile {profile.pk} ({profile.user.username}): CREATED")
                    stats['created'] += 1
            else:
                if profile.signature_stamp:
                    print(f"🔄 Profile {profile.pk} ({profile.user.username}): Would REGENERATE")
                    stats['regenerated'] += 1
                else:
                    print(f"✅ Profile {profile.pk} ({profile.user.username}): Would CREATE")
                    stats['created'] += 1
                    
        except Exception as e:
            print(f"❌ Profile {profile.pk}: ERROR - {str(e)}")
            stats['errors'] += 1
            continue
    
    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total profiles processed:     {stats['processed']}")
    print(f"Stamps created:               {stats['created']}")
    print(f"Stamps regenerated:           {stats['regenerated']}")
    print(f"Skipped (no user):            {stats['skipped_no_user']}")
    print(f"Skipped (no username):        {stats['skipped_no_username']}")
    print(f"Skipped (already has stamp):  {stats['skipped_has_stamp']}")
    print(f"Errors:                       {stats['errors']}")
    print("=" * 70)
    
    if dry_run:
        print()
        print("ℹ️  This was a dry run. No changes were made.")
        print("   Run without --dry-run to apply changes.")
    else:
        print()
        print("✅ Operation completed successfully!")
    
    return stats


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Regenerate signature stamps for user profiles',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Regenerate stamps even for profiles that already have one'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    args = parser.parse_args()
    
    # Confirm if force mode
    if args.force and not args.dry_run:
        print("⚠️  WARNING: Force mode will regenerate ALL stamps!")
        print("   This will overwrite existing stamps with new ones.")
        response = input("   Are you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Operation cancelled.")
            return
        print()
    
    # Run the regeneration
    try:
        stats = regenerate_stamps(force=args.force, dry_run=args.dry_run)
        
        # Exit with appropriate code
        if stats['errors'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n\n❌ Operation cancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
