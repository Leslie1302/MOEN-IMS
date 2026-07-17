"""
Phase 3 regression tests: one processing path, explicit status machine.

Covers the two behaviours that caused this month's bugs:
  * the signed-letter guard applies on EVERY processing endpoint
    (the Store Hub used to skip it), and
  * a status set explicitly survives an unrelated save()
    (MaterialOrder.save() used to recompute and revert it).
"""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from Inventory.models import MaterialOrder, ReleaseLetter, Unit
from Inventory.services.order_flow import ProcessingError, process_quantity


class OrderFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user('officer', password='x')
        # Group membership matters: users without a group get bounced to
        # the awaiting-authorization page before any view runs.
        group, _ = Group.objects.get_or_create(name='Store Officers')
        cls.officer.groups.add(group)
        cls.unit = Unit.objects.create(name='each')

    def _order(self, **overrides):
        defaults = dict(
            name='Pole', code='POLE-1', quantity=10, unit=self.unit,
            request_type='Release', status='Approved', user=self.officer,
            processed_quantity=0, remaining_quantity=10,
            assigned_to=self.officer,
        )
        defaults.update(overrides)
        return MaterialOrder.objects.create(**defaults)

    def test_release_without_letter_is_blocked(self):
        order = self._order()
        with self.assertRaises(ProcessingError):
            process_quantity(order, 5, self.officer)
        order.refresh_from_db()
        self.assertEqual(order.processed_quantity or 0, 0)

    def test_hub_endpoint_enforces_the_guard_too(self):
        """The Store Hub path must hit the same guard as the officers' page."""
        order = self._order()
        self.client.force_login(self.officer)
        resp = self.client.post(
            reverse('process_order_partial', args=[order.id]),
            {'quantity': '5'})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('release letter', resp.json()['message'])

    def test_processing_with_signed_letter_succeeds(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        letter = ReleaseLetter.objects.create(
            request_code='REQ-X', title='Poles',
            total_quantity=10, uploaded_by=self.officer,
            pdf_file=SimpleUploadedFile('s.pdf', b'%PDF-1.4', 'application/pdf'),
        )
        order = self._order(release_letter=letter)
        process_quantity(order, 4, self.officer)
        order.refresh_from_db()
        self.assertEqual(order.status, 'Partially Fulfilled')
        self.assertEqual(order.processed_quantity, Decimal('4'))
        process_quantity(order, 6, self.officer)
        order.refresh_from_db()
        self.assertEqual(order.status, 'Completed')
        self.assertEqual(order.remaining_quantity, Decimal('0'))

    def test_explicit_status_survives_save(self):
        """save() must not run a shadow state machine any more."""
        order = self._order(processed_quantity=10, status='Completed')
        order.status = 'In Transit'
        order.save()
        order.refresh_from_db()
        self.assertEqual(order.status, 'In Transit')
        # remaining_quantity stays derived
        self.assertEqual(order.remaining_quantity, Decimal('0'))
