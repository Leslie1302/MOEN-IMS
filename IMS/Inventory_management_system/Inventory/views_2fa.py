"""
Two-Factor Authentication Views
"""
import hmac
import logging

from django.conf import settings
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp import login as otp_login
from django_otp.util import random_hex
from django_ratelimit.decorators import ratelimit
import qrcode
import io

from Inventory.services.audit import audit

logger = logging.getLogger(__name__)


def _get_client_ip(request):
    """Extract client IP from request, respecting X-Forwarded-For."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _notify_2fa_event(user, title, message):
    """Send an in-app security notification to the user."""
    try:
        from Inventory.models import Notification
        Notification.objects.create(
            notification_type='security_alert',
            title=title,
            message=message,
            recipient_group='All',
            sender=user,
            recipient_user=user,
        )
    except Exception as exc:
        logger.warning("Failed to create 2FA notification for user %s: %s", user.id, exc)


@login_required
def setup_2fa(request):
    """
    View to set up 2FA for a user.
    Generates a QR code for Google Authenticator/Authy/etc.
    """
    user = request.user

    # Check if user already has 2FA enabled
    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if device:
        messages.info(request, '2FA is already enabled for your account.')
        return redirect('profile')

    # Get or create unconfirmed device
    device, created = TOTPDevice.objects.get_or_create(
        user=user,
        name='default',
        defaults={'confirmed': False}
    )

    if not device.key:
        device.key = random_hex(20)
        device.save()

    # Generate OTP URL for QR code
    otpauth_url = device.config_url

    context = {
        'device': device,
        'otpauth_url': otpauth_url,
        'secret_key': device.key,
    }

    return render(request, 'Inventory/2fa_setup.html', context)


@login_required
def setup_2fa_qr(request):
    """
    Generate QR code image for 2FA setup.
    """
    user = request.user
    device = TOTPDevice.objects.filter(user=user, name='default').first()

    if not device:
        return HttpResponse(status=404)

    # Generate OTP URL natively from device
    otpauth_url = device.config_url

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(otpauth_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Save to bytes
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)

    return HttpResponse(img_buffer, content_type='image/png')


@login_required
@ratelimit(key='user', rate=getattr(settings, 'RATELIMIT_2FA_CONFIRM', '5/m'), block=True)
def confirm_2fa(request):
    """
    Confirm 2FA setup by verifying a code from the authenticator app.
    """
    if request.method == 'POST':
        user = request.user
        device = TOTPDevice.objects.filter(user=user, name='default', confirmed=False).first()

        if not device:
            messages.error(request, 'No 2FA device found to confirm.')
            return redirect('setup_2fa')

        code = request.POST.get('code', '').strip()
        logger.debug("Validating 2FA token for user %s", user.id)

        is_valid = device.verify_token(code)
        logger.debug("2FA token verification result for user %s: %s", user.id, is_valid)

        if is_valid:
            # Confirm the device
            device.confirmed = True
            device.save()
            logger.info("2FA device confirmed for user %s", user.id)

            # Generate backup codes
            generate_backup_codes(user)

            audit(
                user=user, target=user, action='2fa.confirmed',
                message='2FA TOTP device confirmed', ip_address=_get_client_ip(request),
            )
            _notify_2fa_event(
                user, '2FA Enabled',
                'Two-factor authentication has been enabled on your account.',
            )

            messages.success(request, '2FA has been successfully enabled! Please save your backup codes.')
            return redirect('2fa_backup_codes')
        else:
            logger.info("Invalid 2FA code submitted for user %s", user.id)
            messages.error(request, 'Invalid code. Please try again.')
            return redirect('setup_2fa')

    return redirect('setup_2fa')


@login_required
def disable_2fa(request):
    """
    Disable 2FA for the user. Requires current password AND a valid TOTP code.
    """
    if request.method == 'POST':
        user = request.user
        password = request.POST.get('password', '')
        code = request.POST.get('code', '').strip()

        if not user.check_password(password):
            messages.error(request, 'Incorrect password. Please try again.')
            return render(request, 'Inventory/2fa_disable.html')

        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if not device or not device.verify_token(code):
            messages.error(request, 'Invalid 2FA code. Please try again.')
            return render(request, 'Inventory/2fa_disable.html')

        # Delete all TOTP devices
        TOTPDevice.objects.filter(user=user).delete()

        # Delete all static tokens (backup codes)
        StaticDevice.objects.filter(user=user).delete()

        audit(
            user=user, target=user, action='2fa.disabled',
            message='2FA disabled — all TOTP devices and backup codes removed',
            ip_address=_get_client_ip(request),
        )
        _notify_2fa_event(
            user, '2FA Disabled',
            'Two-factor authentication has been disabled on your account. '
            'Your account is now less secure.',
        )

        # Flush session so any stolen session cookies become invalid
        request.session.flush()

        messages.success(request, '2FA has been disabled for your account.')
        return redirect('profile')

    return render(request, 'Inventory/2fa_disable.html')


@login_required
def backup_codes(request):
    """
    Display backup codes for the user.
    """
    user = request.user
    device = StaticDevice.objects.filter(user=user, name='backup').first()

    if not device:
        messages.error(request, 'No backup codes found. Please set up 2FA first.')
        return redirect('setup_2fa')

    tokens = device.token_set.all()

    # Build a list of dicts with both raw and formatted codes
    formatted_tokens = [
        {'token': _format_backup_code(t.token), 'raw': t.token}
        for t in tokens
    ]

    context = {
        'tokens': formatted_tokens,
    }

    return render(request, 'Inventory/2fa_backup_codes.html', context)


@login_required
def regenerate_backup_codes(request):
    """
    Regenerate backup codes for the user.
    """
    if request.method == 'POST':
        user = request.user

        # Delete old backup codes
        device = StaticDevice.objects.filter(user=user, name='backup').first()
        if device:
            device.token_set.all().delete()

        # Generate new backup codes
        generate_backup_codes(user)

        audit(
            user=user, target=user, action='2fa.backup_regenerated',
            message='Backup codes regenerated', ip_address=_get_client_ip(request),
        )

        messages.success(request, 'New backup codes have been generated.')
        return redirect('2fa_backup_codes')

    return redirect('2fa_backup_codes')


@ratelimit(key='user', rate=getattr(settings, 'RATELIMIT_2FA_VERIFY', '5/m'), block=True)
def verify_2fa(request):
    """
    Verify 2FA code after initial login.
    """
    if not request.user.is_authenticated:
        return redirect('signin')

    # Check if already verified
    if request.user.is_verified():
        return redirect('dashboard')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip().replace('-', '').upper()
        user = request.user

        # Try TOTP device first
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device and device.verify_token(code):
            otp_login(request, device)

            audit(
                user=user, target=user, action='2fa.verified',
                message='2FA verification successful (TOTP)',
                ip_address=_get_client_ip(request),
            )

            messages.success(request, 'Successfully verified!')
            return redirect('dashboard')

        # Try backup codes (timing-safe comparison)
        static_device = StaticDevice.objects.filter(user=user, name='backup').first()
        if static_device:
            for token in static_device.token_set.all():
                if hmac.compare_digest(token.token, code):
                    token.delete()  # Backup codes are single-use
                    otp_login(request, static_device)

                    audit(
                        user=user, target=user, action='2fa.backup_used',
                        message='2FA verification successful (backup code)',
                        ip_address=_get_client_ip(request),
                    )

                    messages.success(request, 'Successfully verified using backup code!')
                    messages.warning(
                        request,
                        'You have used a backup code. Consider regenerating your backup codes.',
                    )
                    return redirect('dashboard')

        messages.error(request, 'Invalid code. Please try again.')

    return render(request, 'Inventory/2fa_verify.html')


def _format_backup_code(raw_hex):
    """Format a 16-char hex string as XXXX-XXXX-XXXX-XXXX."""
    code = raw_hex.upper()
    return f"{code[0:4]}-{code[4:8]}-{code[8:12]}-{code[12:16]}"


def generate_backup_codes(user):
    """
    Generate backup codes for a user. Codes are stored raw but displayed formatted.
    """
    device, created = StaticDevice.objects.get_or_create(
        user=user,
        name='backup'
    )

    # Clear existing tokens
    device.token_set.all().delete()

    # Generate 10 backup codes
    for _ in range(10):
        StaticToken.objects.create(
            device=device,
            token=random_hex(8).upper()
        )
