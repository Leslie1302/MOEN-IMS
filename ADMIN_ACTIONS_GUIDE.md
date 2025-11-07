# Admin Actions - Visual Guide

## Quick Reference: Signature Stamp Management in Django Admin

---

## Three Admin Actions Available

### 1. Regenerate Selected Stamps
- **What it does:** Updates stamps for profiles you select
- **Overwrites:** Yes
- **Selection matters:** Yes
- **Use for:** Fixing specific users

### 2. Regenerate ALL Stamps (Warning)
- **What it does:** Updates stamps for EVERY profile
- **Overwrites:** Yes
- **Selection matters:** No (processes all)
- **Use for:** System-wide updates

### 3. Generate Missing Stamps
- **What it does:** Creates stamps only where missing
- **Overwrites:** No
- **Selection matters:** Yes
- **Use for:** Filling gaps safely

---

## Step-by-Step: Using Admin Actions

### Step 1: Navigate to Profiles
Django Admin → Inventory → Profiles

### Step 2: Select Profiles
- Click checkboxes next to profiles
- Or use "Select all" at top

### Step 3: Choose Action
- Click the "Action" dropdown
- Select one of the three stamp actions

### Step 4: Execute
- Click "Go" button
- Review the results

---

## Common Scenarios

### Scenario 1: Fix One User Stamp
1. Search for user
2. Select the checkbox
3. Action: "Regenerate signature stamps for selected profiles"
4. Click "Go"

### Scenario 2: Fill Missing Stamps
1. Select profiles without stamps
2. Action: "Generate stamps for profiles without one"
3. Click "Go"

### Scenario 3: System-Wide Update
1. Select any profile
2. Action: "Regenerate ALL signature stamps"
3. Click "Go"

---

## Quick Actions Cheat Sheet

| I Want To... | Action to Use | Selection Needed |
|-------------|---------------|------------------|
| Fix one user stamp | Regenerate Selected | Yes |
| Fix multiple stamps | Regenerate Selected | Yes |
| Update all stamps | Regenerate ALL | No |
| Fill missing stamps | Generate Missing | Yes |
| Safe routine check | Generate Missing | Yes |

---

**See ADMIN_STAMP_MANAGEMENT.md for detailed documentation**
