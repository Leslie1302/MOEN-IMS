"""
Phase H — daily SQLite backup to Azure Blob Storage.

Usage:
    python manage.py backup_db [--container=moen-ims-backups]

Reads the production SQLite file at /home/site/data/db.sqlite3 (or whatever
is configured), uploads a timestamped copy to the Azure Blob container
named by AZURE_BACKUP_CONTAINER, and prunes backups older than
AZURE_BACKUP_RETENTION_DAYS (default 30).

Required environment variables (set in App Service Application Settings,
in a different region than the App Service for true disaster recovery):
  - AZURE_BACKUP_CONNECTION_STRING  (Azure Storage account connection string)
  - AZURE_BACKUP_CONTAINER          (container name, default 'moen-ims-backups')
  - AZURE_BACKUP_RETENTION_DAYS     (integer, default 30)

If the env vars aren't set, the command logs a warning and exits 0
(no-op). This means schedules can be wired up before the credentials
exist, and they'll silently succeed until the credentials land.
"""

import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Back up the production SQLite database to Azure Blob Storage.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--container',
            default=os.environ.get('AZURE_BACKUP_CONTAINER', 'moen-ims-backups'),
            help='Azure Blob container to upload the backup to.',
        )
        parser.add_argument(
            '--retention-days',
            type=int,
            default=int(os.environ.get('AZURE_BACKUP_RETENTION_DAYS', '30')),
            help='Delete backups older than this many days.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would happen without uploading or deleting anything.',
        )

    def handle(self, *args, **opts):
        container_name = opts['container']
        retention_days = opts['retention_days']
        dry_run = opts['dry_run']

        # Resolve the SQLite path. Use the configured DATABASES setting.
        db_path = Path(settings.DATABASES['default']['NAME'])
        if not db_path.exists():
            self.stdout.write(self.style.ERROR(
                f"SQLite file not found at {db_path}; skipping backup."
            ))
            return

        connection_string = os.environ.get('AZURE_BACKUP_CONNECTION_STRING', '').strip()
        if not connection_string:
            self.stdout.write(self.style.WARNING(
                "AZURE_BACKUP_CONNECTION_STRING not set; skipping backup. "
                "Set it in App Service Application Settings to enable backups."
            ))
            return

        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError:
            self.stdout.write(self.style.WARNING(
                "azure-storage-blob package not installed; skipping backup. "
                "Add `azure-storage-blob` to requirements.txt to enable backups."
            ))
            return

        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')
        blob_name = f"db-{timestamp}.sqlite3"

        # Snapshot the SQLite file via shutil.copy2 (preserves mtime).
        # SQLite is durable across copy if not mid-write; the WSGI hook only
        # writes during request handling, so an off-hours backup is safe.
        snapshot_dir = Path('/tmp') if Path('/tmp').exists() else db_path.parent
        snapshot_path = snapshot_dir / f"snapshot-{timestamp}.sqlite3"
        try:
            shutil.copy2(db_path, snapshot_path)
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(f"Could not snapshot SQLite file: {exc}"))
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f"[dry-run] Would upload {snapshot_path} as {blob_name} to container '{container_name}'"
            ))
            snapshot_path.unlink(missing_ok=True)
            return

        try:
            client = BlobServiceClient.from_connection_string(connection_string)
            container_client = client.get_container_client(container_name)
            try:
                container_client.create_container()
            except Exception:
                pass  # Container already exists.

            with open(snapshot_path, 'rb') as fh:
                container_client.upload_blob(name=blob_name, data=fh, overwrite=False)

            self.stdout.write(self.style.SUCCESS(
                f"Uploaded {snapshot_path.stat().st_size} bytes as {blob_name}"
            ))
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(f"Upload failed: {exc}"))
            snapshot_path.unlink(missing_ok=True)
            return
        finally:
            snapshot_path.unlink(missing_ok=True)

        # Prune old backups.
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
            deleted = 0
            for blob in container_client.list_blobs():
                if blob.name.startswith('db-') and blob.creation_time and blob.creation_time < cutoff:
                    container_client.delete_blob(blob.name)
                    deleted += 1
            if deleted:
                self.stdout.write(self.style.SUCCESS(
                    f"Pruned {deleted} backup(s) older than {retention_days} days."
                ))
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"Pruning failed (non-fatal): {exc}"))
