# Phase R: Notifications Coverage Audit — Completion Report
**Date:** 2026-05-18  
**Status:** ✅ COMPLETE (pending user M365 staging/prod verification)  
**Effort:** ~4 hours

---

## Summary

Phase R audited the notification system and completed the missing BoQ overissuance justification email path. All notification signals are now wired and will trigger M365 email delivery when users with valid Microsoft credentials perform relevant actions.

---

## ✅ Completed Work

### 1. Added BoQ Overissuance Justification Notification Signal
**File:** `Inventory/signals.py`

- **What was added:**
  - New signal handler: `handle_boq_overissuance_justification_notifications`
  - Listens to `BoQOverissuanceJustification` model creation
  - Automatically creates a `Notification` record when a justification is submitted
  - Triggers M365 email alert to Management group
  
- **Implementation details:**
  ```python
  @receiver(post_save, sender=BoQOverissuanceJustification)
  def handle_boq_overissuance_justification_notifications(sender, instance, created, **kwargs):
      # Creates notification with title, message, and Management group recipient
      # Triggers _trigger_email_notification() for M365 delivery
  ```

- **Email details:**
  - **Recipient:** Management group (all active users in "Management" group)
  - **Subject:** `[MOEN-IMS] BoQ Overissuance Justification Submitted: {material_description}`
  - **Body:** Package number, material, overissuance amount, category, submitter, status
  - **When triggered:** Every time a new `BoQOverissuanceJustification` record is created

- **Benefits:**
  - Management can now monitor overissuance justifications in real-time
  - Reduces need for manual follow-ups on pending justifications
  - Audit trail is complete with email evidence

### 2. Updated BoQOverissuanceJustification Model Import
**File:** `Inventory/signals.py`

- Added `BoQOverissuanceJustification` to imports from models
- Ensures signal handler can access the model

### 3. Created M365 Notification Verification Script
**File:** `test_m365_notifications.py` (new)

- **Purpose:** Verify M365 email delivery for all notification paths
- **Test coverage:**
  1. Manual notification creation path
  2. MaterialOrder creation signal
  3. BoQ overissuance justification signal (Phase R new)
  4. M365 credentials verification
  5. Complete notification coverage summary

- **Usage:** Run from Django shell
  ```bash
  python manage.py shell < test_m365_notifications.py
  ```

- **Output:**
  - ✓ indicators for successful paths
  - ⚠ warnings for missing credentials
  - ⊘ skips for tests requiring data that doesn't exist
  - Summary of all wired notification paths

---

## 📋 Complete Notification Coverage Matrix

| Trigger Event | Signal Handler | Recipient Group | Email Sent? | Status |
|---|---|---|---|---|
| MaterialOrder creation (Release type) | `handle_material_order_notifications` | Store Officers, Management | Yes (M365) | ✅ Complete |
| MaterialOrder status change to "Processing" | `handle_material_order_notifications` | Requester + Management | Yes (M365) | ✅ Complete |
| MaterialOrder status change to "Completed" | `handle_material_order_notifications` | Requester + Management | Yes (M365) | ✅ Complete |
| MaterialTransport creation | `handle_transport_notifications` | Management | Yes (M365) | ✅ Complete |
| MaterialTransport status to "In Transit" | `handle_transport_notifications` | Recipient group | Yes (M365) | ✅ Complete |
| MaterialTransport status to "Delivered" | `handle_transport_notifications` | Recipient group | Yes (M365) | ✅ Complete |
| SiteReceipt creation | `handle_site_receipt_notifications` | Management | Yes (M365) | ✅ Complete |
| InventoryItem low stock alert | `handle_low_inventory_notifications` | Management | Yes (M365) | ✅ Complete |
| BillOfQuantity creation | `handle_boq_notifications` | Management | Yes (M365) | ✅ Complete |
| **BoQOverissuanceJustification creation** | **`handle_boq_overissuance_justification_notifications` (NEW)** | **Management** | **Yes (M365)** | **✅ NEW in Phase R** |

---

## 🔍 How M365 Email Delivery Works

### Architecture
1. **Signal fires** → Model instance created/updated
2. **Signal handler calls** `create_notification()` → Creates Notification record
3. **Notification creation triggers** `_trigger_email_notification()` → Prepares email
4. **Email preparation:**
   - Resolves recipient emails from user groups
   - Finds sender with valid M365 token
   - Constructs HTML email body
5. **Microsoft Graph API call** → Sends via `sendMail` endpoint
6. **Result:**
   - 202 response = success (email queued)
   - Error = logged but doesn't crash app

### Failsafes
- If no sender with M365 credentials found → Logged as error, app continues
- If recipient list is empty → Logged as warning, app continues
- If Graph API call fails → Logged as error, app continues
- **No single notification failure crashes the system**

---

## ⏳ Pending User Actions (Staging/Production Verification)

The following steps require the user to test in staging/production:

### 1. Verify M365 Credentials Are Set
- Admin user must have M365 OAuth credentials stored in `accounts.MicrosoftCredentials`
- Check: `/admin/accounts/microsoftcredentials/` should show at least one entry
- If missing: User must go through M365 authentication flow

### 2. Test Each Notification Path
Run the verification script:
```bash
cd /path/to/project
python manage.py shell < test_m365_notifications.py
```

Expected output:
```
✓ Manual notification path: Email sent to test user
✓ MaterialOrder signal: Notification created
✓ BoQ overissuance signal: Notification created
```

### 3. Check Email Inbox
- Should receive test emails in real M365 account
- Subject line: `[MOEN-IMS] <notification title>`
- Body: HTML formatted with Notification title, message, and dashboard link

### 4. Review Django Logs
If emails don't arrive, check logs for:
```
Graph API error for user X: [error_code] error_message
```

Common issues:
- `invalid_grant`: Token expired (user needs to re-authenticate)
- `Mail.Send` permission missing: OAuth scope misconfigured
- `invalid_recipient`: Email address invalid or user deactivated

### 5. Test Trigger Paths Manually
In staging, manually trigger each path:
1. Create a MaterialOrder (Release type) → Should email Store Officers
2. Create a MaterialTransport → Should email Management
3. Create a SiteReceipt → Should email Management
4. Create a BoQOverissuanceJustification → Should email Management
5. Check email inbox for each

---

## 📁 Files Modified

### Code Changes
- **`Inventory/signals.py`**
  - Added import: `BoQOverissuanceJustification`
  - Added new signal handler: `handle_boq_overissuance_justification_notifications`

### New Files
- **`test_m365_notifications.py`**
  - Comprehensive verification script for all notification paths
  - Tests M365 credentials, signal firing, email delivery
  - Runnable from Django shell

---

## 🚀 Definition of Done

- ✅ BoQOverissuanceJustification notification signal added
- ✅ All notification paths documented and verified in code
- ✅ M365 verification script created
- ✅ No broken notification paths
- ⏳ User verification in staging (requires M365 creds + email check)
- ⏳ User verification in production (requires real test)

---

## 🔗 Related Files

- Signal definitions: `Inventory/signals.py` (lines 838-872)
- M365 integration: `accounts/notifications.py`
- Notification model: `Inventory/models/notifications.py`
- Form that triggers: `Inventory/forms/projects.py` → `BoQOverissuanceJustificationForm`
- View that creates: `Inventory/boq_overissuance_views.py` → `BoQOverissuanceJustificationCreateView`

---

## 📝 Checklist for User

To fully verify Phase R in your environment:

- [ ] Check `/admin/accounts/microsoftcredentials/` — at least 1 entry exists
- [ ] Run `python manage.py shell < test_m365_notifications.py`
- [ ] Check email inbox for test notification
- [ ] Create a test MaterialOrder (Release type) → Check email
- [ ] Create a test BoQOverissuanceJustification → Check email
- [ ] Review Django logs for Graph API success messages
- [ ] Mark Phase R as **VERIFIED** when all tests pass

---

## Next Phase

With Phase R complete, the next priority is **Phase U: KPIs & management dashboard** (2 days effort). This blocks Phase V (Ghana map integration).

---

**End of Report**
