"""Materials movement report: period resolution, build, enrichment, access."""
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from Inventory.models import (
    BillOfQuantity, InventoryItem, MaterialOrder, Unit, Warehouse,
)
from Inventory.services.movement_report import build_report, resolve_period
from Inventory.services.stock_ledger import record_movement


class MovementReportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user('so', password='x')
        cls.officer.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        cls.outsider = User.objects.create_user('out', password='x')
        cls.wh = Warehouse.objects.create(name='Tema Central', code='TC')
        cls.unit = Unit.objects.create(name='pcs')
        cls.item = InventoryItem.objects.create(
            name='Pole', code='P1', quantity=100, unit=cls.unit, warehouse=cls.wh)
        record_movement(cls.item, 'opening', qty_in=100, note='opening')
        # A release that cites a request code resolvable to a destination.
        cls.boq = BillOfQuantity.objects.create(
            region='Greater Accra', district='Ga West', community='AMASAMAN',
            consultant='C', contractor='K', package_number='PKG1',
            material_description='Pole', item_code='P1', contract_quantity=500.0)
        cls.order = MaterialOrder.objects.create(
            name='Pole', quantity=Decimal('20'), code='P1', unit=cls.unit,
            request_code='REQ-20261001-000001', status='Completed',
            linked_boq_item=cls.boq)
        cls.item.quantity = 80
        cls.item.save()
        record_movement(cls.item, 'issue', qty_out=20, reference='P1',
                        user=cls.officer, note='Release order REQ-20261001-000001')

    # --- period resolution ---
    def test_resolve_week_is_seven_days(self):
        d_from, d_to, _ = resolve_period('week')
        self.assertEqual((d_to - d_from).days, 6)
        self.assertEqual(d_from.weekday(), 0)  # Monday

    def test_resolve_custom_swaps_reversed_range(self):
        d_from, d_to, _ = resolve_period('custom', '2026-10-10', '2026-10-01')
        self.assertLess(d_from, d_to)

    # --- build ---
    def test_build_summary_and_detail(self):
        today = timezone.localdate()
        rep = build_report(today - timedelta(days=1), today + timedelta(days=1))
        self.assertEqual(rep['totals']['materials'], 1)
        # opening(100 in) + issue(20 out)
        self.assertEqual(rep['totals']['received'], 100)
        self.assertEqual(rep['totals']['issued'], 20)
        row = rep['summary'][0]
        self.assertEqual(row['issued'], 20)
        self.assertEqual(row['closing_balance'], 80)

    def test_detail_enriches_destination_and_status(self):
        today = timezone.localdate()
        rep = build_report(today - timedelta(days=1), today + timedelta(days=1))
        issue = [d for d in rep['detail'] if d['type_raw'] == 'issue'][0]
        self.assertIn('AMASAMAN', issue['destination'])
        self.assertEqual(issue['status'], 'Completed')

    def test_warehouse_filter(self):
        today = timezone.localdate()
        other = Warehouse.objects.create(name='Other', code='OT')
        rep = build_report(today - timedelta(days=1), today + timedelta(days=1),
                           warehouse_id=other.id)
        self.assertEqual(rep['totals']['movements'], 0)

    def test_empty_period(self):
        rep = build_report(date(2020, 1, 1), date(2020, 1, 2))
        self.assertEqual(rep['summary'], [])
        self.assertEqual(rep['totals']['movements'], 0)

    # --- access + export ---
    def test_page_access(self):
        self.client.force_login(self.outsider)
        self.assertNotEqual(self.client.get(reverse('materials_movement_report')).status_code, 200)
        self.client.force_login(self.officer)
        self.assertEqual(self.client.get(reverse('materials_movement_report')).status_code, 200)

    def test_excel_export(self):
        self.client.force_login(self.officer)
        r = self.client.get(reverse('materials_movement_report_excel') + '?period=month')
        self.assertEqual(r.status_code, 200)
        self.assertIn('spreadsheetml', r['Content-Type'])

    # --- command ---
    def test_weekly_command_dry_run(self):
        out = StringIO()
        call_command('generate_materials_movement_report', '--dry-run', stdout=out)
        self.assertIn('Week', out.getvalue())

    def test_weekly_command_creates_notifications(self):
        # Non-dry: email path self-skips without M365 creds; in-app notifications
        # must still be created for both stakeholder groups, and it must not crash.
        from Inventory.models import Notification
        out = StringIO()
        call_command('generate_materials_movement_report', stdout=out, stderr=StringIO())
        titles = Notification.objects.filter(
            title__startswith='Weekly Materials Movement').values_list('recipient_group', flat=True)
        self.assertEqual(set(titles), {'Management', 'Stores Management'})
