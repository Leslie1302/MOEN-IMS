# MOEN-IMS Disaster Recovery

This document captures the backup and restore procedure for the
production MOEN-IMS deployment.

## Current architecture

- **Runtime:** Azure App Service Linux (UK South), single tenant
- **Database:** SQLite at `/home/site/data/db.sqlite3` (persistent across
  deploys; backed by Azure Files at that path)
- **Static / media:** WhiteNoise serves static; media is in
  `/home/site/wwwroot/.../media/` (also persistent on Azure Files)
- **Code:** unpacked into `/tmp/<deploy-hash>/` on each deploy
  (ephemeral; restored from git on every push)

## Backup approach

We do **daily snapshots** of `/home/site/data/db.sqlite3` to **Azure Blob
Storage in a different region** from the App Service. The blob storage
account is the only piece of state outside the App Service region; if
the UK South region has a multi-day outage, the blob is still reachable.

### One-time setup

1. **Create a storage account in a different region.** Recommended:
   - Resource group: `moen-ims-rg-dr` (separate from main RG)
   - Storage account: `moenimsbackups`
   - Region: **North Europe** (different from the UK South App Service)
   - Redundancy: GRS (geo-redundant storage)
2. **Create a container** named `moen-ims-backups`.
3. **Copy the storage account connection string** (Access keys → key1
   → Connection string).
4. **Set App Service Application Settings:**
   ```
   AZURE_BACKUP_CONNECTION_STRING=<paste connection string>
   AZURE_BACKUP_CONTAINER=moen-ims-backups
   AZURE_BACKUP_RETENTION_DAYS=30
   ```
5. **Add `azure-storage-blob` to requirements.txt** (already listed if
   you're running this version):
   ```
   azure-storage-blob>=12.19.0
   ```
6. **Schedule daily backups.** Three options, pick whichever fits:
   - **Azure Storage Lifecycle (recommended):** schedule via App Service
     Cron WebJob: deploy a `manage.py backup_db` invocation under
     `/site/wwwroot/App_Data/jobs/triggered/backup-db/run.sh` with a
     `settings.job` containing `{"schedule": "0 0 2 * * *"}` (02:00 daily
     UTC).
   - **GitHub Actions cron:** add a workflow that runs daily and hits
     an authenticated webhook on the App Service. Webhook path TBD.
   - **External scheduler:** any cron job that can call
     `https://moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net/<auth>`.

### Manual ad-hoc backup

Run from a shell session in the App Service (via the Kudu console at
`https://moen-ims-fegfgqf3c5frejfv.scm.azurewebsites.net/`):

```bash
cd /home/site/wwwroot/IMS/Inventory_management_system/
python manage.py backup_db
```

With `--dry-run` to verify config without uploading.

## Restore procedure

If the production database needs to be restored:

### Soft restore (e.g. accidental delete, want to roll back to yesterday's state)

1. **Take the production app offline** to prevent further writes:
   - Azure Portal → App Service → Stop
2. **Download the most recent backup blob:**
   - Azure Portal → Storage account → Containers → `moen-ims-backups`
     → pick the most recent `db-YYYY-MM-DDTHH-MM-SS.sqlite3` → Download
3. **SSH into the App Service** via Kudu console or `az webapp ssh`
4. **Back up the current (broken) DB file** before overwriting it:
   ```bash
   cp /home/site/data/db.sqlite3 /home/site/data/db.sqlite3.bad.$(date +%s)
   ```
5. **Replace the DB file** with the downloaded backup:
   ```bash
   # Upload the downloaded backup via Kudu's drag-and-drop to /home/site/data/
   mv /home/site/data/db-YYYY-MM-DDTHH-MM-SS.sqlite3 /home/site/data/db.sqlite3
   ```
6. **Restart the App Service:**
   - Azure Portal → App Service → Restart

### Hard restore (App Service region outage, account compromise, etc.)

1. **Stand up a new App Service in a different region** (or wait for the
   current one to recover).
2. **Deploy the code** to it from git (`main` branch).
3. **Set all App Service Application Settings** to match the original
   (especially `DJANGO_SECRET_KEY`, `MS_CLIENT_*`, `TOKEN_ENCRYPTION_KEY`).
4. **Download the most recent backup blob.**
5. **Connect to the new App Service via Kudu** and place the downloaded
   `.sqlite3` file at `/home/site/data/db.sqlite3`.
6. **Restart the new App Service.**

## DR drill schedule

Quarterly: take the most recent backup blob, restore it to a *test* App
Service (separate slot or separate environment), verify the application
boots, log in, navigate to dashboards, confirm data integrity. Document
results in this file.

| Date | Drill result | Notes |
|------|--------------|-------|
| (pending) | — | First drill scheduled within 30 days of go-live |

## What this does NOT cover

- **Media files** (uploaded scans, weekly reports, etc.) are at
  `/home/site/wwwroot/...media/` on the App Service Files share, **not
  backed up by this command**. They are backed up by Azure's underlying
  Files redundancy, but if you want cross-region redundancy for them too,
  add an `azcopy` or `rclone sync` to the daily backup job.
- **Microsoft 365 OAuth tokens** stored encrypted in
  `MicrosoftCredentials`. After a restore, users may need to re-auth.
- **Real-time replication.** This is a daily snapshot, not a hot
  standby. Up to 24 hours of writes can be lost in the worst case.

## Until you have done two successful drills

**Keep physical paper files as the system of record.** The digital
system is the primary working copy, but paper backups remain ground
truth until restoration has been proven twice.
