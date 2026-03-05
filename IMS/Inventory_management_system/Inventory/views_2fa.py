"""
Two-Factor Authentication Views
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp import login as otp_login
from django_otp.util import random_hex
import qrcode
import io
import pyotp


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
        print(f"DEBUG: Validating 2FA token. Code entered: '{code}'")
        
        # Log the verification result
        is_valid = device.verify_token(code)
        print(f"DEBUG: Token verification result: {is_valid}")
        
        if is_valid:
            # Confirm the device
            device.confirmed = True
            device.save()
            print("DEBUG: Device confirmed successfully.")
            
            # Generate backup codes
            generate_backup_codes(user)
            
            messages.success(request, '2FA has been successfully enabled! Please save your backup codes.')
            return redirect('2fa_backup_codes')
        else:
            print("DEBUG: Invalid code, sending error response.")
            messages.error(request, 'Invalid code. Please try again.')
            return redirect('setup_2fa')
    
    return redirect('setup_2fa')


@login_required
def disable_2fa(request):
    """
    Disable 2FA for the user.
    """
    if request.method == 'POST':
        user = request.user
        
        # Delete all TOTP devices
        TOTPDevice.objects.filter(user=user).delete()
        
        # Delete all static tokens (backup codes)
        StaticDevice.objects.filter(user=user).delete()
        
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
    
    context = {
        'tokens': tokens,
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
        
        messages.success(request, 'New backup codes have been generated.')
        return redirect('2fa_backup_codes')
    
    return redirect('2fa_backup_codes')


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
        code = request.POST.get('code', '').strip()
        user = request.user
        
        # Try TOTP device first
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device and device.verify_token(code):
            otp_login(request, device)
            messages.success(request, 'Successfully verified!')
            return redirect('dashboard')
        
        # Try backup codes
        static_device = StaticDevice.objects.filter(user=user, name='backup').first()
        if static_device:
            for token in static_device.token_set.all():
                if token.token == code:
                    token.delete()  # Backup codes are single-use
                    otp_login(request, static_device)
                    messages.success(request, 'Successfully verified using backup code!')
                    messages.warning(request, 'You have used a backup code. Consider regenerating your backup codes.')
                    return redirect('dashboard')
        
        messages.error(request, 'Invalid code. Please try again.')
    
    return render(request, 'Inventory/2fa_verify.html')


def generate_backup_codes(user):
    """
    Generate backup codes for a user.
    """
    device, created = StaticDevice.objects.get_or_create(
        user=user,
        name='backup'
    )
    
    # Clear existing tokens
    device.token_set.all().delete()
    
    # Generate 10 backup codes
    for _ in range(10):
        token = StaticToken.objects.create(
            device=device,
            token=random_hex(8).upper()
        )



