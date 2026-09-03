"""The stock ledger (tally card source of truth) must record every real stock
change, and its running balance must always equal live stock.

These lock in the two things that make the tally card trustworthy:
  * processing a release writes an 'issue' movement, and
  * balance_after on the latest movement equals the item's live quantity.
"""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from Inventory.models import InventoryItem, ReleaseLetter, StockMovement, Unit
from Inventory.services.order_flow import process_quantity
from Inventory.services.stock_ledger import record_movement


class StockLedgerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user('officer', password='x')
        cls.officer.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        cls.unit = Unit.objects.create(name='each')

    def _signed_letter(self):
        return ReleaseLetter.objects.create(
            request_code='REQ-LEDGER', title='Poles', total_quantity=10,
            uploaded_by=self.officer,
            pdf_file=SimpleUploadedFile('s.pdf', b'%PDF-1.4', 'application/pdf'))

    def test_release_writes_issue_movement_and_tracks_balance(self):
        item = InventoryItem.objects.create(
            name='Pole', code='POLE-1', quantity=100, unit=self.unit)
        from Inventory.models import MaterialOrder
        order = MaterialOrder.objects.create(
            name='Pole', code='POLE-1', quantity=10, unit=self.unit,
            request_type='Release', status='Approved', user=self.officer,
            processed_quantity=0, remaining_quantity=10,
            release_letter=self._signed_letter())

        process_quantity(order, 4, self.officer)
        process_quantity(order, 6, self.officer)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 90)  # 100 - 10 issued

        issues = list(StockMovement.objects.filter(item=item, movement_type='issue'))
        self.assertEqual(len(issues), 2)
        self.assertEqual(sum(m.qty_out for m in issues), Decimal('10'))
        # Latest movement's running balance must equal live stock — the
        # integrity invariant the whole card rests on.
        self.assertEqual(issues[-1].balance_after, Decimal('90'))

    def test_record_movement_snapshots_live_quantity(self):
        item = InventoryItem.objects.create(
            name='Cable', code='CAB-1', quantity=50, unit=self.unit)

        item.quantity += 15
        item.save()
        m_in = record_movement(item, 'receipt', qty_in=15, user=self.officer)
        self.assertEqual(m_in.qty_in, 15)
        self.assertEqual(m_in.balance_after, item.quantity)  # 65

        item.quantity -= 5
        item.save()
        m_out = record_movement(item, 'issue', qty_out=5, user=self.officer)
        self.assertEqual(m_out.qty_out, 5)
        self.assertEqual(m_out.balance_after, Decimal('60'))

    def test_new_item_can_open_its_own_balance(self):
        item = InventoryItem.objects.create(
            name='Lug', code='LUG-1', quantity=200, unit=self.unit)
        m = record_movement(item, 'opening', qty_in=200, note='opening')
        self.assertEqual(m.movement_type, 'opening')
        self.assertEqual(m.balance_after, Decimal('200'))
