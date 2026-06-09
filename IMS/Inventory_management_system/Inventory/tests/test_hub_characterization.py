"""
Characterization tests for the four largest, highest-blast-radius, untested
view functions identified by the code-graph analysis:

    download_waybill_pdf   transporter_views.py        (1085 lines)
    management_dashboard   views/dashboard_views.py    ( 545 lines)
    upload_requests        views/request_flow_views.py ( 284 lines)
    handle_bulk_request    views/order_views.py        ( 258 lines, via legacy view)

These are CHARACTERIZATION tests: they pin the *current* observable contract
(auth boundary, permission gating, HTTP-method handling, input rejection)
BEFORE the functions are decomposed — so a refactor that changes behavior
fails loudly. They intentionally do not assert on the happy-path PDF/render
internals, which need heavy fixtures; the goal is a safety net around the
stable edges.

Auth note: this app enforces login centrally via
`Inventory.middleware.UserRoleMiddleware` (default-deny allowlist), not via
per-view `@login_required`. Authenticated test users are therefore given a
group so the middleware lets them through to the view under test.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile

from Inventory.models import Unit, MaterialOrder
from Inventory.models.transport import MaterialTransport


def _staff_in_group(group_name, **kwargs):
    """Create a staff user assigned to a (single) group so UserRoleMiddleware
    admits them. No 2FA device is created, so MFA enforcement is skipped."""
    user = User.objects.create_user(
        username=kwargs.pop("username", f"u_{group_name.replace(' ', '_').lower()}"),
        password="pass12345",
        is_staff=True,
        **kwargs,
    )
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)
    return user


class DownloadWaybillPdfCharacterizationTests(TestCase):
    def setUp(self):
        self.unit = Unit.objects.create(name="each")
        order = MaterialOrder.objects.create(
            name="Pole", quantity=Decimal("10"), unit=self.unit
        )
        # waybill_number defaults to 'Unknown' and no site_receipt exists,
        # which drives the "not yet received on site" guard branch.
        self.transport = MaterialTransport.objects.create(
            material_order=order, quantity=Decimal("10")
        )

    def test_requires_login(self):
        resp = self.client.get(
            reverse("download_waybill_pdf", args=[self.transport.pk])
        )
        self.assertIn(resp.status_code, (301, 302))  # middleware → login

    def test_nonexistent_transport_returns_404(self):
        _staff_in_group("Store Officers")
        self.client.login(username="u_store_officers", password="pass12345")
        resp = self.client.get(reverse("download_waybill_pdf", args=[999999]))
        self.assertEqual(resp.status_code, 404)

    def test_no_site_receipt_redirects_not_pdf(self):
        """Core business rule: a waybill cannot be downloaded until the site
        receipt is logged — the view redirects to transportation_status
        instead of returning a PDF."""
        _staff_in_group("Store Officers")
        self.client.login(username="u_store_officers", password="pass12345")
        resp = self.client.get(
            reverse("download_waybill_pdf", args=[self.transport.pk])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("transportation_status"), resp.url)


class ManagementDashboardCharacterizationTests(TestCase):
    def test_requires_login(self):
        resp = self.client.get(reverse("management_dashboard"))
        self.assertIn(resp.status_code, (301, 302))

    def test_non_management_user_redirected_to_dashboard(self):
        _staff_in_group("Store Officers")
        self.client.login(username="u_store_officers", password="pass12345")
        resp = self.client.get(reverse("management_dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("dashboard"), resp.url)

    def test_management_user_gets_200(self):
        _staff_in_group("Management")
        self.client.login(username="u_management", password="pass12345")
        resp = self.client.get(reverse("management_dashboard"))
        self.assertEqual(resp.status_code, 200)

    def test_superuser_gets_200(self):
        User.objects.create_superuser(
            username="root", password="pass12345", email="r@e.com"
        )
        self.client.login(username="root", password="pass12345")
        resp = self.client.get(reverse("management_dashboard"))
        self.assertEqual(resp.status_code, 200)


class UploadRequestsCharacterizationTests(TestCase):
    def setUp(self):
        _staff_in_group("Store Officers")
        self.client.login(username="u_store_officers", password="pass12345")

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.post(reverse("upload_requests"))
        self.assertIn(resp.status_code, (301, 302))

    def test_get_redirects_to_request_material(self):
        resp = self.client.get(reverse("upload_requests"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("request_material"), resp.url)

    def test_post_without_file_redirects(self):
        resp = self.client.post(reverse("upload_requests"), {"project": "shep"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("request_material"), resp.url)

    def test_post_non_excel_file_rejected(self):
        bad = SimpleUploadedFile("data.txt", b"not excel", content_type="text/plain")
        resp = self.client.post(
            reverse("upload_requests"), {"project": "shep", "file": bad}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("request_material"), resp.url)

    def test_post_unknown_project_rejected(self):
        xlsx = SimpleUploadedFile(
            "rows.xlsx",
            b"PK\x03\x04dummy",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp = self.client.post(
            reverse("upload_requests"),
            {"project": "definitely-not-a-real-project", "file": xlsx},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("request_material"), resp.url)


class BulkRequestCharacterizationTests(TestCase):
    """handle_bulk_request is a method of the legacy RequestMaterialView,
    reachable at request_material_legacy. We pin the auth boundary and that
    malformed bulk input does not 500."""

    def test_legacy_view_requires_login(self):
        resp = self.client.get(reverse("request_material_legacy"))
        self.assertIn(resp.status_code, (301, 302))

    def test_malformed_bulk_post_does_not_crash(self):
        _staff_in_group("Store Officers")
        self.client.login(username="u_store_officers", password="pass12345")
        resp = self.client.post(
            reverse("request_material_legacy"),
            {"bulk_submit": "1"},  # routes to handle_bulk_request; no file/valid data
        )
        # Current contract: invalid bulk input is handled (form re-render or
        # redirect), never a server error.
        self.assertLess(resp.status_code, 500)
