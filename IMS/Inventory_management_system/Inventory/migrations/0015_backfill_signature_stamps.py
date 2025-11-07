# Generated manually for backfilling signature stamps to existing profiles

from django.db import migrations
from django.utils import timezone
import uuid
import logging

logger = logging.getLogger(__name__)


def generate_signature_stamp(username):
    """
    Generate a unique digital signature stamp for a user.
    
    Args:
        username (str): The username to include in the stamp
        
    Returns:
        str: The generated signature stamp
    """
    try:
        # Generate timestamp in ISO format
        timestamp = timezone.now().isoformat()
        
        # Generate unique identifier using UUID
        unique_id = uuid.uuid4().hex[:12].upper()
        
        # Create the signature stamp
        stamp = f"SIGNED_BY:{username}|TIMESTAMP:{timestamp}|ID:{unique_id}"
        
        return stamp
    except Exception as e:
        logger.error(f"Error generating signature stamp for user {username}: {str(e)}")
        return None


def backfill_signature_stamps(apps, schema_editor):
    """
    Backfill signature stamps for all existing profiles that don't have one.
    
    This function:
    1. Retrieves all Profile objects
    2. Checks if they have a user and the user has a username
    3. Generates a signature stamp if one doesn't exist
    4. Handles errors gracefully to prevent migration failure
    
    Args:
        apps: Django apps registry
        schema_editor: Database schema editor
    """
    # Get the Profile model from the migration state
    Profile = apps.get_model('Inventory', 'Profile')
    
    # Track statistics
    total_profiles = 0
    stamps_created = 0
    skipped_no_user = 0
    skipped_no_username = 0
    skipped_already_has_stamp = 0
    errors = 0
    
    # Get all profiles
    profiles = Profile.objects.all()
    total_profiles = profiles.count()
    
    logger.info(f"Starting signature stamp backfill for {total_profiles} profiles...")
    
    for profile in profiles:
        try:
            # Check if profile already has a signature stamp
            if profile.signature_stamp:
                skipped_already_has_stamp += 1
                continue
            
            # Check if profile has a user
            if not profile.user:
                logger.warning(f"Profile {profile.pk} has no associated user - skipping")
                skipped_no_user += 1
                continue
            
            # Check if user has a username
            if not hasattr(profile.user, 'username') or not profile.user.username:
                logger.warning(f"Profile {profile.pk} user has no username - skipping")
                skipped_no_username += 1
                continue
            
            # Generate and save the signature stamp
            stamp = generate_signature_stamp(profile.user.username)
            
            if stamp:
                profile.signature_stamp = stamp
                profile.save(update_fields=['signature_stamp'])
                stamps_created += 1
                logger.info(f"Created signature stamp for user: {profile.user.username}")
            else:
                logger.error(f"Failed to generate stamp for profile {profile.pk}")
                errors += 1
                
        except Exception as e:
            # Log error but continue with other profiles
            logger.error(f"Error processing profile {profile.pk}: {str(e)}")
            errors += 1
            continue
    
    # Log summary
    logger.info(f"""
    Signature Stamp Backfill Summary:
    ---------------------------------
    Total profiles: {total_profiles}
    Stamps created: {stamps_created}
    Already had stamps: {skipped_already_has_stamp}
    Skipped (no user): {skipped_no_user}
    Skipped (no username): {skipped_no_username}
    Errors: {errors}
    """)
    
    # Print to console as well
    print(f"\nSignature Stamp Backfill Complete:")
    print(f"  Created: {stamps_created}")
    print(f"  Skipped: {skipped_already_has_stamp + skipped_no_user + skipped_no_username}")
    print(f"  Errors: {errors}")


def reverse_backfill(apps, schema_editor):
    """
    Reverse migration - clear all signature stamps.
    
    WARNING: This will remove all signature stamps from profiles.
    Use with caution.
    
    Args:
        apps: Django apps registry
        schema_editor: Database schema editor
    """
    Profile = apps.get_model('Inventory', 'Profile')
    
    # Clear all signature stamps
    count = Profile.objects.filter(signature_stamp__isnull=False).update(signature_stamp=None)
    
    logger.info(f"Cleared {count} signature stamps during reverse migration")
    print(f"\nCleared {count} signature stamps")


class Migration(migrations.Migration):
    """
    Data migration to backfill signature stamps for existing profiles.
    
    This migration is safe to run multiple times - it will only create stamps
    for profiles that don't already have one.
    """

    dependencies = [
        ('Inventory', '0014_add_signature_stamp_to_profile'),
    ]

    operations = [
        migrations.RunPython(
            backfill_signature_stamps,
            reverse_code=reverse_backfill,
        ),
    ]
