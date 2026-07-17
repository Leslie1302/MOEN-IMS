# MOEN-IMS — Server Commands for July 2026 Update
**For the App Service admin.** Run these once, AFTER the latest code from
`main` has deployed to the **moen-ims** App Service.

## 1. Open a shell on the app

Azure portal → App Service **moen-ims** → Development Tools → **SSH** (or Kudu → Bash), then:

```bash
cd /home/site/wwwroot
# Activate the app's environment if present (Oryx builds it as 'antenv'):
source antenv/bin/activate 2>/dev/null || true
```

## 2. Apply database migrations (required)

```bash
python manage.py migrate --noinput
```

Expected: applies `Inventory 0068_merge_role_group_aliases` (merges the
'Store Officer'/'Storekeeper' user groups into 'Store Officers', and
'Consultant' into 'Consultants') and `0069_remove_dead_order_statuses`
(removes two unused order statuses). Both are safe: no data is deleted,
users keep all their access.

## 3. Backfill Ghana-map sites from the community registry (required, one-time)

```bash
python manage.py sync_community_sites
```

Expected output: `Done. Sites created: <N>, already present: <M>.`
This creates a map site for every registered community so the Ghana map
populates from the community progress page. Safe to re-run (idempotent).

## 4. Verify

```bash
python manage.py showmigrations Inventory | tail -4
```

Expected: the last lines show `[X] 0068_...` and `[X] 0069_...`.

## 5. One-time portal setting (recommended, so future updates need no manual steps)

Portal → **moen-ims** → Configuration → General settings → **Startup Command**:

```
python manage.py migrate --noinput && gunicorn Inventory_management_system.wsgi
```

Save and restart. From then on, migrations apply automatically on every deploy.

---
*Questions: Leslie Nii Adjei (leslieniiadjetey2000@gmail.com). Nothing here
touches user data destructively; total runtime under a minute.*
