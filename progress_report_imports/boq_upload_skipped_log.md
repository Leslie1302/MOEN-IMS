# BoQ Bulk Upload — Skipped Materials Log

_Running log. Each region upload appends a section below. Last updated: 2026-07-07._

## How to read this

The BoQ importer rejects any line whose `material_description` is not an exact existing inventory item. Skipped lines fall into three buckets:

- **TARGET-DRIVER (pole)** — pole lines (`LV Poles`, `No. of H.T. Poles`, `No.of 10/11m HT poles…`). These *do* drive HT/LV pole targets, so any community whose only pole lines were skipped shows a **0 pole target** until resolved. These are the ones worth revisiting.
- **Accessory** — stay/strain insulators, earth rods, cable lugs, line taps, etc. Not counted toward any target; skipping them has **no effect on completion %**. Only matters for stock-consumption tracking.
- **Aggregate/label** — section headers / non-materials (`Services`, `1-ph Connections`, `Stays`, `LV LINE EQUIPMENT`). Not stock items; safe to ignore.

---

## Eastern  ·  uploaded 2026-07-07

Rows: **2924** · imported: **2570** · skipped: **354**

| Skipped material | Rows | Bucket |
|---|---:|---|
| Stay Insulators | 72 | Accessory |
| Strain Insulators | 68 | Accessory |
| Earth Rod | 64 | Accessory |
| LV Poles | 57 | TARGET-DRIVER (pole) |
| No.of 10/11m HT poles, Steel/(Wood) | 44 | TARGET-DRIVER (pole) |
| Cu Cable Lugs | 20 | Accessory |
| 1-ph Connections | 12 | Aggregate/label |
| 3-ph Connections | 9 | Aggregate/label |
| Services | 2 | Aggregate/label |
| Aluminum Line Tap | 2 | Accessory |
| Bolts, Nuts and Washers | 1 | Aggregate/label |
| LV LINE EQUIPMENT | 1 | Aggregate/label |
| Service cutout | 1 | Accessory |
| Stays | 1 | Aggregate/label |

**Communities left with 0 pole target (11):** Adamufentum, Adjoago, Ankaase, Birim Central, Essase, Green Earth Farms, Kibi, Nkyenenkyene Amanfrom, Obedeka, Prepaw, Wangara New Site

---

## North East  ·  uploaded 2026-07-07

Rows: **870** · imported: **759** · skipped: **111**

| Skipped material | Rows | Bucket |
|---|---:|---|
| LV Poles | 23 | TARGET-DRIVER (pole) |
| Stay Insulators | 23 | Accessory |
| Strain Insulators | 23 | Accessory |
| Cu Cable Lugs | 22 | Accessory |
| No. of H.T. Poles | 19 | TARGET-DRIVER (pole) |
| Earth rod | 1 | Accessory |

**Communities left with 0 pole target:** none

---

## Regions still to upload

Append their sections here as you go: Upper East, Ashanti, Greater Accra, Bono East, Upper West, Volta, Northern, Central, Savannah, Bono.
