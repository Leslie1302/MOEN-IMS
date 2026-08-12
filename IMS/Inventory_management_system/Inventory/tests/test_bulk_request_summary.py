"""Bulk material release requests lump their per-line notifications into one
summary — mirroring the BoQ bulk-import behaviour. The per-line signal is
suppressed while the `_order_bulk` flag is set; a single summary is sent by the
bulk creator instead."""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from Inventory.models import MaterialOrder, Unit
from Inventory.signals import _order_bulk, order_bulk_active


class BulkRequestSummaryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unit = Unit.objects.create(name='No.')

    def _order(self):
        return MaterialOrder.objects.create(
            name='Pole', quantity=Decimal('5'), unit=self.unit,
            request_type='Release', region='ASHANTI', district='KUMASI')

    @patch('Inventory.signals.create_notification')
    def test_bulk_suppresses_per_line_notifications(self, mock_notify):
        _order_bulk.on = True
        try:
            self._order()
            self._order()
        finally:
            _order_bulk.on = False
        mock_notify.assert_not_called()          # no per-line spam during the loop

    @patch('Inventory.signals.create_notification')
    def test_non_bulk_still_notifies_per_request(self, mock_notify):
        self._order()
        self.assertTrue(mock_notify.called)      # a single (non-bulk) request still notifies

    def test_flag_defaults_off(self):
        self.assertFalse(order_bulk_active())
