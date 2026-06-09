"""
Tests for UserRoleMiddleware — the central default-deny auth gate.

Authentication in this app is enforced here, not by per-view @login_required.
Every protected view is safe only because this middleware's process_view
redirects unauthenticated/unauthorised requests. That makes the allowlist
and branch logic security-critical and, until now, untested: a stray entry
added to `allowed_urls` would silently expose a view with no test to catch it.

Most cases unit-test process_view directly via RequestFactory (fast, no
template/view-resolution coupling). The 2FA-enforcement branch is exercised
through the test client so django_otp's OTPMiddleware is in the stack.
"""
from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User, Group, AnonymousUser
from django.http import HttpResponse
from django.urls import reverse
from django.conf import settings

from Inventory.middleware import UserRoleMiddleware


def _dummy_view(request):
    return HttpResponse("ok")


class UserRoleMiddlewareUnitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.mw = UserRoleMiddleware(get_response=lambda r: HttpResponse())

    def _process(self, path, user):
        request = self.factory.get(path)
        request.user = user
        # OTPMiddleware normally attaches is_verified(); for authenticated
        # users in these unit tests there is no 2FA device, so the branch
        # that calls it is skipped. Provide a stub defensively so an
        # unexpected device can't turn this into an AttributeError.
        if not isinstance(user, AnonymousUser) and not hasattr(user, "is_verified"):
            user.is_verified = lambda: True
        return self.mw.process_view(request, _dummy_view, (), {})

    # --- anonymous ---------------------------------------------------------

    def test_anonymous_on_protected_path_redirected_to_login(self):
        resp = self._process("/protected/area/", AnonymousUser())
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(settings.LOGIN_URL, resp.url)
        self.assertIn("/protected/area/", resp.url)  # ?next= preserved

    def test_allowlisted_paths_open_to_anonymous(self):
        for path in ["/signin/", "/help/", "/auth/callback/", "/.well-known/acme/"]:
            with self.subTest(path=path):
                self.assertIsNone(
                    self._process(path, AnonymousUser()),
                    f"{path} should bypass the auth gate",
                )

    def test_root_is_public(self):
        self.assertIsNone(self._process("/", AnonymousUser()))

    def test_admin_is_skipped(self):
        # Admin has its own auth; middleware must not interfere.
        self.assertIsNone(self._process("/admin/", AnonymousUser()))

    # --- authenticated -----------------------------------------------------

    def test_user_without_groups_redirected_to_awaiting_authorization(self):
        user = User.objects.create_user("nogroup", password="pass12345")
        resp = self._process("/protected/area/", user)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("awaiting_authorization"))

    def test_user_with_group_allowed_through(self):
        user = User.objects.create_user("grouped", password="pass12345")
        group, _ = Group.objects.get_or_create(name="Store Officers")
        user.groups.add(group)
        self.assertIsNone(self._process("/protected/area/", user))

    def test_superuser_allowed_through(self):
        user = User.objects.create_superuser("root", "r@e.com", "pass12345")
        self.assertIsNone(self._process("/protected/area/", user))

    def test_awaiting_page_is_allowlisted_for_everyone(self):
        """`/awaiting-authorization/` is in `allowed_urls`, which is checked
        early and returns None. So a grouped user is NOT bounced to the
        dashboard here.

        FINDING: the `elif request.path == reverse('awaiting_authorization'):
        return redirect('dashboard')` branch at the end of process_view is
        therefore unreachable dead code — the allowlist short-circuits first.
        This test pins the real behavior (page is open); the dead branch can
        be removed in a later cleanup without changing behavior.
        """
        user = User.objects.create_user("grouped2", password="pass12345")
        group, _ = Group.objects.get_or_create(name="Store Officers")
        user.groups.add(group)
        self.assertIsNone(self._process(reverse("awaiting_authorization"), user))


class TwoFactorEnforcementTests(TestCase):
    """The MFA branch: an authenticated user who has a confirmed 2FA device
    but has not verified in this session is forced to /2fa/verify/."""

    def test_unverified_2fa_user_forced_to_verify(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        user = User.objects.create_user("mfauser", password="pass12345")
        group, _ = Group.objects.get_or_create(name="Store Officers")
        user.groups.add(group)
        TOTPDevice.objects.create(user=user, name="default", confirmed=True)

        self.client.login(username="mfauser", password="pass12345")
        resp = self.client.get(reverse("dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("verify_2fa"), resp.url)
