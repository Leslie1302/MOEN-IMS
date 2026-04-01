# Fix: "State mismatch. Possible CSRF attack." on Production Sign-In

**Date:** 2026-04-01  
**Symptom:** Clicking "Sign in with Microsoft" in production always returned `State mismatch. Possible CSRF attack.` — across all browsers and incognito tabs.

---

## Root Cause

The OAuth 2.0 Authorization Code flow relies on a `state` parameter to prevent CSRF:

1. `/auth/login/` generates a random `state`, stores it in `request.session["oauth_state"]`, and redirects to Microsoft.
2. Microsoft redirects back to `/auth/callback/?code=...&state=...`.
3. The callback view compares `state` from the URL with `request.session["oauth_state"]`.

**The session cookie was being lost between step 1 and step 3** due to three compounding issues:

### Issue 1 — `SESSION_COOKIE_SAMESITE = 'None'`

Setting `SameSite=None` tells browsers to treat the session cookie as a **third-party cookie**. Modern browsers (Chrome 80+, Firefox, Edge) increasingly restrict or block third-party cookies entirely. When Microsoft redirected back to the app, the browser did not send the session cookie, so `request.session["oauth_state"]` was `None`.

### Issue 2 — `CanonicalHostRedirectMiddleware` redirecting the callback

The `CanonicalHostRedirectMiddleware` runs **before** the session middleware processes the request. If Microsoft's redirect URI pointed to a non-canonical host (e.g., the Azure `*.azurewebsites.net` domain instead of `www.moen-ims.org`), the middleware issued a 301 redirect to the canonical host. This extra redirect could strip the session cookie (different domain) or cause the authorisation code to be consumed/expired.

### Issue 3 — Mismatched `MS_REDIRECT_URI` default

The default `MS_REDIRECT_URI` in `settings.py` was `http://localhost:8000/auth/callback/`, which is incorrect for production. If the environment variable wasn't set, the MSAL library would tell Microsoft to redirect to localhost — which obviously fails.

---

## Changes Made

### 1. `settings.py` — Changed `SameSite` from `None` to `Lax`

```diff
- SESSION_COOKIE_SAMESITE = 'None'  # or 'None' if you need cross-site cookies
- CSRF_COOKIE_SAMESITE = 'None'     # or 'None' if you need cross-site cookies
+ SESSION_COOKIE_SAMESITE = 'Lax'
+ CSRF_COOKIE_SAMESITE = 'Lax'
```

`Lax` is the correct setting for same-site OAuth flows. It sends the cookie on top-level navigations (like the Microsoft redirect back to your app) while still protecting against cross-site POST attacks. `None` should only be used for cross-site iframe embedding scenarios.

### 2. `settings.py` — Updated default `MS_REDIRECT_URI`

```diff
- "REDIRECT_URI": os.environ.get("MS_REDIRECT_URI", "http://localhost:8000/auth/callback/"),
+ "REDIRECT_URI": os.environ.get("MS_REDIRECT_URI", "https://moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net/auth/callback/"),
```

The default now points to the actual Azure production domain. This ensures MSAL tells Microsoft to redirect to the correct host even if the `MS_REDIRECT_URI` environment variable isn't explicitly set.

### 3. `middleware.py` — Exempted `/auth/callback` from canonical host redirect

```diff
+ # Allow OAuth callback without redirect so the session cookie (containing
+ # oauth_state) is preserved from the original login request.
+ if request.path.startswith('/auth/callback'):
+     return None
```

This prevents the `CanonicalHostRedirectMiddleware` from issuing a 301 redirect on the OAuth callback URL. The session cookie set during `/auth/login/` is preserved and the `state` parameter can be validated correctly.

---

## Files Modified

| File | Change |
|------|--------|
| `IMS/Inventory_management_system/Inventory_management_system/settings.py` | `SameSite` → `Lax`; default redirect URI → Azure domain |
| `IMS/Inventory_management_system/Inventory/middleware.py` | Exempt `/auth/callback` from canonical host redirect |

---

## Azure App Registration Reminder

Make sure the **Redirect URI** registered in your Azure AD App Registration matches exactly:

```
https://moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net/auth/callback/
```

You can verify this at:  
**Azure Portal → App registrations → [Your App] → Authentication → Redirect URIs**

---

## How to Verify the Fix

1. Deploy the updated code to Azure.
2. Open an incognito/private browser window.
3. Navigate to the production URL and click "Sign in with Microsoft".
4. You should be redirected to Microsoft login, and after authentication, redirected back to the app dashboard without the state mismatch error.
