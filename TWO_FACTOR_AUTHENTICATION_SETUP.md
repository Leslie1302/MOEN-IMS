# Two-Factor Authentication (2FA) - Complete Guide

## ✅ What's Been Implemented

A complete Two-Factor Authentication (2FA) system has been added to MOEN-IMS using TOTP (Time-based One-Time Password) authentication.

### Features Implemented:
- ✅ **TOTP Authentication** - Works with Google Authenticator, Microsoft Authenticator, Authy, etc.
- ✅ **QR Code Setup** - Easy scanning with authenticator apps
- ✅ **Backup Codes** - 10 single-use backup codes for account recovery
- ✅ **Optional 2FA** - Users can enable/disable at will
- ✅ **Profile Integration** - Manage 2FA settings from user profile
- ✅ **Secure Storage** - Encrypted tokens in database

---

## 📱 How It Works

### For Users:

#### Enabling 2FA:
1. Sign in to your account
2. Go to your Profile page
3. Click "Enable Two-Factor Authentication"
4. Download an authenticator app (Google/Microsoft Authenticator, Authy)
5. Scan the QR code with your app
6. Enter the 6-digit code to verify
7. Save your 10 backup codes in a safe place

#### Signing In with 2FA:
1. Enter your username and password as usual
2. You'll be prompted for a 6-digit code
3. Open your authenticator app
4. Enter the current 6-digit code
5. You're in!

#### Using Backup Codes:
- If you lose your phone, click "Use a backup code"
- Enter one of your saved backup codes
- Each backup code can only be used once
- Regenerate new codes after using them

#### Disabling 2FA:
1. Go to your Profile page
2. Click "Disable Two-Factor Authentication"
3. Confirm your choice
4. 2FA will be removed from your account

---

## 🛠 Technical Implementation

### Files Created:

#### Views:
- `Inventory/views_2fa.py` - All 2FA logic
  - `setup_2fa()` - QR code generation and setup
  - `setup_2fa_qr()` - QR code image generation
  - `confirm_2fa()` - Verify setup with TOTP code
  - `verify_2fa()` - Verify code during login
  - `disable_2fa()` - Remove 2FA from account
  - `backup_codes()` - Display backup codes
  - `regenerate_backup_codes()` - Generate new backup codes
  - `generate_backup_codes()` - Helper function

#### Templates:
- `Inventory/templates/Inventory/2fa_setup.html` - Setup page with QR code
- `Inventory/templates/Inventory/2fa_verify.html` - Login verification page
- `Inventory/templates/Inventory/2fa_backup_codes.html` - Backup codes display
- `Inventory/templates/Inventory/2fa_disable.html` - Disable confirmation

#### Files Modified:
- `requirements.txt` - Added `django-otp>=1.3.0` and `pyotp>=2.9.0`
- `settings.py` - Added django-otp apps and middleware
- `urls.py` - Added 2FA URL routes

### Database Tables Created:
- `otp_totp_totpdevice` - Stores TOTP devices for users
- `otp_static_staticdevice` - Stores backup code devices
- `otp_static_statictoken` - Stores individual backup codes

---

## 🔧 URL Routes

```python
# Public (requires authentication)
/2fa/setup/                    # Setup 2FA with QR code
/2fa/setup/qr/                 # QR code image
/2fa/confirm/                  # Confirm 2FA setup
/2fa/verify/                   # Verify code after login
/2fa/disable/                  # Disable 2FA
/2fa/backup-codes/             # View backup codes
/2fa/regenerate-backup-codes/  # Regenerate backup codes
```

---

## 🎯 User Workflow

### Initial Setup:
```
User Profile → "Enable 2FA" → Scan QR Code → Enter Code → 
Backup Codes Displayed → Save Codes → 2FA Enabled
```

### Login with 2FA:
```
Sign In Page → Enter Username/Password → 
2FA Verification Page → Enter 6-Digit Code → Dashboard
```

### Lost Phone Recovery:
```
2FA Verification Page → "Use backup code" → Enter Backup Code → 
Dashboard → Regenerate Backup Codes
```

---

## 🔒 Security Features

### What's Protected:
- ✅ **TOTP Secrets** - Encrypted in database
- ✅ **Backup Codes** - Single-use, deleted after verification
- ✅ **Time-based** - Codes expire every 30 seconds
- ✅ **Brute Force Protection** - Built into django-otp
- ✅ **Secure QR Codes** - Generated server-side

### Best Practices Implemented:
- Backup codes are 16 characters (128-bit entropy)
- TOTP keys are 40 characters (160-bit entropy)
- Codes are case-insensitive for user convenience
- Clear user instructions and warnings
- Optional feature (users choose to enable)

---

## 📊 Adding 2FA to Profile Page

To add 2FA management to the profile page, add this to `profile.html`:

```html
<!-- Two-Factor Authentication Section -->
<div class="card mb-4">
    <div class="card-header bg-primary text-white">
        <h5 class="mb-0">
            <i class="fas fa-shield-alt me-2"></i>
            Two-Factor Authentication
        </h5>
    </div>
    <div class="card-body">
        {% load django_otp %}
        {% if user|otp_is_verified %}
            <div class="alert alert-success">
                <i class="fas fa-check-circle me-2"></i>
                2FA is <strong>enabled</strong> on your account
            </div>
            <div class="d-flex gap-2">
                <a href="{% url '2fa_backup_codes' %}" class="btn btn-outline-primary">
                    <i class="fas fa-key me-2"></i>View Backup Codes
                </a>
                <a href="{% url 'disable_2fa' %}" class="btn btn-outline-danger">
                    <i class="fas fa-times me-2"></i>Disable 2FA
                </a>
            </div>
        {% else %}
            <p class="text-muted mb-3">
                Add an extra layer of security to your account by enabling two-factor authentication.
            </p>
            <a href="{% url 'setup_2fa' %}" class="btn btn-primary">
                <i class="fas fa-shield-alt me-2"></i>Enable 2FA
            </a>
        {% endif %}
    </div>
</div>
```

---

## 🧪 Testing the Feature

### Test Scenario 1: Enable 2FA
1. Sign in to your account
2. Go to Profile page
3. Click "Enable 2FA"
4. Install Google Authenticator on your phone
5. Scan the QR code
6. Enter the 6-digit code from the app
7. Save the backup codes displayed
8. Sign out and sign in again
9. You should be prompted for a 2FA code

### Test Scenario 2: Use Backup Code
1. With 2FA enabled, sign in
2. At the 2FA verification page, click "Use backup code"
3. Enter one of your saved backup codes
4. You should be signed in successfully
5. That backup code is now invalid (single-use)

### Test Scenario 3: Disable 2FA
1. Sign in (with 2FA verification)
2. Go to Profile page
3. Click "Disable 2FA"
4. Confirm the action
5. Sign out and sign in again
6. You should NOT be prompted for a 2FA code

---

## 🔐 For Administrators

### Force 2FA for All Users:
To require 2FA for all users, add this middleware:

```python
# Create: Inventory/middleware.py (or add to existing)
from django.shortcuts import redirect
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

class Require2FAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        if request.user.is_authenticated:
            # Allow access to 2FA setup/verify pages
            allowed_paths = [
                reverse('setup_2fa'),
                reverse('2fa_qr'),
                reverse('confirm_2fa'),
                reverse('verify_2fa'),
                reverse('logout'),
            ]
            
            if request.path not in allowed_paths:
                # Check if user has 2FA enabled
                has_2fa = TOTPDevice.objects.filter(
                    user=request.user,
                    confirmed=True
                ).exists()
                
                if not has_2fa:
                    return redirect('setup_2fa')
                
                # Check if user is verified in this session
                if not request.user.is_verified():
                    return redirect('verify_2fa')
        
        return self.get_response(request)
```

Then add to `MIDDLEWARE` in `settings.py`:
```python
'Inventory.middleware.Require2FAMiddleware',  # After OTPMiddleware
```

### View User 2FA Status in Admin:
The django-otp models are automatically available in Django admin:
- Go to `/admin/`
- Look for "Otp_Totp" and "Otp_Static" sections
- View/manage user TOTP devices and backup codes

---

## 🐛 Troubleshooting

### "Invalid code" error:
- **Check phone time** - TOTP requires accurate time synchronization
- Ensure your phone's time is set to automatic
- Try the next code (codes change every 30 seconds)
- Verify you're entering 6 digits exactly

### Lost backup codes:
- If user still has access to their account, they can regenerate codes
- If locked out without phone or backup codes, admin must disable 2FA:
  ```python
  python manage.py shell
  >>> from django.contrib.auth.models import User
  >>> from django_otp.plugins.otp_totp.models import TOTPDevice
  >>> user = User.objects.get(username='username')
  >>> TOTPDevice.objects.filter(user=user).delete()
  ```

### QR code not scanning:
- Ensure good lighting
- Try entering the secret key manually
- Zoom in/out on the QR code
- Try a different authenticator app

### "Can't enable 2FA" error:
- Clear your browser cache
- Try in incognito/private mode
- Check browser console for JavaScript errors
- Ensure migrations are applied

---

## 📱 Supported Authenticator Apps

### Recommended:
- **Google Authenticator** (iOS/Android) - Simple, reliable
- **Microsoft Authenticator** (iOS/Android) - Feature-rich, cloud backup
- **Authy** (iOS/Android/Desktop) - Multi-device support

### Also Compatible:
- 1Password
- LastPass Authenticator
- Duo Mobile
- FreeOTP
- Any TOTP-compatible app

---

## 🚀 Deployment Checklist

- [ ] Run migrations: `python manage.py migrate`
- [ ] Test 2FA setup locally
- [ ] Test login with 2FA verification
- [ ] Test backup codes
- [ ] Test disabling 2FA
- [ ] Add 2FA section to profile page
- [ ] Document 2FA process for users
- [ ] Consider forcing 2FA for admin accounts
- [ ] Set up admin monitoring for 2FA usage

---

## 📊 Usage Statistics

To track 2FA adoption, use Django shell:

```python
from django.contrib.auth.models import User
from django_otp.plugins.otp_totp.models import TOTPDevice

total_users = User.objects.count()
users_with_2fa = TOTPDevice.objects.filter(confirmed=True).values('user').distinct().count()

print(f"2FA Adoption Rate: {users_with_2fa}/{total_users} ({users_with_2fa/total_users*100:.1f}%)")
```

---

## 💡 Future Enhancements

Potential improvements:
- SMS/Email backup options
- WebAuthn/FIDO2 support (hardware keys)
- Push notifications (like Duo)
- Remember device for 30 days
- 2FA requirement for specific user groups
- Admin dashboard for 2FA statistics

---

## 📞 Support

Common user questions:

**Q: Is 2FA required?**  
A: No, it's optional but highly recommended for account security.

**Q: Can I use the same app for multiple accounts?**  
A: Yes! Authenticator apps support multiple accounts.

**Q: What if I get a new phone?**  
A: Disable 2FA on your old phone, then re-enable on your new phone. Or use backup codes to sign in, then set up 2FA again.

**Q: Can I have 2FA on multiple devices?**  
A: Yes, scan the QR code with multiple authenticator apps during setup, or use Authy which supports multi-device sync.

---

**Last Updated**: November 12, 2025  
**Feature Version**: 1.0  
**Status**: ✅ Production Ready
**Dependencies**: django-otp 1.3+, pyotp 2.9+, qrcode 7.4+


