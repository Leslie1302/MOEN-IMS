# SHEP Simulation — Research Brief & Seeded Data Guide

_Prepared for MOEN-IMS end-to-end simulation, June 2026._

## 1. What SHEP is

The **Self-Help Electrification Programme (SHEP)** is a Government of Ghana rural-electrification scheme introduced in **1989** to complement the **National Electrification Scheme (NES)**. Its purpose is to accelerate grid connection by rewarding communities that take the initiative to do preparatory work themselves — chiefly procuring and erecting the low-voltage (LV) distribution poles.

A community qualifies for SHEP when it meets four conditions:

- it lies **within 20 km** of an existing **11 kV / 33 kV** (high-voltage) network;
- it **applies** to be included in the programme;
- it is **willing and able to procure and erect all the LV distribution poles** required; and
- at least **one-third of the houses** are already wired and ready to be serviced once supply arrives.

The programme has run in successive phases (SHEP-1 through the current **SHEP-4 / SHEP-5**). Recent activity includes ECG commissioning distribution transformers to energise newly connected SHEP communities (e.g. the Dambai area in the Oti Region).

## 2. Typical materials (what flows through the IMS)

SHEP and related electrification works move a recognisable bill of materials, which the seeded inventory now mirrors:

- **Poles & structures** — wooden 9 m poles, concrete 11 m poles.
- **Conductors & cables** — ACSR conductor (≈50–75 mm², "Rabbit"/"Raccoon"), LV ABC cable 4×70 mm².
- **Transformers** — pole-mounted distribution transformers, 33 kV primary, typically **50 / 100 / 200 kVA**.
- **Line hardware & insulators** — 11 kV pin and disc insulators, stay-wire sets, galvanised cross-arms.
- **Metering** — single-phase credit meters for household connections.
- **Civil** — cement and sand for pole foundations.

## 3. How the three programmes differ in the system

The IMS distinguishes three project types, which differ mainly in **who the materials are released to (the consignee)**:

| Programme | `ProjectType.code` | Consignee role | Package number |
|---|---|---|---|
| SHEP | `shep` | **Consultant** | Yes (SHEP-specific) |
| Cost Sharing | `cost_sharing` | **Member of Parliament** | No |
| Streetlights | `streetlights` | **Member of Parliament** | No |

This is why the seed links SHEP communities to a **ProjectConsultant** and Cost Sharing / Streetlights communities to a **Member of Parliament**.

## 4. The end-to-end workflow the data exercises

```
Request (MaterialOrder, type=Release)
   → Release Letter wizard: generate memo + letter (with QR)
   → get signed → upload signed scan (workflow: memo_generated → approved → released)
   → Transport / Waybill (dispatched → delivered)
   → Site Receipt (received on site)
Parallel: Receipt orders (new supply against a contract; over-issuance returns)
Backing data: BoQ allocations, Supply Contracts, Inventory stock, Projects/Sites, Ghana map
```

## 5. What was seeded (now live in your database)

Auth is preserved — your superuser **`mac`** still logs in. Everything else was flushed and rebuilt:

- **3 ProjectTypes**, **22 inventory items** (real electrification materials) across **4 warehouses**, **5 suppliers**, **4 supply contracts**.
- **10 communities** across 8 regions (4 SHEP with package numbers, 3 Cost Sharing, 3 Streetlights), each with GPS coordinates so the Ghana map renders. **6 MPs** + **1 consultant** wired in for consignee resolution.
- **4 projects** (SHEP-4, SHEP-5, CS-2026, SL-2026) + **10 project sites**; **30 BoQ lines** (complete / in-progress / not-started, including **1 deliberate over-issuance**).
- **12 release requests** spanning every lifecycle state (Pending, Approved, In Transit, Completed) × all three programmes.
- **9 release letters** — 3 `released`, 3 `approved` (signed), 3 `memo_generated` (awaiting signature). **6 transports** (3 delivered, 3 in-transit) and **3 site receipts**.
- **2 receipt orders** — one new-supply against a contract, one over-issuance return offsetting the over-issued BoQ line.
- **3 active signatories** so the release-letter wizard works out of the box.

### Demo logins (password: `Moen@2026`)

| Username | Role group | Use it to test |
|---|---|---|
| `schedule.officer` | Schedule Officers | Generate & upload release letters |
| `store.officer` | Store Officers | Fulfil / process orders |
| `stores.manager` | Stores Management | Stores oversight |
| `transport.officer` | Transport Officers | Waybills / dispatch |
| `management.lead` | Management | Approvals / dashboards |
| `consultant.shep` | Consultants | SHEP consignee view |

## 6. Re-running the simulation

The data is built by a management command. To wipe and rebuild any time (auth always preserved):

```bash
python manage.py seed_simulation --confirm --user mac
python manage.py setup_groups          # role permissions
python manage.py sync_sites_from_boq   # push BoQ completion onto the map
```

Pages to walk: `/material-orders-officers/`, `/release-letters/`, `/project-management/`, `/ghana-map/`, `/bill-of-quantity/`.

## Sources

- [Guidelines and Procedures for Rural Electrification — PURC](https://www.purc.com.gh/attachment/56890-20220113110128.pdf)
- [National Electrification Scheme — IEA Policies](https://www.iea.org/policies/4956-national-electrification-scheme)
- [Self-Help Electrification (SHEP) for the Ministry of Energy, Ghana — IPD](https://ipd.uk.com/self-help-eletrification-shep-for-the-ministry-of-energy-ghana/)
- [Self-Help Electrification Project (SHEP-4) — Wilkins Engineering](https://wilkinsengineering.com/project/self-help-electrification-project-shep-4-2/)
- [ECG commissions 21 transformers to power Dambai SHEP communities — ECG](https://ecg.com.gh/blog/2025/09/25/ecg-commissions-21-transformers-to-power-dambai-shep-communities/)
- [Report of the Parliamentary Select Committee on the SHEP — Parliament of Ghana](https://repository.parliament.gh/items/fe4a9386-e932-4f65-a228-b7a8d9ffd923)
