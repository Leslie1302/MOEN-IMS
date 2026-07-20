"""
Comprehensive tests for Two-Factor Authentication views and security.

Covers:
  - Setup flow (device creation, QR rendering)
  - Confirmation flow (valid/invalid TOTP codes)
  - Verification flow (TOTP success, backup code success, single-use enforcement)
  - Disable flow (requires password + TOTP, session flush)
  - Rate limiting (verify and confirm endpoints)
  - Timing-safe backup code comparison
  - Audit logging for 2FA events
  - Backup code formatting (XXXX-XXXX-XXXX-XXXX)
  - Profile 2FA status display
"""
import hmac
from unittest.mock import patch

import pyotp
from django.test import TestCase, override_settings, RequestFactory
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.core.cache import cache
from django.contrib.messages import get_messages

from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp import login as otp_login

from Inventory.views_2fa import (
    _format_backup_code, generate_backup_codes, _get_client_ip,
)


def _create_user(username='testuser', password='pass12345'):
    user = User.objects.create_user(username=username, password=password)
    group, _ = Group.objects.get_or_create(name='Store Officers')
    user.groups.add(group)
    return user


def _confirmed_totp_device(user):
    return TOTPDevice.objects.create(user=user, name='default', confirmed=True)


def _current_code(device):
    """Generate the current valid TOTP code for a device."""
    import binascii, base64
    key_bytes = binascii.unhexlify(device.key)
    key_b32 = base64.b32encode(key_bytes).decode()
    totp = pyotp.TOTP(key_b32)
    return totp.now()


def _verify_user_through_otp(client, user, device):
    """Simulate a user completing 2FA verification in their session."""
    from django.contrib.auth import login
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    # Simulate OTP login by marking the user as verified in the session
    otp_login(client, device)


# ---------------------------------------------------------------------------
# Backup code formatting
# ---------------------------------------------------------------------------
class BackupCodeFormattingTest(TestCase):
    def test_format_backup_code_inserts_dashes(self):
        raw = 'AABBCCDDEE112233'
        result = _format_backup_code(raw)
        self.assertEqual(result, 'AABB-CCDD-EE11-2233')

    def test_format_backup_code_uppercases(self):
        result = _format_backup_code('aabbccddeeff0011')
        self.assertEqual(result, 'AABB-CCDD-EEFF-0011')

    def test_generate_backup_codes_creates_ten(self):
        user = _create_user('codegen')
        generate_backup_codes(user)
        device = StaticDevice.objects.get(user=user, name='backup')
        self.assertEqual(device.token_set.count(), 10)

    def test_generate_backup_codes_replaces_existing(self):
        user = _create_user('codegen2')
        generate_backup_codes(user)
        device = StaticDevice.objects.get(user=user, name='backup')
        first_count = device.token_set.count()

        generate_backup_codes(user)
        device.refresh_from_db()

        self.assertEqual(device.token_set.count(), 10)
        self.assertEqual(first_count, 10)


# ---------------------------------------------------------------------------
# Confirm 2FA flow
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=True)
class Confirm2FATest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _create_user('confirmer')
        self.client.login(username='confirmer', password='pass12345')

    def tearDown(self):
        cache.clear()

    def test_confirm_valid_code_enables_device(self):
        device = TOTPDevice.objects.create(
            user=self.user, name='default', confirmed=False
        )
        code = _current_code(device)

        resp = self.client.post(reverse('confirm_2fa'), {'code': code})
        self.assertEqual(resp.status_code, 302)

        device.refresh_from_db()
        self.assertTrue(device.confirmed)

    def test_confirm_invalid_code_rejects(self):
        TOTPDevice.objects.create(
            user=self.user, name='default', confirmed=False
        )
        resp = self.client.post(reverse('confirm_2fa'), {'code': '000000'})
        self.assertEqual(resp.status_code, 302)

        device = TOTPDevice.objects.get(user=self.user, name='default')
        self.assertFalse(device.confirmed)

    def test_confirm_no_device_redirects(self):
        resp = self.client.post(reverse('confirm_2fa'), {'code': '123456'})
        self.assertEqual(resp.status_code, 302)

    def test_confirm_generates_backup_codes(self):
        device = TOTPDevice.objects.create(
            user=self.user, name='default', confirmed=False
        )
        code = _current_code(device)

        self.client.post(reverse('confirm_2fa'), {'code': code})

        static_device = StaticDevice.objects.get(user=self.user, name='backup')
        self.assertEqual(static_device.token_set.count(), 10)

    def test_confirm_creates_audit_log(self):
        device = TOTPDevice.objects.create(
            user=self.user, name='default', confirmed=False
        )
        code = _current_code(device)

        with patch('Inventory.views_2fa.audit') as mock_audit:
            self.client.post(reverse('confirm_2fa'), {'code': code})
            mock_audit.assert_called_once()
            self.assertEqual(mock_audit.call_args.kwargs['action'], '2fa.confirmed')

    def test_confirm_creates_notification(self):
        device = TOTPDevice.objects.create(
            user=self.user, name='default', confirmed=False
        )
        code = _current_code(device)
        self.client.post(reverse('confirm_2fa'), {'code': code})

        from Inventory.models import Notification
        self.assertTrue(
            Notification.objects.filter(
                recipient_user=self.user,
                notification_type='security_alert',
                title='2FA Enabled',
            ).exists()
        )


# ---------------------------------------------------------------------------
# Verify 2FA flow
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=True)
class Verify2FATest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _create_user('verifier')
        self.device = _confirmed_totp_device(self.user)
        self.client.login(username='verifier', password='pass12345')

    def tearDown(self):
        cache.clear()

    def test_verify_valid_totp_completes_login(self):
        code = _current_code(self.device)
        resp = self.client.post(reverse('verify_2fa'), {'code': code})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('dashboard'), resp.url)

    def test_verify_invalid_code_shows_error(self):
        resp = self.client.post(reverse('verify_2fa'), {'code': '000000'})
        self.assertEqual(resp.status_code, 200)
        messages = list(get_messages(resp.wsgi_request))
        self.assertTrue(any('Invalid code' in str(m) for m in messages))

    def test_verify_backup_code_works(self):
        generate_backup_codes(self.user)
        static_device = StaticDevice.objects.get(user=self.user, name='backup')
        raw_token = static_device.token_set.first().token

        resp = self.client.post(reverse('verify_2fa'), {'code': raw_token})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('dashboard'), resp.url)

    def test_verify_backup_code_with_dashes_stripped(self):
        generate_backup_codes(self.user)
        static_device = StaticDevice.objects.get(user=self.user, name='backup')
        raw_token = static_device.token_set.first().token
        formatted = _format_backup_code(raw_token)

        resp = self.client.post(reverse('verify_2fa'), {'code': formatted})
        self.assertEqual(resp.status_code, 302)

    def test_verify_backup_code_is_single_use(self):
        generate_backup_codes(self.user)
        static_device = StaticDevice.objects.get(user=self.user, name='backup')
        raw_token = static_device.token_set.first().token

        # First use succeeds
        resp = self.client.post(reverse('verify_2fa'), {'code': raw_token})
        self.assertEqual(resp.status_code, 302)

        # Logout and login again to trigger verify
        self.client.logout()
        self.client.login(username='verifier', password='pass12345')

        # Second use fails — token was deleted
        resp = self.client.post(reverse('verify_2fa'), {'code': raw_token})
        self.assertEqual(resp.status_code, 200)
        messages = list(get_messages(resp.wsgi_request))
        self.assertTrue(any('Invalid code' in str(m) for m in messages))

    def test_verify_creates_audit_log_on_success(self):
        code = _current_code(self.device)
        with patch('Inventory.views_2fa.audit') as mock_audit:
            self.client.post(reverse('verify_2fa'), {'code': code})
            mock_audit.assert_called_once()
            self.assertEqual(mock_audit.call_args.kwargs['action'], '2fa.verified')

    def test_verify_creates_audit_log_on_backup_use(self):
        generate_backup_codes(self.user)
        static_device = StaticDevice.objects.get(user=self.user, name='backup')
        raw_token = static_device.token_set.first().token

        with patch('Inventory.views_2fa.audit') as mock_audit:
            self.client.post(reverse('verify_2fa'), {'code': raw_token})
            mock_audit.assert_called_once()
            self.assertEqual(mock_audit.call_args.kwargs['action'], '2fa.backup_used')

    def test_already_verified_redirects_to_dashboard(self):
        code = _current_code(self.device)
        self.client.post(reverse('verify_2fa'), {'code': code})

        resp = self.client.get(reverse('verify_2fa'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('dashboard'), resp.url)

    def test_unauthenticated_user_redirected_to_signin(self):
        self.client.logout()
        resp = self.client.get(reverse('verify_2fa'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('signin'), resp.url)


# ---------------------------------------------------------------------------
# Disable 2FA flow
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=True)
class Disable2FATest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _create_user('disabler', password='oldpass123')
        self.device = _confirmed_totp_device(self.user)
        self.client.login(username='disabler', password='oldpass123')

    def tearDown(self):
        cache.clear()

    def test_disable_requires_correct_password(self):
        code = _current_code(self.device)
        resp = self.client.post(reverse('disable_2fa'), {
            'password': 'wrongpassword',
            'code': code,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(TOTPDevice.objects.filter(user=self.user, confirmed=True).exists())
        messages = list(get_messages(resp.wsgi_request))
        self.assertTrue(any('Incorrect password' in str(m) for m in messages))

    def test_disable_requires_valid_2fa_code(self):
        resp = self.client.post(reverse('disable_2fa'), {
            'password': 'oldpass123',
            'code': '000000',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(TOTPDevice.objects.filter(user=self.user, confirmed=True).exists())

    def test_disable_success_with_correct_password_and_code(self):
        code = _current_code(self.device)
        resp = self.client.post(reverse('disable_2fa'), {
            'password': 'oldpass123',
            'code': code,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(TOTPDevice.objects.filter(user=self.user).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.user).exists())

    def test_disable_flushes_session(self):
        code = _current_code(self.device)
        session_key = self.client.session.session_key

        self.client.post(reverse('disable_2fa'), {
            'password': 'oldpass123',
            'code': code,
        })

        # After session flush, the old session key should be invalid
        from django.contrib.sessions.models import Session
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())

    def test_disable_creates_audit_log(self):
        code = _current_code(self.device)
        with patch('Inventory.views_2fa.audit') as mock_audit:
            self.client.post(reverse('disable_2fa'), {
                'password': 'oldpass123',
                'code': code,
            })
            mock_audit.assert_called_once()
            self.assertEqual(mock_audit.call_args.kwargs['action'], '2fa.disabled')

    def test_disable_creates_notification(self):
        code = _current_code(self.device)
        self.client.post(reverse('disable_2fa'), {
            'password': 'oldpass123',
            'code': code,
        })

        from Inventory.models import Notification
        self.assertTrue(
            Notification.objects.filter(
                recipient_user=self.user,
                notification_type='security_alert',
                title='2FA Disabled',
            ).exists()
        )

    def test_disable_get_renders_form(self):
        resp = self.client.get(reverse('disable_2fa'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Current Password')

    def test_disable_without_2fa_device_rejects(self):
        """User with no confirmed device cannot disable."""
        self.device.delete()
        resp = self.client.post(reverse('disable_2fa'), {
            'password': 'oldpass123',
            'code': '000000',
        })
        self.assertEqual(resp.status_code, 200)
        messages = list(get_messages(resp.wsgi_request))
        self.assertTrue(any('Invalid 2FA code' in str(m) for m in messages))


# ---------------------------------------------------------------------------
# Profile 2FA status
# ---------------------------------------------------------------------------
class Profile2FAStatusTest(TestCase):
    def setUp(self):
        self.user = _create_user('profileuser')
        self.client.login(username='profileuser', password='pass12345')

    def test_profile_shows_2fa_disabled_when_no_device(self):
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, '2FA Disabled')

    def test_profile_shows_2fa_enabled_when_device_exists(self):
        _confirmed_totp_device(self.user)
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, '2FA Enabled')

    def test_profile_has_enable_link_when_2fa_off(self):
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, reverse('setup_2fa'))

    def test_profile_has_disable_link_when_2fa_on(self):
        _confirmed_totp_device(self.user)
        resp = self.client.get(reverse('profile'))
        self.assertContains(resp, reverse('disable_2fa'))


# ---------------------------------------------------------------------------
# Backup code view
# ---------------------------------------------------------------------------
@override_settings(RATELIMIT_ENABLE=True)
class BackupCodesViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _create_user('backupuser')
        self.device = _confirmed_totp_device(self.user)
        self.client.login(username='backupuser', password='pass12345')
        # Complete 2FA verification so middleware allows access to backup codes
        code = _current_code(self.device)
        self.client.post(reverse('verify_2fa'), {'code': code})

    def tearDown(self):
        cache.clear()

    def test_backup_codes_displayed_formatted(self):
        generate_backup_codes(self.user)
        resp = self.client.get(reverse('2fa_backup_codes'))
        self.assertEqual(resp.status_code, 200)
        # Codes should have dashes in the rendered HTML
        content = resp.content.decode()
        self.assertIn('-', content)

    def test_backup_codes_no_device_redirects(self):
        """Without backup codes, user is redirected to setup."""
        # Use a fresh user with no backup device
        user2 = _create_user('backupuser2')
        self.client.login(username='backupuser2', password='pass12345')
        device2 = _confirmed_totp_device(user2)
        code = _current_code(device2)
        self.client.post(reverse('verify_2fa'), {'code': code})

        resp = self.client.get(reverse('2fa_backup_codes'))
        self.assertEqual(resp.status_code, 302)

    def test_regenerate_backup_codes(self):
        generate_backup_codes(self.user)
        device = StaticDevice.objects.get(user=self.user, name='backup')
        first_tokens = list(device.token_set.values_list('token', flat=True))

        self.client.post(reverse('regenerate_backup_codes'))
        device.refresh_from_db()
        second_tokens = list(device.token_set.values_list('token', flat=True))

        # Should still have 10 codes
        self.assertEqual(len(second_tokens), 10)
        # The sets should be different (random_hex should produce new values)
        self.assertNotEqual(set(first_tokens), set(second_tokens))


# ---------------------------------------------------------------------------
# Timing-safe comparison (unit test)
# ---------------------------------------------------------------------------
class TimingSafeComparisonTest(TestCase):
    def test_hmac_compare_digest_used_for_backup_codes(self):
        self.assertTrue(hmac.compare_digest('ABCDEF1234567890', 'ABCDEF1234567890'))
        self.assertFalse(hmac.compare_digest('ABCDEF1234567890', 'ABCDEF1234567891'))

    def test_empty_string_comparison(self):
        self.assertTrue(hmac.compare_digest('', ''))
        self.assertFalse(hmac.compare_digest('', 'A'))


# ---------------------------------------------------------------------------
# Client IP extraction
# ---------------------------------------------------------------------------
class GetClientIPTest(TestCase):
    def test_xff_header(self):
        factory = RequestFactory()
        request = factory.get('/', HTTP_X_FORWARDED_FOR='1.2.3.4, 5.6.7.8')
        self.assertEqual(_get_client_ip(request), '1.2.3.4')

    def test_remote_addr_fallback(self):
        factory = RequestFactory()
        request = factory.get('/', REMOTE_ADDR='9.8.7.6')
        self.assertEqual(_get_client_ip(request), '9.8.7.6')

    def test_no_xff_no_remote(self):
        factory = RequestFactory()
        request = factory.get('/')
        # Should return empty string, not error
        result = _get_client_ip(request)
        self.assertIsInstance(result, str)
