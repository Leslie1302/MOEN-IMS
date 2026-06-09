"""
Rate-limit tests for the heavy / abusable endpoints.

These endpoints generate PDFs or parse uploaded spreadsheets and write many
rows, so an authenticated user hammering them is a resource-exhaustion
vector. django-ratelimit (key='user', block=True) caps them; exceeding the
cap returns 403.

Notes:
- RATELIMIT_ENABLE is forced True so the tests are deterministic regardless
  of env. (Axes is already disabled under TESTING and doesn't interfere.)
- The ratelimit cache (LocMemCache in tests) is shared across the process,
  so we clear it in setUp to keep counters isolated per test.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.core.cache import cache

from Inventory.models import Unit, MaterialOrder
from Inventory.models.transport import MaterialTransport


def _staff_in_group(username, group_name="Store Officers"):
    user = User.objects.create_user(
        username=username, password="pass12345", is_staff=True
    )
    group, _ = Group.objects.get_or_create(name=group_name)
    user.groups.add(group)
    return user


@override_settings(RATELIMIT_ENABLE=True)
class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()  # reset ratelimit counters between tests

    def tearDown(self):
        cache.clear()

    # --- download_waybill_pdf: 10/min/user ---

    def test_waybill_pdf_throttled_after_limit(self):
        unit = Unit.objects.create(name="each")
        order = MaterialOrder.objects.create(
            name="Pole", quantity=Decimal("10"), unit=unit
        )
        transport = MaterialTransport.objects.create(
            material_order=order, quantity=Decimal("10")
        )
        _staff_in_group("wb_user")
        self.client.login(username="wb_user", password="pass12345")
        url = reverse("download_waybill_pdf", args=[transport.pk])

        statuses = [self.client.get(url).status_code for _ in range(11)]
        # First request is allowed (302 redirect: no site receipt yet),
        # and at least one request past the 10/min cap is blocked (403).
        self.assertNotEqual(statuses[0], 403)
        self.assertIn(403, statuses)

    # --- upload_requests: 6 POSTs/min/user ---

    def test_upload_requests_throttled_after_limit(self):
        _staff_in_group("ul_user")
        self.client.login(username="ul_user", password="pass12345")
        url = reverse("upload_requests")

        # Each POST is malformed (no file) → 302 until the cap trips at 403.
        statuses = [
            self.client.post(url, {"project": "shep"}).status_code
            for _ in range(7)
        ]
        self.assertNotEqual(statuses[0], 403)
        self.assertIn(403, statuses)

    # --- RequestMaterialView (legacy, owns handle_bulk_request): 6 POSTs/min/user ---

    def test_bulk_request_post_throttled_after_limit(self):
        _staff_in_group("bk_user")
        self.client.login(username="bk_user", password="pass12345")
        url = reverse("request_material_legacy")

        statuses = [
            self.client.post(url, {"bulk_submit": "1"}).status_code
            for _ in range(7)
        ]
        self.assertNotEqual(statuses[0], 403)
        self.assertIn(403, statuses)
