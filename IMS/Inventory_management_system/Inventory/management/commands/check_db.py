from django.core.management.base import BaseCommand
from django.db import connection
import time

class Command(BaseCommand):
    help = 'Checks database connection and provides connection details'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Checking database connection...'))
        
        try:
            start_time = time.time()
            with connection.cursor() as cursor:
                # Test the connection
                cursor.execute("SELECT version();")
                db_version = cursor.fetchone()
                
                # Get database name and user
                cursor.execute("SELECT current_database(), current_user;")
                db_info = cursor.fetchone()
                
                elapsed_time = (time.time() - start_time) * 1000  # in milliseconds
                
                self.stdout.write(self.style.SUCCESS('✓ Database connection successful!'))
                self.stdout.write(f"• Database: {db_info[0]}")
                self.stdout.write(f"• User: {db_info[1]}")
                self.stdout.write(f"• Version: {db_version[0]}")
                self.stdout.write(f"• Connection Time: {elapsed_time:.2f}ms")
                
                # Get table count
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public';
                """)
                table_count = cursor.fetchone()[0]
                self.stdout.write(f"• Tables in database: {table_count}")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Database connection failed: {str(e)}'))
            raise

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed database information',
        )
