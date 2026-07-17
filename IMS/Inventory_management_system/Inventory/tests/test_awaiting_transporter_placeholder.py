"""
Regression test: 'Awaiting Transporter' placeholder rows (auto-created when
an order is fully processed) must NOT count as already-transported quantity,
otherwise completed orders vanish from the Assign Transporter page.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from Inventory.models import MaterialOrder, MaterialTransport, Transporter, Unit


class AwaitingTransporterPlaceholderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('officer', password='x')
        self.unit = Unit.objects.create(name='drums')
        self.order = MaterialOrder.objects.create(
            name='Conductor',
            quantity=100,
            unit=self.unit,
            request_type='Release',
            user=self.user,
            status='Approved',
        )

    def _fully_process(self):
        self.order.processed_quantity = Decimal('100')
        self.order._status_changed = True
        self.order.save()
        self.order.refresh_from_db()

    def test_placeholder_created_on_completion(self):
        self._fully_process()
        self.assertEqual(self.order.status, 'Completed')
        self.assertTrue(
            self.order.transports.filter(status='Awaiting Transporter').exists()
        )

    def test_placeholder_excluded_from_transported_quantity(self):
        self._fully_process()
        # Placeholder carries the full quantity but must not count as transported.
        self.assertEqual(self.order.total_transported_quantity, 0)
        self.assertEqual(self.order.remaining_transport_quantity, Decimal('100'))

    def test_real_assignment_removes_placeholder(self):
        self._fully_process()
        transporter = Transporter.objects.create(name='Haul Ltd')
        MaterialTransport.objects.create(
            material_order=self.order,
            transporter=transporter,
            status='Assigned',
            quantity=100,
        )
        self.assertFalse(
            self.order.transports.filter(status='Awaiting Transporter').exists()
        )
        self.assertEqual(self.order.total_transported_quantity, 100)
