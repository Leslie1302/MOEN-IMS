"""Stock valuation report: value = qty x unit_cost, grouped by store, unpriced
items flagged and counted, prices editable by supervisors."""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from Inventory.models import InventoryItem, Unit, Warehouse


class StockValuationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user('so', password='x')
        cls.officer.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        cls.boss = User.objects.create_user('boss', password='x')
        cls.boss.groups.add(Group.objects.get_or_create(name='Stores Management')[0])
        cls.unit = Unit.objects.create(name='pcs')
        cls.tema = Warehouse.objects.create(name='Tema', code='T', location='x')
        cls.wa = Warehouse.objects.create(name='Wa', code='W', location='y')
        InventoryItem.objects.create(name='Pole', code='P1', quantity=10,
                                     unit=cls.unit, warehouse=cls.tema, unit_cost=Decimal('5'))
        InventoryItem.objects.create(name='Cable', code='C1', quantity=4,
                                     unit=cls.unit, warehouse=cls.tema, unit_cost=Decimal('2.50'))
        # Unpriced item in a different store.
        InventoryItem.objects.create(name='Lug', code='L1', quantity=100,
                                     unit=cls.unit, warehouse=cls.wa, unit_cost=Decimal('0'))

    def test_values_and_totals(self):
        self.client.force_login(self.officer)
        r = self.client.get(reverse('stock_valuation'))
        self.assertEqual(r.status_code, 200)
        # Tema subtotal = 10*5 + 4*2.5 = 60; grand total = 60 (+ Wa 0)
        self.assertEqual(r.context['grand_total'], Decimal('60.00'))
        self.assertEqual(r.context['total_unpriced'], 1)
        # Two stores grouped
        self.assertEqual(len(r.context['stores']), 2)

    def test_store_filter(self):
        self.client.force_login(self.officer)
        r = self.client.get(reverse('stock_valuation') + f'?warehouse={self.tema.id}')
        self.assertEqual(len(r.context['stores']), 1)
        self.assertEqual(r.context['grand_total'], Decimal('60.00'))

    def test_supervisor_can_update_price(self):
        item = InventoryItem.objects.get(code='L1')
        self.client.force_login(self.boss)
        self.client.post(reverse('stock_valuation_update_price', args=[item.pk]),
                         {'unit_cost': '3.00', 'next': reverse('stock_valuation')})
        item.refresh_from_db()
        self.assertEqual(item.unit_cost, Decimal('3.00'))

    def test_officer_cannot_update_price(self):
        item = InventoryItem.objects.get(code='L1')
        self.client.force_login(self.officer)
        self.client.post(reverse('stock_valuation_update_price', args=[item.pk]),
                         {'unit_cost': '9.99'})
        item.refresh_from_db()
        self.assertEqual(item.unit_cost, Decimal('0'))  # unchanged

    def test_excel_export(self):
        self.client.force_login(self.officer)
        r = self.client.get(reverse('stock_valuation_excel'))
        self.assertEqual(r.status_code, 200)
        self.assertIn('spreadsheetml', r['Content-Type'])
