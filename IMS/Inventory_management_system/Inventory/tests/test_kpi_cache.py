"""
Tests for the management-dashboard KPI summary cache.

get_management_dashboard_summary() returns shared aggregates (no per-user
data) and is cached for a short TTL so dashboard refreshes / many managers
don't each re-run the COUNT/annotate queries. These tests pin: the result is
served from cache between calls, and the explicit invalidation hook forces a
recompute.
"""
from decimal import Decimal

from django.test import TestCase
from django.core.cache import cache

from Inventory.models import Unit, MaterialOrder
from Inventory.services.kpi import (
    get_management_dashboard_summary,
    invalidate_management_dashboard_summary,
    MANAGEMENT_SUMMARY_CACHE_KEY,
)


class ManagementSummaryCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.unit = Unit.objects.create(name="each")

    def tearDown(self):
        cache.clear()

    def _order(self):
        return MaterialOrder.objects.create(
            name="Pole", quantity=Decimal("1"), unit=self.unit
        )

    def test_cache_key_populated_after_first_call(self):
        self.assertIsNone(cache.get(MANAGEMENT_SUMMARY_CACHE_KEY))
        get_management_dashboard_summary()
        self.assertIsNotNone(cache.get(MANAGEMENT_SUMMARY_CACHE_KEY))

    def test_result_served_from_cache_within_ttl(self):
        first = get_management_dashboard_summary()
        self.assertEqual(first["total_orders"], 0)
        # Mutate the underlying data; the cached summary must NOT change
        # until the TTL expires or it's invalidated.
        self._order()
        second = get_management_dashboard_summary()
        self.assertEqual(second["total_orders"], 0)

    def test_invalidate_forces_recompute(self):
        get_management_dashboard_summary()  # populate cache (0 orders)
        self._order()
        invalidate_management_dashboard_summary()
        refreshed = get_management_dashboard_summary()
        self.assertEqual(refreshed["total_orders"], 1)
