"""
Django management command for importing users from Excel files.

Usage:
    python manage.py import_users_excel path/to/users.xlsx
    python manage.py import_users_excel path/to/users.xlsx --group=default
    python manage.py import_users_excel path/to/users.xlsx --report-file=import_report.txt
"""

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group
import os
from Inventory.user_import import ExcelUserImporter


class Command(BaseCommand):
    help = 'Import users from Excel file with automatic password generation'

    def add_arguments(self, parser):
        parser.add_argument(
            'excel_file',
            type=str,
            help='Path to Excel file containing user data'
        )
        parser.add_argument(
            '--group',
            type=str,
            help='Default group to assign imported users to',
            default=None
        )
        parser.add_argument(
            '--report-file',
            type=str,
            help='Path to save detailed import report',
            default=None
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Validate file without creating users',
            default=False
        )

    def handle(self, *args, **options):
        excel_file = options['excel_file']
        default_group = options['group']
        report_file = options['report_file']
        dry_run = options['dry_run']

        # Validate file exists
        if not os.path.exists(excel_file):
            raise CommandError(f'Excel file does not exist: {excel_file}')

        # Validate group exists if specified
        if default_group:
            try:
                Group.objects.get(name=default_group)
                self.stdout.write(f'Will assign users to group: {default_group}')
            except Group.DoesNotExist:
                raise CommandError(f'Group does not exist: {default_group}')

        # Create importer
        importer = ExcelUserImporter()

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No users will be created'))
            try:
                # Just validate the file
                df = importer.validate_excel_file(excel_file)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'File validation successful. Found {len(df)} rows to process.'
                    )
                )
                
                # Show preview of data
                self.stdout.write('\nPreview of data to be imported:')
                for index, row in df.head().iterrows():
                    username = str(row.get('username', '')).strip()
                    name = str(row.get('name', '')).strip()
                    email = str(row.get('email', '')).strip()
                    self.stdout.write(f'  {username} | {name} | {email}')
                
                if len(df) > 5:
                    self.stdout.write(f'  ... and {len(df) - 5} more rows')
                    
            except Exception as e:
                raise CommandError(f'File validation failed: {str(e)}')
        else:
            # Perform actual import
            self.stdout.write(f'Starting import from: {excel_file}')
            
            try:
                results = importer.import_users_from_excel(excel_file, default_group)
                
                # Display results
                self.stdout.write('\n=== IMPORT RESULTS ===')
                self.stdout.write(f'Successfully created: {results["success_count"]} users')
                self.stdout.write(f'Errors encountered: {results["error_count"]}')
                
                if results['created_users']:
                    self.stdout.write('\nCreated users:')
                    for user_info in results['created_users']:
                        self.stdout.write(
                            f'  ✓ {user_info["username"]} ({user_info["email"]}) - Password: {user_info["password"]}'
                        )
                
                if results['errors']:
                    self.stdout.write(self.style.ERROR('\nErrors:'))
                    for error in results['errors']:
                        self.stdout.write(self.style.ERROR(f'  ✗ {error}'))
                
                # Generate and save report if requested
                if report_file:
                    report_content = importer.generate_import_report()
                    with open(report_file, 'w', encoding='utf-8') as f:
                        f.write(report_content)
                    self.stdout.write(f'\nDetailed report saved to: {report_file}')
                
                # Final status
                if results['error_count'] == 0:
                    self.stdout.write(
                        self.style.SUCCESS(f'\n✓ Import completed successfully!')
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'\n⚠ Import completed with {results["error_count"]} errors'
                        )
                    )
                    
            except Exception as e:
                raise CommandError(f'Import failed: {str(e)}')

        self.stdout.write('\nIMPORTANT: Save the generated passwords securely and share them with users through a secure channel.')
