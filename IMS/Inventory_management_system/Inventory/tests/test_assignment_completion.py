"""Completing an assignment from the 'My Assigned Orders' page must release
the underlying material order through the shared processing core.

Before this fix, completion only flipped the StoreOrderAssignment record;
the MaterialOrder stayed un-processed, so it still appeared available in the
officers' 'All Material Orders' table and could be released a SECOND time
(double release). These tests lock the two halves together and keep the
signed-letter guard failing CLOSED.
"""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from Inventory.models import MaterialOrder, ReleaseLetter, StoreOrderAssignment, Unit
from Inventory.services.order_flow import process_quantity


class AssignmentCompletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user('officer', password='x')
        cls.officer.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        cls.unit = Unit.objects.create(name='each')

    def _signed_letter(self, code='REQ-X'):
        return ReleaseLetter.objects.create(
            request_code=code, title='Poles', total_quantity=10,
            uploaded_by=self.officer,
            pdf_file=SimpleUploadedFile('s.pdf', b'%PDF-1.4', 'application/pdf'),
        )

    def _order(self, **overrides):
        defaults = dict(
            name='Pole', code='POLE-1', quantity=Decimal('10'), unit=self.unit,
            request_type='Release', status='Approved', user=self.officer,
            processed_quantity=Decimal('0'), remaining_quantity=Decimal('10'),
            assigned_to=self.officer,
        )
        defaults.update(overrides)
        return MaterialOrder.objects.create(**defaults)

    def _assignment(self, order, status='In Progress'):
        return StoreOrderAssignment.objects.create(
            material_order=order, assigned_to=self.officer,
            assigned_by=self.officer, status=status,
        )

    def _complete(self, assignment):
        self.client.force_login(self.officer)
        return self.client.post(
            reverse('stores_update_assignment_status', args=[assignment.id]),
            {'status': 'Completed'})

    def test_completing_assignment_releases_the_order(self):
        """The core regression: completion must process the order so it no
        longer reads as available in the officers' table."""
        order = self._order(release_letter=self._signed_letter())
        assignment = self._assignment(order)

        resp = self._complete(assignment)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        order.refresh_from_db()
        self.assertEqual(order.status, 'Completed')
        self.assertEqual(order.processed_quantity, Decimal('10'))
        self.assertEqual(order.remaining_quantity, Decimal('0'))
        self.assertEqual(order.processed_by, self.officer)

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, 'Completed')

    def test_completion_without_signed_letter_fails_closed(self):
        """No signed letter -> 400, and NOTHING is released or marked done."""
        order = self._order()  # no release_letter
        assignment = self._assignment(order)

        resp = self._complete(assignment)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('release letter', resp.json()['message'])

        order.refresh_from_db()
        self.assertEqual(order.processed_quantity or 0, 0)
        self.assertNotEqual(order.status, 'Completed')

        assignment.refresh_from_db()
        self.assertNotEqual(assignment.status, 'Completed')

    def test_already_processed_order_is_not_released_twice(self):
        """If an officer already released the order from the All Material
        Orders table, completing the assignment must NOT process it again."""
        order = self._order(release_letter=self._signed_letter())
        process_quantity(order, Decimal('10'), self.officer)  # officer releases first
        order.refresh_from_db()
        self.assertEqual(order.processed_quantity, Decimal('10'))

        assignment = self._assignment(order)
        resp = self._complete(assignment)
        self.assertEqual(resp.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(order.processed_quantity, Decimal('10'))  # not 20
        self.assertEqual(order.status, 'Completed')
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, 'Completed')
