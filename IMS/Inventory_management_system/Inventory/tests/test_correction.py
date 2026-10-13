"""Correction / reversal process: raise -> superuser review -> auto-reverse."""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from Inventory.models import (
    CorrectionRequest, InventoryItem, MaterialOrder, StockMovement, Unit,
)
from Inventory.services.correction import ReversalError, execute_reversal
from Inventory.services.stock_ledger import record_movement


class CorrectionFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('u', password='x')
        cls.user.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        cls.admin = User.objects.create_superuser('a', 'a@b.c', 'x')
        cls.unit = Unit.objects.create(name='pcs')
        cls.item = InventoryItem.objects.create(
            name='Pole', code='P1', quantity=90, unit=cls.unit)
        record_movement(cls.item, 'opening', qty_in=90, note='opening')

    def _order(self, **kw):
        base = dict(name='Pole', quantity=Decimal('10'), code='P1',
                    unit=self.unit, request_type='Release', request_code='R1')
        base.update(kw)
        return MaterialOrder.objects.create(**base)

    # --- raising ---
    def test_user_can_raise_and_it_is_pending(self):
        order = self._order(status='Draft')
        self.client.force_login(self.user)
        r = self.client.post(reverse('raise_correction'), {
            'target_model': 'order', 'target_id': order.pk,
            'kind': 'order_approval', 'reason': 'approved wrong order'})
        self.assertEqual(r.status_code, 302)
        cr = CorrectionRequest.objects.get()
        self.assertEqual(cr.status, 'Pending')
        self.assertEqual(cr.raised_by, self.user)

    def test_duplicate_pending_blocked(self):
        order = self._order(status='Draft')
        ct = ContentType.objects.get_for_model(MaterialOrder)
        CorrectionRequest.objects.create(content_type=ct, object_id=order.pk,
                                         kind='order_approval', reason='x',
                                         raised_by=self.user)
        self.client.force_login(self.user)
        self.client.post(reverse('raise_correction'), {
            'target_model': 'order', 'target_id': order.pk,
            'kind': 'order_approval', 'reason': 'again'})
        self.assertEqual(CorrectionRequest.objects.filter(object_id=order.pk).count(), 1)

    # --- review gate ---
    def test_review_queue_superuser_only(self):
        self.client.force_login(self.user)
        self.assertNotEqual(self.client.get(reverse('correction_list')).status_code, 200)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('correction_list')).status_code, 200)

    def test_non_superuser_cannot_approve(self):
        order = self._order(status='Draft')
        cr = self._cr(order, 'order_approval')
        self.client.force_login(self.user)
        self.client.post(reverse('review_correction', args=[cr.pk]),
                         {'action': 'approve'})
        cr.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(cr.status, 'Pending')

    def _cr(self, target, kind):
        ct = ContentType.objects.get_for_model(type(target))
        return CorrectionRequest.objects.create(
            content_type=ct, object_id=target.pk, kind=kind,
            reason='mistake', raised_by=self.user)

    # --- auto-execute reversals ---
    def test_approve_release_restocks_and_reopens(self):
        self.item.quantity = 80; self.item.save()  # 10 already released
        order = self._order(status='Completed', processed_quantity=Decimal('10'),
                            remaining_quantity=Decimal('0'),
                            stock_deducted_quantity=Decimal('10'))
        cr = self._cr(order, 'release')
        self.client.force_login(self.admin)
        self.client.post(reverse('review_correction', args=[cr.pk]), {'action': 'approve'})
        cr.refresh_from_db(); order.refresh_from_db(); self.item.refresh_from_db()
        self.assertEqual(cr.status, 'Approved')
        self.assertEqual(self.item.quantity, 90)           # restocked
        self.assertEqual(order.status, 'Approved')         # re-opened
        self.assertEqual(order.processed_quantity, 0)
        self.assertTrue(StockMovement.objects.filter(
            item=self.item, movement_type='reversal').exists())

    def test_approve_order_approval_sets_draft(self):
        order = self._order(status='Approved', assigned_to=self.user)
        cr = self._cr(order, 'order_approval')
        self.client.force_login(self.admin)
        self.client.post(reverse('review_correction', args=[cr.pk]), {'action': 'approve'})
        order.refresh_from_db()
        self.assertEqual(order.status, 'Draft')
        self.assertIsNone(order.assigned_to)

    def test_approve_stock_entry_compensates(self):
        # A wrong receipt of 20 pushed stock from 90 -> 110.
        self.item.quantity = 110; self.item.save()
        mv = record_movement(self.item, 'receipt', qty_in=20, reference='bad',
                             user=self.user, note='wrong upload')
        cr = self._cr(mv, 'stock_entry')
        self.client.force_login(self.admin)
        self.client.post(reverse('review_correction', args=[cr.pk]), {'action': 'approve'})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 90)           # undone
        self.assertEqual(StockMovement.objects.filter(
            item=self.item, movement_type='reversal').count(), 1)

    def test_reject_does_not_reverse(self):
        order = self._order(status='Approved')
        cr = self._cr(order, 'order_approval')
        self.client.force_login(self.admin)
        self.client.post(reverse('review_correction', args=[cr.pk]),
                         {'action': 'reject', 'review_note': 'not a mistake'})
        cr.refresh_from_db(); order.refresh_from_db()
        self.assertEqual(cr.status, 'Rejected')
        self.assertEqual(order.status, 'Approved')         # unchanged

    def test_cannot_reverse_a_reversal(self):
        mv = record_movement(self.item, 'reversal', qty_in=5, user=self.user)
        cr = self._cr(mv, 'stock_entry')
        with self.assertRaises(ReversalError):
            execute_reversal(cr, self.admin)
