"""Seed demo stock movements so the Materials Movement Report has data to test.

Creates a DEMO store, a few materials with matching BoQ destinations, demo
release orders, and ledger movements (opening / receipt / issue / transfer /
adjustment / write-off) spread across the last ~12 days.

    python manage.py seed_movement_demo          # create demo data
    python manage.py seed_movement_demo --clear   # remove it again

All demo data is tagged (store code DEMO, request codes REQ-DEMO-*) so --clear
removes exactly what this command created and nothing else.
"""
import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from Inventory.models import (
    BillOfQuantity, InventoryItem, MaterialOrder, StockMovement, Unit, Warehouse,
)
from Inventory.services.stock_ledger import record_movement

MATERIALS = [
    ('HT Stay Insulator', 'DEMO-SMA002', 400),
    ('LV Stay Insulator', 'DEMO-SMA001', 500),
    ('33/0.433kV 200kVA Transformer', 'DEMO-TRF200', 60),
    ('Stay Wire', 'DEMO-SMA015', 800),
]
SITES = [
    ('Greater Accra', 'Ga West', 'AMASAMAN'),
    ('Greater Accra', 'Ga South', 'WEIJA'),
    ('Eastern', 'Yilo Krobo', 'SOMANYA'),
]
STATUSES = ['Completed', 'Partially Fulfilled', 'In Transit']


class Command(BaseCommand):
    help = "Seed (or clear) demo stock movements for the movement report."

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true')

    def handle(self, *args, **opts):
        if opts['clear']:
            return self._clear()
        self._seed()

    def _clear(self):
        n_mv = StockMovement.objects.filter(item__code__startswith='DEMO-').count()
        StockMovement.objects.filter(item__code__startswith='DEMO-').delete()
        MaterialOrder.objects.filter(request_code__startswith='REQ-DEMO-').delete()
        InventoryItem.objects.filter(code__startswith='DEMO-').delete()
        BillOfQuantity.objects.filter(package_number='PKG-DEMO').delete()
        Warehouse.objects.filter(code='DEMO').delete()
        self.stdout.write(self.style.SUCCESS(f"Cleared demo data ({n_mv} movements)."))

    @transaction.atomic
    def _seed(self):
        today = timezone.localdate()
        unit, _ = Unit.objects.get_or_create(name='pcs')
        wh, _ = Warehouse.objects.get_or_create(code='DEMO', defaults={'name': 'DEMO Store (test)'})

        # BoQ destinations + items + orders
        boqs = []
        for region, district, community in SITES:
            boqs.append(BillOfQuantity.objects.create(
                region=region, district=district, community=community,
                consultant='Demo Consult', contractor='Demo Contractor',
                package_number='PKG-DEMO', material_description='Mixed',
                item_code='DEMO', contract_quantity=1000.0))

        items = []
        for name, code, opening in MATERIALS:
            it = InventoryItem.objects.create(
                name=name, code=code, quantity=0, unit=unit, warehouse=wh)
            items.append((it, opening))

        order_seq = 1
        mv_count = 0

        def _stamp(mv, day_offset, hour):
            """Backdate a just-created movement so it lands on a past day."""
            when = timezone.now() - timedelta(days=day_offset)
            when = when.replace(hour=hour, minute=random.randint(0, 59))
            StockMovement.objects.filter(pk=mv.pk).update(created_at=when)

        for it, opening in items:
            # opening balance 12 days ago
            it.quantity = opening
            it.save(update_fields=['quantity'])
            mv = record_movement(it, 'opening', qty_in=opening, note='Demo opening balance')
            _stamp(mv, 12, 8); mv_count += 1

            # a receipt mid-period
            recv = random.randint(20, 80)
            it.quantity += recv
            it.save(update_fields=['quantity'])
            mv = record_movement(it, 'receipt', qty_in=recv, reference=it.code,
                                 note='Demo receipt from supplier')
            _stamp(mv, random.randint(7, 10), 10); mv_count += 1

            # two issues to sites, each with a demo order (destination + status)
            for _ in range(2):
                qty = random.randint(10, 40)
                if qty > it.quantity:
                    qty = max(1, it.quantity // 2)
                boq = random.choice(boqs)
                rc = f"REQ-DEMO-{order_seq:04d}"; order_seq += 1
                MaterialOrder.objects.create(
                    name=it.name, quantity=qty, code=it.code, unit=unit,
                    request_code=rc, status=random.choice(STATUSES),
                    linked_boq_item=boq)
                it.quantity -= qty
                it.save(update_fields=['quantity'])
                mv = record_movement(it, 'issue', qty_out=qty, reference=it.code,
                                     note=f"Release order {rc}")
                _stamp(mv, random.randint(1, 6), 13); mv_count += 1

            # a stock-count adjustment this week
            delta = random.choice([-3, -2, 2, 5])
            it.quantity = max(0, it.quantity + delta)
            it.save(update_fields=['quantity'])
            mv = record_movement(
                it, 'adjustment',
                qty_in=(delta if delta > 0 else 0), qty_out=(-delta if delta < 0 else 0),
                reference='Stock count', note='Demo physical count adjustment')
            _stamp(mv, random.randint(0, 3), 15); mv_count += 1

        # one inter-store transfer-out on the first item
        it0 = items[0][0]
        tq = 5
        it0.quantity = max(0, it0.quantity - tq)
        it0.save(update_fields=['quantity'])
        mv = record_movement(it0, 'transfer_out', qty_out=tq, reference='DEMO->MAIN',
                             note='Demo transfer to main store')
        _stamp(mv, 2, 11); mv_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {mv_count} demo movements across {len(items)} materials "
            f"and {len(boqs)} sites (last 12 days). "
            f"View: /reports/movement/?period=month  —  remove with --clear."))
