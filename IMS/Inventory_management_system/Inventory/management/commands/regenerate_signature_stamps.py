"""
Management command to regenerate all signature stamps with first and last names.
This command updates existing signature stamps to use the new format.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from Inventory.models import Profile


class Command(BaseCommand):
    help = 'Regenerate all signature stamps to use first and last names instead of usernames'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force regeneration even for profiles that already have stamps',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be changed without actually changing anything',
        )

    def handle(self, *args, **options):
        force = options['force']
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.WARNING('=' * 70))
        self.stdout.write(self.style.WARNING('Regenerating Signature Stamps'))
        self.stdout.write(self.style.WARNING('=' * 70))
        
        if dry_run:
            self.stdout.write(self.style.NOTICE('DRY RUN MODE - No changes will be made'))
        
        # Get all profiles
        profiles = Profile.objects.select_related('user').all()
        total_count = profiles.count()
        
        self.stdout.write(f'\nFound {total_count} profile(s) to process\n')
        
        success_count = 0
        skipped_count = 0
        error_count = 0
        
        for profile in profiles:
            try:
                # Check if profile has a user
                if not profile.user:
                    self.stdout.write(
                        self.style.WARNING(f'⊗ Profile {profile.pk}: No associated user - SKIPPED')
                    )
                    skipped_count += 1
                    continue
                
                # Get user info
                user = profile.user
                first_name = user.first_name.strip() if user.first_name else ""
                last_name = user.last_name.strip() if user.last_name else ""
                username = user.username
                
                # Construct display name
                if first_name and last_name:
                    display_name = f"{first_name} {last_name}"
                elif first_name:
                    display_name = first_name
                elif last_name:
                    display_name = last_name
                else:
                    display_name = username
                
                # Show current vs new
                old_stamp = profile.signature_stamp if profile.signature_stamp else "None"
                
                if not dry_run:
                    # Regenerate the stamp
                    profile.regenerate_signature_stamp(force=True)
                    new_stamp = profile.signature_stamp
                    
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Profile {profile.pk} ({username}): {display_name}')
                    )
                    success_count += 1
                else:
                    self.stdout.write(
                        self.style.NOTICE(f'→ Would regenerate: Profile {profile.pk} ({username}): {display_name}')
                    )
                    success_count += 1
                    
            except ValueError as ve:
                self.stdout.write(
                    self.style.ERROR(f'✗ Profile {profile.pk}: {str(ve)}')
                )
                error_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Profile {profile.pk}: Unexpected error - {str(e)}')
                )
                error_count += 1
        
        # Summary
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write(self.style.WARNING('SUMMARY'))
        self.stdout.write('=' * 70)
        self.stdout.write(f'Total profiles: {total_count}')
        self.stdout.write(self.style.SUCCESS(f'Successfully processed: {success_count}'))
        self.stdout.write(self.style.WARNING(f'Skipped: {skipped_count}'))
        self.stdout.write(self.style.ERROR(f'Errors: {error_count}'))
        
        if dry_run:
            self.stdout.write(self.style.NOTICE('\nThis was a DRY RUN - no changes were made'))
            self.stdout.write(self.style.NOTICE('Run without --dry-run to apply changes'))
        else:
            self.stdout.write(self.style.SUCCESS('\n✓ Signature stamps have been regenerated!'))
