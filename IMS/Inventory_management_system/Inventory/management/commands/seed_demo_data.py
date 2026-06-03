"""
Wipe every domain table and repopulate with a realistic end-to-end dataset
so the whole system can be walked through in one session.

Touches:
  - ProjectType (registry the request form reads from)
  - Category / Unit / Warehouse / Supplier / SupplyContract / SupplyContractItem
  - InventoryItem (with real warehouse + stock)
  - Community (multi-region, multi-project)
  - Project + ProjectSite (in multiple regions so the Ghana map lights up)
  - BillOfQuantity (carries project_type → drives dashboard + map)
  - MaterialOrder (request + receipt orders in several lifecycle states)
  - ReleaseLetter (one signed, one awaiting signature)
  - MaterialTransport / SiteReceipt (so the full pipeline is exercised)

Auth tables (User, Group, Permission) are NEVER touched.

Usage:
    python manage.py seed_demo_data --confirm
    python manage.py seed_demo_data --confirm --user leslie
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth.models import User
from django.utils import timezone

from Inventory.models import (
    ProjectType, Category, Unit, Warehouse, InventoryItem,
    Supplier, MaterialOrder, ReleaseLetter, MaterialTransport,
    SiteReceipt, BillOfQuantity, Project, ProjectSite, SHEPCommunity,
)
from Inventory.models.suppliers import SupplyContract, SupplyContractItem


REGIONS = [
    ('Greater Accra', 'Ga East', 'Abokobi'),
    ('Greater Accra', 'Ga West', 'Amasaman'),
    ('Ashanti',       'Kumasi Metro', 'Asokore Mampong'),
    ('Ashanti',       'Ahafo Ano South', 'Mankranso'),
    ('Volta',         'Hohoe', 'Likpe Mate'),
    ('Eastern',       'Akwapim South', 'Aburi'),
    ('Western',       'Tarkwa-Nsuaem', 'Tarkwa'),
    ('Northern',      'Tamale Metro', 'Sagnarigu'),
    ('Central',       'Cape Coast Metro', 'Besease'),
    ('Bono',          'Sunyani Municipal', 'Goaso'),
]


class Command(BaseCommand):
    help = "Wipe & reseed every Inventory domain table for end-to-end demo."

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Required. Acknowledges destructive action.')
        parser.add_argument('--user', type=str, default=None,
                            help='Username to stamp as created_by / requestor.')

    def handle(self, *args, **opts):
        if not opts['confirm']:
            raise CommandError(
                "Refusing to run without --confirm. This deletes every row "
                "in MaterialOrder, ReleaseLetter, Transport, SiteReceipt, "
                "BoQ, Inventory, Projects, Communities, Suppliers, "
                "Contracts, and Warehouses."
            )

        actor = None
        if opts['user']:
            actor = User.objects.filter(username=opts['user']).first()
        if not actor:
            actor = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not actor:
            raise CommandError("No User in the database. Create one before seeding.")

        random.seed(42)

        with transaction.atomic():
            self._wipe()
            ptypes      = self._seed_project_types()
            units       = self._seed_units()
            categories  = self._seed_categories()
            warehouses  = self._seed_warehouses()
            suppliers   = self._seed_suppliers()
            inventory   = self._seed_inventory(units, categories, warehouses, actor)
            contracts   = self._seed_contracts(suppliers, inventory, warehouses, actor)
            communities = self._seed_communities(ptypes)
            projects    = self._seed_projects(actor)
            self._seed_project_sites(projects)
            boq_rows    = self._seed_boq(communities, inventory, actor)
            orders      = self._seed_material_orders(inventory, warehouses,
                                                     communities, ptypes, actor)
            self._seed_release_pipeline(orders, actor)
            self._seed_receipt_orders(inventory, suppliers, contracts, boq_rows, actor)

        self.stdout.write(self.style.SUCCESS(
            "\n=== Seed complete. Quick links: ===\n"
            "  /material-orders-officers/   (active requests)\n"
            "  /project-management/         (SHEP & Electrification Dashboard)\n"
            "  /ghana-map/                  (Regional Electrification Map)\n"
            "  /projects/                   (Project Management)\n"
            "  /bill-of-quantity/           (BoQ table — note project_type column)\n"
            "Run `python manage.py sync_sites_from_boq` once to push BoQ "
            "completion into the map's site status.\n"
        ))

    # ─────────────── teardown ───────────────

    def _wipe(self):
        # FK-safe order: dependents → parents.
        for model in [
            SiteReceipt, MaterialTransport, ReleaseLetter, MaterialOrder,
            BillOfQuantity, SupplyContractItem, SupplyContract,
            ProjectSite, Project, SHEPCommunity, InventoryItem,
            Supplier, Warehouse, Category, Unit, ProjectType,
        ]:
            n = model.objects.count()
            model.objects.all().delete()
            self.stdout.write(f"  wiped {n:5d} {model.__name__}")

    # ─────────────── seeders ───────────────

    def _seed_project_types(self):
        rows = [
            ('shep',         'SHEP',         'consultant', 10),
            ('cost_sharing', 'Cost Sharing', 'mp',         20),
            ('streetlights', 'Streetlights', 'mp',         30),
        ]
        out = {}
        for code, name, role, sort in rows:
            out[code] = ProjectType.objects.create(
                code=code, name=name, consignee_role=role,
                sort_order=sort, active=True,
                description=f"{name} programme (seeded).",
            )
        self.stdout.write(f"  + {len(out)} ProjectType")
        return out

    def _seed_units(self):
        names = ['Bags', 'Tons', 'Cubic Meters', 'Pieces', 'Metres', 'Kilograms']
        out = {n: Unit.objects.create(name=n) for n in names}
        self.stdout.write(f"  + {len(out)} Unit")
        return out

    def _seed_categories(self):
        names = ['Construction Materials', 'Steel Products', 'Aggregates',
                 'Electrical Hardware', 'Lighting', 'Cabling']
        out = {n: Category.objects.create(name=n) for n in names}
        self.stdout.write(f"  + {len(out)} Category")
        return out

    def _seed_warehouses(self):
        rows = [
            ('Accra Main',     'WH-ACC', 'Tema Industrial Area, Greater Accra'),
            ('Kumasi Central', 'WH-KUM', 'Suame Magazine, Kumasi'),
            ('Tamale North',   'WH-TAM', 'Tamale Industrial Zone, Northern Region'),
        ]
        out = {}
        for name, code, loc in rows:
            out[code] = Warehouse.objects.create(
                name=name, code=code, location=loc,
                contact_person='Stores Officer', contact_phone='+233200000000',
                is_active=True,
            )
        self.stdout.write(f"  + {len(out)} Warehouse")
        return out

    def _seed_suppliers(self):
        rows = [
            ('Acme Cement Ltd',        'SUP-ACME'),
            ('Beta Steel Works',       'SUP-BETA'),
            ('Gamma Cable Industries', 'SUP-GAMMA'),
            ('Delta Electricals',      'SUP-DELTA'),
        ]
        out = {}
        for name, code in rows:
            out[code] = Supplier.objects.create(
                name=name, code=code, contact_person='Sales Rep',
                contact_phone='+233300000000', is_active=True,
                rating=Decimal('4.20'),
            )
        self.stdout.write(f"  + {len(out)} Supplier")
        return out

    def _seed_inventory(self, units, categories, warehouses, actor):
        catalogue = [
            ('Portland Cement',                   'CEM-001',   'Construction Materials', 'Bags',         1200),
            ('Steel Reinforcement Bars',          'STEEL-001', 'Steel Products',         'Tons',          150),
            ('Sand',                              'SAND-001',  'Aggregates',             'Cubic Meters', 2200),
            ('Gravel',                            'GRAV-001',  'Aggregates',             'Cubic Meters', 1800),
            ('LV ABC Cable 4x70mm2',              'CAB-001',   'Cabling',                'Metres',       6500),
            ('Distribution Transformer 100 kVA',  'TX-001',    'Electrical Hardware',    'Pieces',         12),
            ('Wooden Pole 9m',                    'POL-001',   'Electrical Hardware',    'Pieces',        420),
            ('LED Streetlight 100W',              'LED-001',   'Lighting',               'Pieces',        180),
            ('Streetlight Pole 8m Galv.',         'SLP-001',   'Lighting',               'Pieces',         95),
        ]
        out = {}
        wh_keys = list(warehouses.keys())
        for i, (name, code, cat, unit, qty) in enumerate(catalogue):
            wh = warehouses[wh_keys[i % len(wh_keys)]]
            item = InventoryItem.objects.create(
                name=name, code=code, quantity=qty,
                category=categories[cat], unit=units[unit],
                warehouse=wh, user=actor,
            )
            out[code] = item
            # Same material in a second warehouse so the "any warehouse"
            # selection has multiple stock holders.
            if i % 3 == 0:
                wh2 = warehouses[wh_keys[(i + 1) % len(wh_keys)]]
                InventoryItem.objects.create(
                    name=name, code=code, quantity=qty // 3,
                    category=categories[cat], unit=units[unit],
                    warehouse=wh2, user=actor,
                )
        self.stdout.write(f"  + {InventoryItem.objects.count()} InventoryItem")
        return out

    def _seed_contracts(self, suppliers, inventory, warehouses, actor):
        contracts = {}
        today = timezone.now().date()
        specs = [
            ('SC-2026-001', 'Cement supply Q1-Q2',       'SUP-ACME',  [('CEM-001', 5000, '52.50')]),
            ('SC-2026-002', 'Steel rebar supply',        'SUP-BETA',  [('STEEL-001', 800, '4800.00')]),
            ('SC-2026-003', 'LV ABC cable framework',    'SUP-GAMMA', [('CAB-001', 20000, '38.20')]),
            ('SC-2026-004', 'Distribution transformers', 'SUP-DELTA', [('TX-001', 40, '32500.00')]),
        ]
        for number, title, supplier_code, items in specs:
            c = SupplyContract.objects.create(
                contract_number=number, title=title,
                supplier=suppliers[supplier_code], contract_type='framework',
                start_date=today, end_date=today + timedelta(days=365),
                total_estimated_value=Decimal('250000.00'), currency='GHS',
                status='active', created_by=actor,
            )
            for code, qty, rate in items:
                SupplyContractItem.objects.create(
                    contract=c, material=inventory[code],
                    quantity=Decimal(qty), unit_rate=Decimal(rate),
                    warehouse=list(warehouses.values())[0],
                )
            contracts[number] = c
        self.stdout.write(f"  + {len(contracts)} SupplyContract")
        return contracts

    def _seed_communities(self, ptypes):
        out = []
        cycle = ['shep', 'cost_sharing', 'streetlights']
        for i, (region, district, community) in enumerate(REGIONS):
            pt_code = cycle[i % 3]
            pkg = f"{pt_code[:4].upper()}-{region[:3].upper()}-{community[:3].upper()}"
            c = SHEPCommunity.objects.create(
                region=region, district=district, community=community,
                package_number=pkg if pt_code == 'shep' else '',
                project_type=ptypes[pt_code], is_active=True,
            )
            out.append(c)
        self.stdout.write(f"  + {len(out)} Community")
        return out

    def _seed_projects(self, actor):
        specs = [
            ('SHEP-4',          'SHEP Phase 4 Electrification', 'SHEP'),
            ('CS-AHA-01',       'Ahafo Ano Cost Sharing',       'Cost Sharing'),
            ('SL-EASTERN-2026', 'Eastern Streetlights 2026',    'Streetlights'),
        ]
        out = {}
        today = timezone.now().date()
        for code, name, ptype in specs:
            out[code] = Project.objects.create(
                code=code, name=name, project_type=ptype,
                description=f'{name} - seeded for demo.',
                phase='Phase 1', status='Active',
                project_manager=actor,
                consultant='Acme Engineers Ltd',
                contractor='Beta Power Works',
                start_date=today - timedelta(days=90),
                planned_end_date=today + timedelta(days=180),
                total_budget=Decimal('1500000.00'),
                created_by=actor,
            )
        self.stdout.write(f"  + {len(out)} Project")
        return out

    def _seed_project_sites(self, projects):
        statuses = ['Completed', 'Active', 'Planned', 'Active', 'Completed',
                    'Active', 'Planned', 'Active', 'Active', 'Planned']
        plist = list(projects.values())
        today = timezone.now().date()
        sites = []
        for i, (region, district, community) in enumerate(REGIONS):
            project = plist[i % len(plist)]
            sites.append(ProjectSite.objects.create(
                project=project, name=f'{community} Site',
                code=f'{project.code}-{community[:3].upper()}-{i:02d}',
                region=region, district=district, community=community,
                status=statuses[i],
                start_date=today - timedelta(days=60),
                planned_completion_date=today + timedelta(days=120),
            ))
        self.stdout.write(f"  + {len(sites)} ProjectSite")
        return sites

    def _seed_boq(self, communities, inventory, actor):
        rows = []
        boq_specs = [
            ('CEM-001',   500),
            ('STEEL-001',  40),
            ('CAB-001',  1500),
            ('TX-001',      2),
            ('POL-001',    35),
        ]
        for idx, c in enumerate(communities):
            pt_name = c.project_type.name
            bucket = idx % 3  # 0=complete, 1=in-progress, 2=not-started
            for code, qty in random.sample(boq_specs, k=3):
                item = inventory[code]
                contract = qty
                if bucket == 0:
                    received = qty
                elif bucket == 1:
                    received = max(1, int(qty * 0.35))
                else:
                    received = 0
                rows.append(BillOfQuantity.objects.create(
                    region=c.region, district=c.district, community=c.community,
                    consultant='Acme Engineers Ltd', contractor='Beta Power Works',
                    package_number=c.package_number or f"PKG-{c.community[:3].upper()}-{idx:02d}",
                    project_type=pt_name,
                    phase='SHEP-4' if pt_name == 'SHEP' else 'Phase 2',
                    material_description=item.name, item_code=item.code,
                    contract_quantity=contract, quantity_received=received,
                    user=actor,
                ))
        # Force one over-issuance so the dashboard's red badge shows.
        if rows:
            r = rows[0]
            r.quantity_received = r.contract_quantity + 5
            r.save(update_fields=['quantity_received'])
        self.stdout.write(f"  + {len(rows)} BillOfQuantity")
        return rows

    def _seed_material_orders(self, inventory, warehouses, communities, ptypes, actor):
        states = ['Pending', 'Approved', 'Completed']
        legacy_map = {'shep': 'SHEP', 'cost_sharing': 'COST', 'streetlights': 'STREET'}
        codes = ['CEM-001', 'STEEL-001', 'CAB-001', 'POL-001']
        orders = []
        for pt_code, ptype in ptypes.items():
            for state in states:
                item = inventory[random.choice(codes)]
                comm = next((c for c in communities if c.project_type_id == ptype.id), communities[0])
                orders.append(MaterialOrder.objects.create(
                    name=item.name, code=item.code, unit=item.unit,
                    category=item.category, warehouse=item.warehouse,
                    quantity=Decimal('50'),
                    processed_quantity=Decimal('50') if state == 'Completed' else Decimal('0'),
                    status=state, request_type='Release',
                    project_type=legacy_map.get(pt_code, 'SHEP'),
                    region=comm.region, district=comm.district, community=comm.community,
                    consultant='Acme Engineers Ltd', contractor='Beta Power Works',
                    package_number=comm.package_number or '',
                    requestor=actor.get_full_name() or actor.username,
                    is_urgent=(state == 'Pending'),
                    user=actor, created_by=actor,
                ))
        self.stdout.write(f"  + {len(orders)} MaterialOrder (Release)")
        return orders

    def _seed_release_pipeline(self, orders, actor):
        completed = [o for o in orders if o.status == 'Completed']
        if not completed:
            return
        order = completed[0]
        rl = ReleaseLetter.objects.create(
            request_code=order.request_code,
            title=f'Release for {order.name}',
            total_quantity=order.quantity,
            material_type='Other',
            project_type=order.project_type,
            workflow_status='approved',
            uploaded_by=actor,
            scan_uploaded_at=timezone.now(),
        )
        order.release_letter = rl
        order.save(update_fields=['release_letter'])

        # Second Completed order: letter generated but unsigned, so the
        # signed-copy prompt has a real example.
        if len(completed) > 1:
            second = completed[1]
            rl2 = ReleaseLetter.objects.create(
                request_code=second.request_code,
                title=f'Release for {second.name}',
                total_quantity=second.quantity,
                material_type='Other',
                project_type=second.project_type,
                workflow_status='memo_generated',
                uploaded_by=actor,
            )
            second.release_letter = rl2
            second.save(update_fields=['release_letter'])

        transport = MaterialTransport.objects.create(
            material_order=order, driver_name='Kwame Mensah',
            driver_phone='+233244000000',
            waybill_number=f'WB-{order.request_code[-6:]}',
            quantity=order.quantity, status='Delivered',
            date_dispatched=timezone.now() - timedelta(days=2),
            date_delivered=timezone.now() - timedelta(days=1),
        )
        SiteReceipt.objects.create(
            material_transport=transport,
            received_quantity=order.quantity,
            received_by=actor,
            condition='Good',
            notes='Delivered in full, signed by consultant on site.',
        )
        self.stdout.write("  + 2 ReleaseLetter, 1 MaterialTransport, 1 SiteReceipt")

    def _seed_receipt_orders(self, inventory, suppliers, contracts, boq_rows, actor):
        # 1. New Supply receipt against a real contract.
        item = inventory['STEEL-001']
        MaterialOrder.objects.create(
            name=item.name, code=item.code, unit=item.unit,
            category=item.category, warehouse=item.warehouse,
            quantity=Decimal('20'), processed_quantity=Decimal('0'),
            status='Approved', request_type='Receipt',
            receipt_category='new_supply',
            supplier=suppliers['SUP-BETA'],
            supply_contract=contracts['SC-2026-002'],
            requestor=actor.get_full_name() or actor.username,
            user=actor, created_by=actor,
        )
        # 2. Overissuance Return linked to the first BoQ row.
        if boq_rows:
            target_boq = boq_rows[0]
            item2 = inventory.get(target_boq.item_code) or inventory['CEM-001']
            MaterialOrder.objects.create(
                name=item2.name, code=item2.code, unit=item2.unit,
                category=item2.category, warehouse=item2.warehouse,
                quantity=Decimal('5'), processed_quantity=Decimal('0'),
                status='Approved', request_type='Receipt',
                receipt_category='overissuance_return',
                supplier=suppliers['SUP-ACME'],
                linked_boq_item=target_boq,
                requestor=actor.get_full_name() or actor.username,
                user=actor, created_by=actor,
                notes='Return offsetting over-issued BoQ line.',
            )
        self.stdout.write("  + 2 MaterialOrder (Receipt: 1 new supply, 1 overissuance return)")
