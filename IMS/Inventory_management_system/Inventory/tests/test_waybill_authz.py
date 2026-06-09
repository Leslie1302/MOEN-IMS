"""
Object-level authorization for waybill PDF downloads.

`download_waybill_pdf` was gated by @login_required only, so any authenticated
user — including an external Transporter operator — could pull ANY waybill by
iterating transport_id (IDOR / cross-company data exposure). The view now
restricts external (non-staff) users to waybills for their own transporter,
while internal staff / Management / superusers retain full access.
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.core.cache import cache

from Inventory.models import Unit, MaterialOrder
from Inventory.models.transport import MaterialTransport
from Inventory.transporter_models import Transporter


class WaybillDownloadAuthorizationTests(TestCase):
    def setUp(self):
        cache.clear()  # isolate rate-limit counters
        self.unit = Unit.objects.create(name="each")
        self.order = MaterialOrder.objects.create(
            name="Pole", quantity=Decimal("5"), unit=self.unit
        )

        transporters = Group.objects.get_or_create(name="Transporters")[0]

        # Two EXTERNAL transporter operators (not staff), each a distinct company.
        self.op_a = User.objects.create_user("op_a", password="pw")
        self.op_b = User.objects.create_user("op_b", password="pw")
        self.op_a.groups.add(transporters)
        self.op_b.groups.add(transporters)
        self.co_a = Transporter.objects.create(name="Co A", user=self.op_a)
        self.co_b = Transporter.objects.create(name="Co B", user=self.op_b)

        # A shipment assigned to Co A (no site receipt yet → download guard
        # redirects rather than producing a PDF, which is fine: we only care
        # here whether the AUTHORIZATION gate passed (302/not-404) or blocked (404)).
        self.transport_a = MaterialTransport.objects.create(
            material_order=self.order, quantity=Decimal("5"), transporter=self.co_a
        )

    def _url(self, transport):
        return reverse("download_waybill_pdf", args=[transport.pk])

    def test_external_operator_cannot_access_other_companys_waybill(self):
        self.client.login(username="op_b", password="pw")
        resp = self.client.get(self._url(self.transport_a))
        self.assertEqual(resp.status_code, 404)  # IDOR blocked, existence not leaked

    def test_external_operator_can_reach_own_waybill(self):
        self.client.login(username="op_a", password="pw")
        resp = self.client.get(self._url(self.transport_a))
        # Passed authz; blocked only by the "no site receipt yet" guard → 302.
        self.assertEqual(resp.status_code, 302)
        self.assertNotEqual(resp.status_code, 404)

    def test_internal_staff_can_reach_any_waybill(self):
        staff = User.objects.create_user("officer", password="pw", is_staff=True)
        staff.groups.add(Group.objects.get_or_create(name="Store Officers")[0])
        self.client.login(username="officer", password="pw")
        resp = self.client.get(self._url(self.transport_a))
        self.assertEqual(resp.status_code, 302)  # internal access allowed (not 404)

    def test_superuser_can_reach_any_waybill(self):
        User.objects.create_superuser("root", "r@e.com", "pw")
        self.client.login(username="root", password="pw")
        resp = self.client.get(self._url(self.transport_a))
        self.assertEqual(resp.status_code, 302)
