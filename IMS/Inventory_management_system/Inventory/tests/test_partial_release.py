"""Partial release from 'My Assigned Orders': releasing part of an order
deducts that quantity, moves the order to Partially Fulfilled, and leaves the
balance open; a partial that clears the balance closes the assignment."""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from Inventory.models import (
    InventoryItem, MaterialOrder, ReleaseLetter, StoreOrderAssignment, Unit,
)


class PartialReleaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user('so', password='x')
        cls.officer.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        cls.unit = Unit.objects.create(name='pcs')
        cls.item = InventoryItem.objects.create(
            name='Pole', code='LHP006', quantity=100, unit=cls.unit)

    def _assignment(self, qty=40):
        letter = ReleaseLetter.objects.create(
            request_code='REQ-P', title='Poles', total_quantity=Decimal('40'),
            uploaded_by=self.officer,
            pdf_file=SimpleUploadedFile('s.pdf', b'%PDF-1.4', 'application/pdf'))
        order = MaterialOrder.objects.create(
            name='Pole', code='LHP006', quantity=Decimal(str(qty)), unit=self.unit,
            request_type='Release', status='Approved', user=self.officer,
            assigned_to=self.officer, processed_quantity=0, remaining_quantity=qty,
            release_letter=letter)
        return StoreOrderAssignment.objects.create(
            material_order=order, assigned_to=self.officer,
            assigned_by=self.officer, status='In Progress')

    def _post(self, assignment, **data):
        self.client.force_login(self.officer)
        return self.client.post(
            reverse('stores_update_assignment_status', args=[assignment.id]), data)

    def test_partial_release_deducts_and_keeps_open(self):
        a = self._assignment(qty=40)
        r = self._post(a, status='Partial', quantity='15')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['success'])
        a.material_order.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(a.material_order.processed_quantity, Decimal('15'))
        self.assertEqual(a.material_order.remaining_quantity, Decimal('25'))
        self.assertEqual(a.material_order.status, 'Partially Fulfilled')
        self.assertEqual(self.item.quantity, 85)  # 100 - 15
        a.refresh_from_db()
        self.assertEqual(a.status, 'In Progress')  # still open

    def test_partial_over_remaining_is_rejected(self):
        a = self._assignment(qty=40)
        r = self._post(a, status='Partial', quantity='999')
        self.assertEqual(r.status_code, 400)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 100)  # nothing deducted

    def test_partial_clearing_balance_completes_assignment(self):
        a = self._assignment(qty=40)
        self._post(a, status='Partial', quantity='40')
        a.refresh_from_db()
        a.material_order.refresh_from_db()
        self.assertEqual(a.material_order.remaining_quantity, Decimal('0'))
        self.assertEqual(a.status, 'Completed')
