# Server change request — MOEN-IMS (moen-ims, Azure App Service)

**Requested by:** Leslie Nii Adjetey · **Date:** 6 August 2026
**Time required:** about 2 minutes · **Restart required:** yes (one restart)

---

## What I need

**Set the App Service Startup Command to:**

```
bash start.sh
```

Azure Portal → App Services → **moen-ims** → Settings → **Configuration** →
**General settings** → *Startup Command* → paste the line above → **Save** →
confirm the restart prompt.

That is the entire change. No other settings, no package installs by hand.

---

## Why

`start.sh` already ships with the application, at the root of what gets
deployed. It is currently never executed, because with no Startup Command set
App Service falls back to its own generated gunicorn line and ignores the script.

The script does three things on each boot:

1. installs the system libraries the PDF renderer needs (`libpango`,
   `libharfbuzz`, `libglib`, and friends);
2. applies any pending database migrations;
3. starts gunicorn exactly as App Service does today.

Step 3 is unchanged behaviour, so this does not alter how the app is served.

**Why it must be the Startup Command and not a one-off `apt-get` over SSH:**
App Service rebuilds the container filesystem on every restart, scale event and
deployment. Libraries installed by hand are gone the next time the app cycles,
and the problem silently returns. The Startup Command is the only place that
persists.

---

## Current impact

Without this, the application starts and most of it works, but it **cannot
generate any PDF**. In practice that means:

- approval memos and release letters cannot be produced;
- the Ag. Director and the Chief Director cannot sign anything;
- releases cannot progress to the Materials Management Unit.

---

## How to confirm it worked

After the restart, open the log stream (App Service → Monitoring → **Log
stream**) and look for either line near the start of the boot:

```
[start.sh] WeasyPrint 69.0 ready.
```

```
[start.sh] WARNING: WeasyPrint unusable -> ...
```

The script deliberately prints one or the other, so the outcome is unambiguous.
If it reports a warning, please send me that line — it names the missing piece.

I can also confirm from my side without portal access: a warning banner in the
application disappears on its own once the renderer is available.

---

## If it causes any problem

Clear the Startup Command field and save. App Service reverts to its generated
gunicorn line and the app returns to exactly its current behaviour. Nothing
else is modified — the change is a single configuration field.

---

## Reference

- Script: `start.sh`, at the root of the deployed application
- Deployed from: `IMS/Inventory_management_system/` (GitHub Actions workflow
  `main_moen-ims.yml`)
- App Service: **moen-ims**, Production slot
