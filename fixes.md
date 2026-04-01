# Fix: "State mismatch. Possible CSRF attack." on Production Sign-In

**Date:** 2026-04-01  
**Symptom:** Clicking "Sign in with Microsoft" in production always returned `State mismatch. Possible CSRF attack.` — across all browsers and incognito tabs.

---

## Root Cause

The OAuth 2.0 Authorization Code flow stores a random `state` in `request.session["oauth_state"]` during `/auth/login/`, then checks it on `/auth/callback/`. The check was failing because the **session cookie was never sent back to the callback**.

### Primary cause — Cookie domain mismatch

`settings.py` had **two** blocks that hardcoded the cookie domain to `.moen-ims.org`:

- Line ~120: `SESSION_COOKIE_DOMAIN = f".{domain}"` (derived from `CANONICAL_HOST` defaulting to `www.moen-ims.org`)
- Line ~149: `_cookie_domain = os.getenv('COOKIE_DOMAIN', '.moen-ims.org')` → `SESSION_COOKIE_DOMAIN = '.moen-ims.org'`

The production site runs on `moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net`, but cookies were scoped to `.moen-ims.org`. **Browsers refuse to send cookies scoped to a domain that doesn't match the current host.** The session was always empty on the callback, so `oauth_state` was `None`.

### Contributing factors

1. **`SESSION_COOKIE_SAMESITE = 'None'`** — Treated the session cookie as a third-party cookie, which modern browsers block.
2. **`CanonicalHostRedirectMiddleware`** — Could issue a 301 redirect on the callback, potentially dropping the session.
3. **Default `MS_REDIRECT_URI`** — Was `http://localhost:8000/auth/callback/`, wrong for production.

---

## All Changes Made

### 1. `settings.py` — Removed hardcoded `.moen-ims.org` cookie domain

```diff
- CANONICAL_HOST = os.getenv('CANONICAL_HOST', ('' if DEBUG else 'www.moen-ims.org')).strip()
+ CANONICAL_HOST = os.getenv('CANONICAL_HOST', '').strip()
```

```diff
- _cookie_domain = os.getenv('COOKIE_DOMAIN', '.moen-ims.org').strip()
+ _cookie_domain = os.getenv('COOKIE_DOMAIN', '').strip()
```

With no cookie domain set, the browser scopes cookies to the exact host (`*.azurewebsites.net`), which is correct.

### 2. `settings.py` — Changed `SameSite` from `None` to `Lax`

```diff
- SESSION_COOKIE_SAMESITE = 'None'
- CSRF_COOKIE_SAMESITE = 'None'
+ SESSION_COOKIE_SAMESITE = 'Lax'
+ CSRF_COOKIE_SAMESITE = 'Lax'
```

### 3. `settings.py` — Updated default `MS_REDIRECT_URI`

```diff
- "REDIRECT_URI": os.environ.get("MS_REDIRECT_URI", "http://localhost:8000/auth/callback/"),
+ "REDIRECT_URI": os.environ.get("MS_REDIRECT_URI", "https://moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net/auth/callback/"),
```

### 4. `middleware.py` — Exempted `/auth/callback` from canonical host redirect

```diff
+ if request.path.startswith('/auth/callback'):
+     return None
```

---

## Files Modified

| File | Change |
|------|--------|
| `Inventory_management_system/settings.py` | Cookie domain defaults cleared; `SameSite` → `Lax`; redirect URI → Azure domain |
| `Inventory/middleware.py` | Exempt `/auth/callback` from canonical host redirect |

---

## Azure App Registration Reminder

Ensure the **Redirect URI** in Azure AD matches exactly:

```
https://moen-ims-fegfgqf3c5frejfv.uksouth-01.azurewebsites.net/auth/callback/
```

**Azure Portal → App registrations → [Your App] → Authentication → Redirect URIs**

---

## Future: Custom Domain

If you later add a custom domain (e.g., `www.moen-ims.org`) pointing to the Azure app, set these environment variables:

```
CANONICAL_HOST=www.moen-ims.org
COOKIE_DOMAIN=.moen-ims.org
MS_REDIRECT_URI=https://www.moen-ims.org/auth/callback/
```

And update the Azure App Registration redirect URI accordingly.

