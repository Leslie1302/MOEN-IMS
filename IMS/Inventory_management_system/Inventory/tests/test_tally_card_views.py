"""The tally card pages are reachable by stores users and show the ledger."""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from Inventory.models import InventoryItem, Unit
from Inventory.services.stock_ledger import record_movement


class TallyCardViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user('so', password='x')
        cls.officer.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        cls.outsider = User.objects.create_user('out', password='x')
        cls.unit = Unit.objects.create(name='pcs')
        cls.item = InventoryItem.objects.create(
            name='Stay Wire', code='SMA015', quantity=100, unit=cls.unit)
        record_movement(cls.item, 'opening', qty_in=100, note='opening')

    def test_list_and_detail_reachable_by_stores_user(self):
        self.client.force_login(self.officer)
        r1 = self.client.get(reverse('tally_card_list'))
        self.assertEqual(r1.status_code, 200)
        self.assertContains(r1, 'SMA015')

        r2 = self.client.get(reverse('tally_card_detail', args=[self.item.pk]))
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, 'Opening balance')

    def test_outsider_denied(self):
        self.client.force_login(self.outsider)
        r = self.client.get(reverse('tally_card_list'))
        self.assertNotEqual(r.status_code, 200)

    def test_reorder_flag_shows(self):
        self.item.reorder_level = 200  # 100 <= 200 -> flagged
        self.item.save()
        self.client.force_login(self.officer)
        r = self.client.get(reverse('tally_card_detail', args=[self.item.pk]))
        self.assertContains(r, 'Reorder')

    def test_adjustment_posts_audited_movement_and_updates_stock(self):
        from Inventory.models import StockMovement
        self.client.force_login(self.officer)
        r = self.client.post(
            reverse('tally_card_adjust', args=[self.item.pk]),
            {'counted_quantity': '90', 'reason': 'physical count, 10 damaged'})
        self.assertEqual(r.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 90)
        adj = StockMovement.objects.filter(item=self.item, movement_type='adjustment').latest('id')
        self.assertEqual(adj.qty_out, 10)          # 100 -> 90
        self.assertEqual(adj.balance_after, 90)
        self.assertIn('physical count', adj.note)
        self.assertEqual(adj.performed_by, self.officer)

    def test_adjustment_requires_reason(self):
        self.client.force_login(self.officer)
        self.client.post(reverse('tally_card_adjust', args=[self.item.pk]),
                         {'counted_quantity': '50', 'reason': ''})
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, 100)  # unchanged

    def test_excel_export_downloads(self):
        self.client.force_login(self.officer)
        r = self.client.get(reverse('tally_card_excel', args=[self.item.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn('spreadsheetml', r['Content-Type'])

    def test_low_stock_filter(self):
        self.item.reorder_level = 200
        self.item.save()
        self.client.force_login(self.officer)
        r = self.client.get(reverse('tally_card_list') + '?low=1')
        self.assertContains(r, 'SMA015')

    def test_find_drift_detects_out_of_band_change(self):
        from Inventory.services.stock_ledger import find_drift
        # Consistent to start (opening balance == quantity).
        self.assertEqual(find_drift(), [])
        # Tamper with live stock WITHOUT a ledger row — the exact thing the
        # integrity check must catch.
        InventoryItem.objects.filter(pk=self.item.pk).update(quantity=77)
        drift = find_drift()
        self.assertEqual(len(drift), 1)
        item, live, ledger = drift[0]
        self.assertEqual(live, 77)
        self.assertEqual(ledger, 100)

    def test_integrity_view_supervisor_only(self):
        # Store officer (not supervisor) is denied.
        self.client.force_login(self.officer)
        self.assertNotEqual(
            self.client.get(reverse('stock_ledger_integrity')).status_code, 200)
        # Stores Management passes.
        boss = User.objects.create_user('boss', password='x')
        boss.groups.add(Group.objects.get_or_create(name='Stores Management')[0])
        self.client.force_login(boss)
        self.assertEqual(
            self.client.get(reverse('stock_ledger_integrity')).status_code, 200)

    def test_consolidated_view_totals_across_warehouses(self):
        # Same code in a second warehouse.
        InventoryItem.objects.create(
            name='Stay Wire', code='SMA015', quantity=40, unit=self.unit)
        self.client.force_login(self.officer)
        r = self.client.get(reverse('tally_card_consolidated'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '140')  # 100 + 40
