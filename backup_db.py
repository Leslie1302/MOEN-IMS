#!/usr/bin/env python3
"""
Database backup and restore utility for MOEN-IMS.

Usage:
    # Create a backup
    python backup_db.py backup backup_file.sql
    
    # Restore from backup
    python backup_db.py restore backup_file.sql
"""
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

def get_db_config():
    """Get database configuration from Django settings."""
    import django
    from django.conf import settings
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')
    django.setup()
    
    db = settings.DATABASES['default']
    return {
        'ENGINE': db['ENGINE'],
        'NAME': db['NAME'],
        'USER': db.get('USER', ''),
        'PASSWORD': db.get('PASSWORD', ''),
        'HOST': db.get('HOST', ''),
        'PORT': db.get('PORT', ''),
    }

def backup_database(output_file):
    """Backup the database to a file."""
    db = get_db_config()
    
    if 'postgresql' in db['ENGINE']:
        # PostgreSQL backup
        cmd = [
            'pg_dump',
            '-h', db.get('HOST', 'localhost'),
            '-U', db.get('USER', 'postgres'),
            '-d', db['NAME'],
            '-f', output_file
        ]
        env = os.environ.copy()
        if db.get('PASSWORD'):
            env['PGPASSWORD'] = db['PASSWORD']
    else:
        # SQLite backup (simple file copy)
        import shutil
        shutil.copy2(db['NAME'], output_file)
        print(f"Backup created at: {output_file}")
        return
    
    try:
        subprocess.run(cmd, check=True, env=env)
        print(f"Backup created at: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating backup: {e}")
        sys.exit(1)

def restore_database(backup_file):
    """Restore database from a backup file."""
    if not os.path.exists(backup_file):
        print(f"Error: Backup file not found: {backup_file}")
        sys.exit(1)
    
    db = get_db_config()
    
    if 'postgresql' in db['ENGINE']:
        # PostgreSQL restore
        cmd = [
            'psql',
            '-h', db.get('HOST', 'localhost'),
            '-U', db.get('USER', 'postgres'),
            '-d', db['NAME'],
            '-f', backup_file
        ]
        env = os.environ.copy()
        if db.get('PASSWORD'):
            env['PGPASSWORD'] = db['PASSWORD']
    else:
        # SQLite restore (simple file copy)
        import shutil
        shutil.copy2(backup_file, db['NAME'])
        print(f"Database restored from: {backup_file}")
        return
    
    try:
        subprocess.run(cmd, check=True, env=env)
        print(f"Database restored from: {backup_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error restoring database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python backup_db.py [backup|restore] filename.sql")
        sys.exit(1)
    
    action = sys.argv[1].lower()
    filename = sys.argv[2]
    
    if action == 'backup':
        backup_database(filename)
    elif action == 'restore':
        restore_database(filename)
    else:
        print(f"Unknown action: {action}. Use 'backup' or 'restore'.")
        sys.exit(1)
