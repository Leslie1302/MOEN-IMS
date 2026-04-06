# Production Sign-In Fix — Briefing Document

**Date:** 1 April 2026  
**Issue:** All users unable to sign in via Microsoft 365 on production  
**Error displayed:** `State mismatch. Possible CSRF attack.`  
**Status:** Fix applied — pending deployment & verification

---

## Executive Summary

A configuration mismatch between the application's cookie settings and the production domain prevented the sign-in flow from completing. The app was setting browser cookies for `moen-ims.org`, but the production site runs on `moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net`. Because the domains don't match, the browser silently discarded the cookies, breaking Microsoft sign-in for every user.

**No data was compromised. No actual CSRF attack occurred.** The error message is a false alarm triggered by the lost session.

---

## What Happened (Non-Technical)

1. User clicks "Sign in with Microsoft" → the app creates a security token and stores it in the user's session.
2. User logs in on Microsoft's page and is sent back to the app.
3. The app checks for the security token in the session — **but the session is empty** because the browser never stored/returned the cookie.
4. The app assumes foul play and blocks the login with the CSRF error.

**Why was the session empty?** The app told the browser: *"This cookie belongs to `moen-ims.org`."* But the site is actually `*.azurewebsites.net`. The browser followed standard security rules and refused to store a cookie for a domain that doesn't match.

---

## What Was Fixed

Four changes were made across two files:

| # | File | What Changed | Why |
|---|------|-------------|-----|
| 1 | `settings.py` | Removed hardcoded cookie domain (`.moen-ims.org`) | Browser now correctly scopes cookies to the Azure domain |
| 2 | `settings.py` | Changed cookie `SameSite` policy from `None` to `Lax` | Prevents browsers from blocking the session cookie as a third-party cookie |
| 3 | `settings.py` | Updated default OAuth redirect URI to Azure domain | Ensures Microsoft sends users back to the correct URL |
| 4 | `middleware.py` | Exempted `/auth/callback` from host redirect | Prevents an internal redirect from interfering with the sign-in callback |

---

## Risk Assessment

| Area | Risk Level | Notes |
|------|-----------|-------|
| Security | **None** | All changes follow security best practices. `Lax` cookies are the browser default and recommended setting. |
| Existing sessions | **Low** | Users may need to sign in again after deployment (expected — cookies were broken anyway). |
| Other functionality | **None** | Changes only affect cookie scoping and the OAuth callback path. No business logic was modified. |

---

## Action Required After Deployment

1. **Deploy** the updated code to Azure.
2. **Test sign-in** in an incognito browser window at:  
   `https://moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net`
3. **Verify** in Azure Portal that the App Registration redirect URI matches:  
   `https://moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net/auth/callback/`  
   *(Portal → App registrations → [MOEN-IMS App] → Authentication → Redirect URIs)*

---

## Future Consideration: Custom Domain

If a custom domain (e.g., `www.moen-ims.org`) is configured to point to the Azure app in the future, three environment variables will need to be set:

```
CANONICAL_HOST=www.moen-ims.org
COOKIE_DOMAIN=.moen-ims.org
MS_REDIRECT_URI=https://www.moen-ims.org/auth/callback/
```

The Azure App Registration redirect URI must also be updated to match.

---

## Technical Details (For Developers)

### Files modified

- **`IMS/Inventory_management_system/Inventory_management_system/settings.py`**
  - Line 90: Default `MS_REDIRECT_URI` → `https://moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net/auth/callback/`
  - Lines 111-112: `SESSION_COOKIE_SAMESITE` and `CSRF_COOKIE_SAMESITE` → `'Lax'`
  - Line 141: `CANONICAL_HOST` default → `''` (was `'www.moen-ims.org'`)
  - Line 149: `COOKIE_DOMAIN` default → `''` (was `'.moen-ims.org'`)

- **`IMS/Inventory_management_system/Inventory/middleware.py`**
  - Lines 22-24: Added exemption for `/auth/callback` in `CanonicalHostRedirectMiddleware`

### Root cause in code

```python
# settings.py — These two lines set cookies for the WRONG domain:
_cookie_domain = os.getenv('COOKIE_DOMAIN', '.moen-ims.org')  # ← hardcoded
SESSION_COOKIE_DOMAIN = _cookie_domain                         # ← applied to all sessions

# The browser sees: "Set-Cookie: sessionid=...; Domain=.moen-ims.org"
# But the URL bar shows: moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net
# Browser: "Domain mismatch — cookie rejected."
```
