"""
seed_simulation — flush every domain table and rebuild a realistic, use-case
specific dataset so the whole MOEN-IMS pipeline can be simulated end to end.

Covers all three programmes with realistic Ghana electrification data:
  - SHEP          (Self-Help Electrification — consignee: consultant)
  - Cost Sharing  (consignee: Member of Parliament)
  - Streetlights  (consignee: Member of Parliament)

What it builds:
  - Demo role users (one per role group) so the approval chain can be walked
    across logins — Schedule Officer → Store Officer → Transport → Management,
    plus a Consultant account for the SHEP consignee.
  - Signatories (memo + release-letter defaults) so the release-letter wizard
    works without extra setup.
  - ProjectType / Unit / Category / Warehouse / Supplier / SupplyContract.
  - InventoryItem — real electrification materials (poles, ACSR conductor,
    distribution transformers, insulators, meters, LV ABC cable, streetlights)
    plus civil items, stocked across warehouses.
  - Members of Parliament + a Project Consultant (consignee resolution).
  - Communities across several regions (SHEP packages + MP-linked CS/SL),
    with GPS coordinates so the Ghana map lights up.
  - Projects + ProjectSites, BillOfQuantity (complete / in-progress /
    not-started, incl. one over-issuance).
  - MaterialOrders (Release) in every lifecycle state per programme.
  - Release pipeline: release letters in draft / memo_generated / approved /
    released states, with transports (waybills) and site receipts.
  - Receipt orders: a new-supply receipt against a contract and an
    over-issuance return linked to a BoQ line.

Auth users you already have (e.g. your own login) are NEVER deleted. Existing
domain rows ARE wiped.

Usage:
    python manage.py seed_simulation --confirm
    python manage.py seed_simulation --confirm --user leslie
    python manage.py seed_simulation --confirm --password 'MyDemoPass1!'

After seeding, run once for full role permissions + map status:
    python manage.py setup_groups
    python manage.py sync_sites_from_boq
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.auth.models import User, Group
from django.utils import timezone

from Inventory.models import (
    ProjectType, Category, Unit, Warehouse, InventoryItem,
    Supplier, MaterialOrder, ReleaseLetter, MaterialTransport,
    SiteReceipt, BillOfQuantity, Project, ProjectSite, SHEPCommunity,
    MemberOfParliament, ProjectConsultant, Signatory,
)
from Inventory.models.access_rate import MeterInstallation
from Inventory.models.suppliers import (
    SupplyContract, SupplyContractItem, SupplierInvoice, SupplierInvoiceItem,
)


# region, district, community, project_type_code, package_number, (lat, lon)
COMMUNITIES = [
    ('Oti',           'Krachi East',        'Dambai',       'shep',        'SHEP4-OTI-DAM-01', (8.0686, 0.1786)),
    ('Volta',         'Hohoe',              'Likpe Mate',   'shep',        'SHEP4-VOL-LKM-02', (7.1550, 0.4740)),
    ('Northern',      'Savelugu',           'Pong-Tamale',  'shep',        'SHEP5-NOR-PGT-03', (9.6500, -0.8200)),
    ('Bono East',     'Nkoranza North',     'Busunya',      'shep',        'SHEP5-BNE-BSY-04', (7.6500, -1.6800)),
    ('Ashanti',       'Ahafo Ano South',    'Mankranso',    'cost_sharing', 'CS-ASH-MKR-01',   (6.7500, -2.0500)),
    ('Eastern',       'Kwahu West',         'Nkawkaw',      'cost_sharing', 'CS-EAS-NKW-02',   (6.5500, -0.7700)),
    ('Western',       'Wassa East',         'Daboase',      'cost_sharing', 'CS-WES-DAB-03',   (5.2000, -1.7300)),
    ('Greater Accra', 'Ga West',            'Amasaman',     'streetlights', 'SL-GAC-AMA-01',   (5.7030, -0.3030)),
    ('Central',       'Gomoa East',         'Potsin',       'streetlights', 'SL-CEN-POT-02',   (5.5200, -0.6300)),
    ('Upper East',    'Kassena Nankana',    'Navrongo',     'streetlights', '',                (10.8950, -1.0920)),
]

# Members of Parliament for the Cost Sharing / Streetlights constituencies.
# Names are illustrative (not real office-holders) — purely for simulation.
MPS = [
    ('Hon.', 'Ama Boateng',    'Ahafo Ano South',  'Ashanti',       'Ahafo Ano South'),
    ('Hon.', 'Kojo Mensah',    'Kwahu West',       'Eastern',       'Kwahu West'),
    ('Hon.', 'Efua Sarpong',   'Wassa East',       'Western',       'Wassa East'),
    ('Hon.', 'Yaw Antwi',      'Ga West',          'Greater Accra', 'Ga West'),
    ('Hon.', 'Abena Owusu',    'Gomoa East',       'Central',       'Gomoa East'),
    ('Hon.', 'Salifu Adamu',   'Navrongo Central', 'Upper East',    'Kassena Nankana'),
]

# Demo users, one per role group (plus your own preserved login).
DEMO_USERS = [
    ('schedule.officer', 'Selorm',  'Adjei',   'Schedule Officers', True),
    ('store.officer',    'Kwabena', 'Osei',    'Store Officers',     True),
    ('stores.manager',   'Adwoa',   'Nyarko',  'Stores Management',  True),
    ('transport.officer','Musah',   'Iddrisu', 'Transport Officers', True),
    ('management.lead',  'Comfort', 'Asante',  'Management',         True),
    ('consultant.shep',  'Daniel',  'Quarshie','Consultants',        False),
]


class Command(BaseCommand):
    help = "Flush domain data and rebuild a realistic SHEP / Cost Sharing / Streetlights simulation."

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Required. Acknowledges that all domain data is deleted.')
        parser.add_argument('--user', type=str, default=None,
                            help='Existing username to stamp as creator / requestor.')
        parser.add_argument('--password', type=str, default='Moen@2026',
                            help='Password set on the seeded demo role users.')

    def handle(self, *args, **opts):
        if not opts['confirm']:
            raise CommandError(
                "Refusing to run without --confirm. This deletes every domain "
                "row (orders, release letters, transports, receipts, BoQ, "
                "inventory, projects, communities, suppliers, contracts, "
                "warehouses, signatories, MPs, consultants). Auth users are kept."
            )

        actor = None
        if opts['user']:
            actor = User.objects.filter(username=opts['user']).first()
        if not actor:
            actor = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not actor:
            raise CommandError("No User exists. Create a superuser before seeding.")

        self.password = opts['password']
        random.seed(42)

        # Per-stage commits (no outer transaction) keep SQLite happy on
        # network-mounted volumes — large single commits can raise I/O errors.
        users       = self._seed_users()
        self._seed_signatories()
        self._wipe()
        ptypes      = self._seed_project_types()
        units       = self._seed_units()
        categories  = self._seed_categories()
        warehouses  = self._seed_warehouses()
        suppliers   = self._seed_suppliers()
        inventory   = self._seed_inventory(units, categories, warehouses, actor)
        contracts   = self._seed_contracts(suppliers, inventory, warehouses, actor)
        mps         = self._seed_mps()
        self._seed_consultant(users)
        communities = self._seed_communities(ptypes, mps)
        projects    = self._seed_projects(actor)
        self._seed_project_sites(projects)
        boq_rows    = self._seed_boq(communities, inventory, actor)
        self._seed_progress(communities, actor)
        orders      = self._seed_material_orders(inventory, communities, ptypes, users, actor)
        self._seed_release_pipeline(orders, users, actor)
        self._seed_receipt_orders(inventory, suppliers, contracts, boq_rows, actor)

        self.stdout.write(self.style.SUCCESS(
            "\n=== Simulation seeded. ===\n"
            f"  Demo users (password: {self.password}):\n"
            "    schedule.officer  store.officer  stores.manager\n"
            "    transport.officer management.lead consultant.shep\n"
            "  Run `python manage.py setup_groups` for full role permissions,\n"
            "  then `python manage.py sync_sites_from_boq` to light up the map.\n"
            "  Walk it: /material-orders-officers/  /project-management/\n"
            "           /ghana-map/  /bill-of-quantity/  /release-letters/\n"
        ))

    # ─────────────── auth (non-destructive) ───────────────

    def _seed_users(self):
        out = {}
        for username, first, last, group_name, is_staff in DEMO_USERS:
            u, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first, 'last_name': last,
                    'email': f'{username}@moen.gov.gh', 'is_staff': is_staff,
                },
            )
            u.first_name, u.last_name, u.is_staff = first, last, is_staff
            u.set_password(self.password)
            u.save()
            group, _ = Group.objects.get_or_create(name=group_name)
            u.groups.add(group)
            out[username] = u
        self.stdout.write(f"  + {len(out)} demo users (roles assigned)")
        return out

    def _seed_signatories(self):
        Signatory.objects.all().delete()
        Signatory.objects.create(
            name='Ing. Lawrence Ofori-Addo', title='CHIEF DIRECTOR',
            is_default_for_release_memo=True, signs_for='Ministry of Energy', active=True,
        )
        Signatory.objects.create(
            name='Ing. Patience Adjabeng', title='DIRECTOR, POWER',
            is_default_for_release_letter=True, signs_for='Power Directorate', active=True,
        )
        Signatory.objects.create(
            name='Mr. Eric Tetteh', title='AG. DIRECTOR, FINANCE',
            is_default_for_payment_memo=True, signs_for='Finance Directorate', active=True,
        )
        self.stdout.write("  + 3 Signatory")

    # ─────────────── teardown ───────────────

    def _wipe(self):
        for model in [
            SiteReceipt, MaterialTransport, ReleaseLetter, MaterialOrder,
            BillOfQuantity, SupplierInvoiceItem, SupplierInvoice,
            SupplyContractItem, SupplyContract,
            ProjectSite, Project, MeterInstallation, SHEPCommunity,
            ProjectConsultant, MemberOfParliament, InventoryItem,
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
                description=f"{name} programme.",
            )
        self.stdout.write(f"  + {len(out)} ProjectType")
        return out

    def _seed_units(self):
        names = ['Pieces', 'Metres', 'Set', 'Coil', 'Bags', 'Cubic Meters', 'Tons']
        out = {n: Unit.objects.create(name=n) for n in names}
        self.stdout.write(f"  + {len(out)} Unit")
        return out

    def _seed_categories(self):
        names = ['Poles & Structures', 'Conductors & Cables', 'Transformers',
                 'Line Hardware & Insulators', 'Metering', 'Lighting',
                 'Civil / Construction']
        out = {n: Category.objects.create(name=n) for n in names}
        self.stdout.write(f"  + {len(out)} Category")
        return out

    def _seed_warehouses(self):
        rows = [
            ('Accra Main Stores',  'WH-ACC', 'Tema Industrial Area, Greater Accra'),
            ('Kumasi Central',     'WH-KUM', 'Suame Magazine, Kumasi, Ashanti'),
            ('Tamale North',       'WH-TAM', 'Tamale Industrial Zone, Northern'),
            ('Takoradi Coastal',   'WH-TAK', 'Sekondi-Takoradi, Western'),
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
            ('Volta Electricals Ltd',      'SUP-VOLTA'),
            ('Ashanti Conductors Ltd',     'SUP-ASH'),
            ('Tema Transformer Works',     'SUP-TTW'),
            ('Northern Line Hardware Co.', 'SUP-NLH'),
            ('Coastal Cement & Aggregates','SUP-CCA'),
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
        # name, code, category, unit, qty
        catalogue = [
            ('Wooden Pole 9m',                       'POL-WD-9',    'Poles & Structures',         'Pieces',         600),
            ('Concrete Pole 11m',                    'POL-CN-11',   'Poles & Structures',         'Pieces',         240),
            ('ACSR Conductor 50mm2 (Rabbit)',        'CON-ACSR-50', 'Conductors & Cables',        'Metres',       42000),
            ('ACSR Conductor 75mm2 (Raccoon)',       'CON-ACSR-75', 'Conductors & Cables',        'Metres',       28000),
            ('LV ABC Cable 4x70mm2',                 'CAB-ABC-70',  'Conductors & Cables',        'Metres',       15000),
            ('Distribution Transformer 50 kVA',      'TX-50',       'Transformers',               'Pieces',          18),
            ('Distribution Transformer 100 kVA',     'TX-100',      'Transformers',               'Pieces',          10),
            ('Distribution Transformer 200 kVA',     'TX-200',      'Transformers',               'Pieces',           6),
            ('11kV Pin Insulator',                   'INS-PIN-11',  'Line Hardware & Insulators', 'Pieces',        1500),
            ('11kV Disc Insulator',                  'INS-DISC-11', 'Line Hardware & Insulators', 'Pieces',        1200),
            ('Stay Wire Set',                        'STAY-SET',    'Line Hardware & Insulators', 'Set',            800),
            ('Cross-arm Galvanized',                 'XARM-GLV',    'Line Hardware & Insulators', 'Pieces',        1000),
            ('Single-phase Credit Meter',            'MTR-1P',      'Metering',                   'Pieces',        3000),
            ('LED Streetlight 100W',                 'LED-100',     'Lighting',                   'Pieces',         350),
            ('Streetlight Pole 8m Galvanized',       'SLP-8',       'Lighting',                   'Pieces',         180),
            ('Portland Cement',                      'CEM-001',     'Civil / Construction',       'Bags',          2000),
            ('Sharp Sand',                           'SAND-001',    'Civil / Construction',       'Cubic Meters',  1500),
        ]
        out = {}
        wh_keys = list(warehouses.keys())
        for i, (name, code, cat, unit, qty) in enumerate(catalogue):
            wh = warehouses[wh_keys[i % len(wh_keys)]]
            out[code] = InventoryItem.objects.create(
                name=name, code=code, quantity=qty,
                category=categories[cat], unit=units[unit],
                warehouse=wh, user=actor,
            )
            # Hold high-volume lines in a second warehouse too.
            if i % 4 == 0:
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
            ('SC-2026-001', 'ACSR conductor framework',  'SUP-ASH',   [('CON-ACSR-50', 80000, '21.40'), ('CON-ACSR-75', 50000, '32.10')]),
            ('SC-2026-002', 'Distribution transformers', 'SUP-TTW',   [('TX-50', 40, '28500.00'), ('TX-100', 25, '46500.00')]),
            ('SC-2026-003', 'LV ABC cable supply',       'SUP-VOLTA', [('CAB-ABC-70', 40000, '38.20')]),
            ('SC-2026-004', 'Line hardware & insulators','SUP-NLH',   [('INS-PIN-11', 4000, '12.50'), ('STAY-SET', 2000, '85.00')]),
        ]
        for number, title, supplier_code, items in specs:
            c = SupplyContract.objects.create(
                contract_number=number, title=title,
                supplier=suppliers[supplier_code], contract_type='framework',
                start_date=today, end_date=today + timedelta(days=365),
                total_estimated_value=Decimal('2500000.00'), currency='GHS',
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

    def _seed_mps(self):
        out = {}
        for title, name, constituency, region, district in MPS:
            out[district] = MemberOfParliament.objects.create(
                title=title, name=name, constituency=constituency,
                region=region, district=district,
                email=f"{name.split()[0].lower()}.mp@parliament.gh",
                phone='+233500000000', active=True,
            )
        self.stdout.write(f"  + {len(out)} MemberOfParliament")
        return out

    def _seed_consultant(self, users):
        ProjectConsultant.objects.create(
            name='Daniel Quarshie', firm='Sunburst Power Consult Ltd',
            region='Oti', district='Krachi East',
            contact_email='consultant.shep@moen.gov.gh', contact_phone='+233244111222',
            active=True, user=users.get('consultant.shep'),
        )
        self.stdout.write("  + 1 ProjectConsultant (linked to consultant.shep)")

    def _seed_communities(self, ptypes, mps):
        out = []
        for region, district, community, pt_code, pkg, (lat, lon) in COMMUNITIES:
            mp = mps.get(district) if pt_code != 'shep' else None
            c = SHEPCommunity.objects.create(
                region=region, district=district, community=community,
                package_number=pkg, project_type=ptypes[pt_code],
                member_of_parliament=mp,
                latitude=Decimal(str(lat)), longitude=Decimal(str(lon)),
                gps_coordinates=f"{lat},{lon}", is_active=True,
            )
            out.append(c)
        self.stdout.write(f"  + {len(out)} Community")
        return out

    def _seed_projects(self, actor):
        specs = [
            ('SHEP-4',          'SHEP Phase 4 Electrification', 'SHEP'),
            ('SHEP-5',          'SHEP Phase 5 Electrification', 'SHEP'),
            ('CS-2026',         'Cost Sharing Programme 2026',  'Cost Sharing'),
            ('SL-2026',         'National Streetlights 2026',   'Streetlights'),
        ]
        out = {}
        today = timezone.now().date()
        for code, name, ptype in specs:
            out[code] = Project.objects.create(
                code=code, name=name, project_type=ptype,
                description=f'{name}.',
                phase='Phase 1', status='Active',
                project_manager=actor,
                consultant='Sunburst Power Consult Ltd',
                contractor='Volta Power Contractors Ltd',
                start_date=today - timedelta(days=120),
                planned_end_date=today + timedelta(days=240),
                total_budget=Decimal('4500000.00'),
                created_by=actor,
            )
        self.stdout.write(f"  + {len(out)} Project")
        return out

    def _seed_project_sites(self, projects):
        statuses = ['Completed', 'Active', 'Active', 'Planned', 'Active',
                    'Active', 'Planned', 'Completed', 'Active', 'Planned']
        plist = list(projects.values())
        today = timezone.now().date()
        sites = []
        for i, (region, district, community, *_rest) in enumerate(COMMUNITIES):
            project = plist[i % len(plist)]
            sites.append(ProjectSite.objects.create(
                project=project, name=f'{community} Site',
                code=f'{project.code}-{community[:3].upper()}-{i:02d}',
                region=region, district=district, community=community,
                status=statuses[i],
                start_date=today - timedelta(days=90),
                planned_completion_date=today + timedelta(days=150),
            ))
        self.stdout.write(f"  + {len(sites)} ProjectSite")
        return sites

    def _seed_boq(self, communities, inventory, actor):
        rows = []
        # A full electrification BoQ per community: HT + LV poles, HT + LV
        # conductor, transformers, meters — each carrying an explicit
        # voltage_class so the targets pull is exact. (code, qty, voltage_class)
        boq_specs = [
            ('POL-CN-11',     30,  'HT'),     # HT poles
            ('POL-WD-9',      120, 'LV'),     # LV poles
            ('CON-ACSR-75',   8000, 'HT'),    # HT conductor (m)
            ('CAB-ABC-70',    3500, 'LV'),    # LV conductor (m)
            ('TX-50',         3,   'XFMR'),   # transformers
            ('MTR-1P',        450, 'METER'),  # service connections
        ]
        for idx, c in enumerate(communities):
            pt_name = c.project_type.name
            bucket = idx % 3  # 0=complete, 1=in-progress, 2=not-started (delivery)
            for code, qty, vclass in boq_specs:
                item = inventory[code]
                if bucket == 0:
                    received = qty
                elif bucket == 1:
                    received = max(1, int(qty * 0.4))
                else:
                    received = 0
                rows.append(BillOfQuantity.objects.create(
                    region=c.region, district=c.district, community=c.community,
                    consultant='Sunburst Power Consult Ltd',
                    contractor='Volta Power Contractors Ltd',
                    package_number=c.package_number or f"PKG-{c.community[:3].upper()}-{idx:02d}",
                    project_type=pt_name,
                    phase='SHEP-4' if pt_name == 'SHEP' else 'Phase 2',
                    material_description=item.name, item_code=item.code,
                    voltage_class=vclass,
                    contract_quantity=qty, quantity_received=received,
                    user=actor,
                ))
        # Force one over-issuance so the dashboard red badge + return flow show.
        # (Delivery reconciliation only — does NOT affect progress targets.)
        if rows:
            r = rows[0]
            r.quantity_received = r.contract_quantity + 8
            r.save(update_fields=['quantity_received'])
        self.stdout.write(f"  + {len(rows)} BillOfQuantity (voltage-classed, 1 over-issued)")
        return rows

    def _seed_progress(self, communities, actor):
        """Pull targets from BoQ, then set realistic site works so the
        5-stage completion varies across communities."""
        from Inventory.services.community_progress import (
            pull_targets_from_boq, recalc_site_progress_percent,
        )
        from decimal import Decimal
        pulled = 0
        sites_done = 0
        for idx, c in enumerate(communities):
            pull_targets_from_boq(c, actor, apply=True)
            pulled += 1
            sites = ProjectSite.objects.filter(
                region__iexact=c.region, district__iexact=c.district,
                community__iexact=c.community,
            )
            bucket = idx % 3  # 0=complete, 1=partial, 2=not-started (works)
            for s in sites:
                if bucket == 0:
                    s.ht_poles_erected = s.ht_poles_dressed = s.ht_poles_strung = 30
                    s.lv_poles_erected = s.lv_poles_dressed = s.lv_poles_strung = 120
                    s.ht_conductor_strung_m = Decimal('8000')
                    s.lv_conductor_strung_m = Decimal('3500')
                    s.transformers_installed = s.transformers_commissioned = 3
                    s.meters_1ph_installed, s.meters_3ph_installed = 400, 50
                    s.works_status = 'Commissioned'
                elif bucket == 1:
                    s.ht_poles_erected, s.ht_poles_dressed, s.ht_poles_strung = 30, 20, 10
                    s.lv_poles_erected, s.lv_poles_dressed, s.lv_poles_strung = 120, 60, 30
                    s.ht_conductor_strung_m = Decimal('3000')
                    s.lv_conductor_strung_m = Decimal('1200')
                    s.transformers_installed, s.transformers_commissioned = 2, 1
                    s.meters_1ph_installed, s.meters_3ph_installed = 120, 10
                    s.works_status = 'In Progress'
                else:
                    s.works_status = 'Planned'
                s.poles_erected = (s.ht_poles_erected or 0) + (s.lv_poles_erected or 0)
                s.conductor_laid_m = (s.ht_conductor_strung_m or 0) + (s.lv_conductor_strung_m or 0)
                s.progress_updated_at = timezone.now()
                s.progress_updated_by = actor
                s.save()
                recalc_site_progress_percent(s, community=c, save=True)
                sites_done += 1
        self.stdout.write(f"  + targets pulled for {pulled} communities, "
                          f"works set on {sites_done} sites (derived %)")

    def _seed_material_orders(self, inventory, communities, ptypes, users, actor):
        # Lifecycle states to exercise the board + fulfilment buttons.
        states = ['Pending', 'Approved', 'In Transit', 'Completed']
        legacy_map = {'shep': 'SHEP', 'cost_sharing': 'COST', 'streetlights': 'STREET'}
        # Items that make sense per programme.
        items_by_pt = {
            'shep':         ['POL-WD-9', 'CON-ACSR-50', 'TX-50', 'MTR-1P'],
            'cost_sharing': ['POL-CN-11', 'CAB-ABC-70', 'TX-100'],
            'streetlights': ['LED-100', 'SLP-8'],
        }
        sch = users.get('schedule.officer')
        orders = []
        for pt_code, ptype in ptypes.items():
            comms = [c for c in communities if c.project_type_id == ptype.id] or communities
            for i, state in enumerate(states):
                code = items_by_pt[pt_code][i % len(items_by_pt[pt_code])]
                item = inventory[code]
                comm = comms[i % len(comms)]
                qty = Decimal('50')
                orders.append(MaterialOrder.objects.create(
                    name=item.name, code=item.code, unit=item.unit,
                    category=item.category, warehouse=item.warehouse,
                    quantity=qty,
                    processed_quantity=qty if state == 'Completed' else Decimal('0'),
                    status=state, request_type='Release',
                    project_type=legacy_map.get(pt_code, 'SHEP'),
                    region=comm.region, district=comm.district, community=comm.community,
                    consultant='Sunburst Power Consult Ltd',
                    contractor='Volta Power Contractors Ltd',
                    package_number=comm.package_number or '',
                    requestor=(sch.get_full_name() if sch else actor.username),
                    is_urgent=(state == 'Pending'),
                    user=actor, created_by=actor,
                ))
        self.stdout.write(f"  + {len(orders)} MaterialOrder (Release, all states)")
        return orders

    def _seed_release_pipeline(self, orders, users, actor):
        sch = users.get('schedule.officer') or actor
        completed = [o for o in orders if o.status == 'Completed']
        in_transit = [o for o in orders if o.status == 'In Transit']
        approved = [o for o in orders if o.status == 'Approved']

        made_rl = 0
        made_tx = 0
        made_rcpt = 0

        # 1. Fully released letters (approved + signed scan) for Completed
        #    orders, each with a delivered transport + site receipt.
        for order in completed:
            rl = ReleaseLetter.objects.create(
                request_code=order.request_code,
                title=f'Release of {order.name} — {order.community}'[:200],
                total_quantity=order.quantity, material_type='Other',
                project_type=order.project_type,
                workflow_status='released',
                uploaded_by=sch, scan_uploaded_at=timezone.now(),
            )
            order.release_letter = rl
            order.save(update_fields=['release_letter'])
            made_rl += 1

            tx = MaterialTransport.objects.create(
                material_order=order, driver_name='Kwame Mensah',
                driver_phone='+233244000000',
                waybill_number=f'WB-{order.request_code[-6:]}',
                quantity=order.quantity, status='Delivered',
                date_dispatched=timezone.now() - timedelta(days=3),
                date_delivered=timezone.now() - timedelta(days=1),
            )
            made_tx += 1
            SiteReceipt.objects.create(
                material_transport=tx, received_quantity=order.quantity,
                received_by=actor, condition='Good',
                notes='Delivered in full; signed by consultant on site.',
            )
            made_rcpt += 1

        # 2. In-transit orders: signed letter on file + dispatched waybill,
        #    not yet received (awaiting site receipt).
        for order in in_transit:
            rl = ReleaseLetter.objects.create(
                request_code=order.request_code,
                title=f'Release of {order.name} — {order.community}'[:200],
                total_quantity=order.quantity, material_type='Other',
                project_type=order.project_type,
                workflow_status='approved',
                uploaded_by=sch, scan_uploaded_at=timezone.now(),
            )
            order.release_letter = rl
            order.save(update_fields=['release_letter'])
            made_rl += 1
            MaterialTransport.objects.create(
                material_order=order, driver_name='Yakubu Sule',
                driver_phone='+233209000000',
                waybill_number=f'WB-{order.request_code[-6:]}',
                quantity=order.quantity, status='In Transit',
                date_dispatched=timezone.now() - timedelta(hours=8),
            )
            made_tx += 1

        # 3. Approved orders: letter generated but unsigned — the "upload the
        #    signed copy" prompt has a real example to act on.
        for order in approved:
            rl = ReleaseLetter.objects.create(
                request_code=order.request_code,
                title=f'Release of {order.name} — {order.community}'[:200],
                total_quantity=order.quantity, material_type='Other',
                project_type=order.project_type,
                workflow_status='memo_generated',
                uploaded_by=sch,
            )
            order.release_letter = rl
            order.save(update_fields=['release_letter'])
            made_rl += 1

        self.stdout.write(
            f"  + {made_rl} ReleaseLetter, {made_tx} MaterialTransport, "
            f"{made_rcpt} SiteReceipt"
        )

    def _seed_receipt_orders(self, inventory, suppliers, contracts, boq_rows, actor):
        # New-supply receipt against a real contract.
        item = inventory['TX-50']
        MaterialOrder.objects.create(
            name=item.name, code=item.code, unit=item.unit,
            category=item.category, warehouse=item.warehouse,
            quantity=Decimal('5'), processed_quantity=Decimal('0'),
            status='Approved', request_type='Receipt',
            receipt_category='new_supply',
            supplier=suppliers['SUP-TTW'],
            supply_contract=contracts['SC-2026-002'],
            requestor=actor.get_full_name() or actor.username,
            user=actor, created_by=actor,
        )
        # Over-issuance return linked to the over-issued BoQ row.
        if boq_rows:
            target = boq_rows[0]
            item2 = inventory.get(target.item_code) or inventory['POL-WD-9']
            MaterialOrder.objects.create(
                name=item2.name, code=item2.code, unit=item2.unit,
                category=item2.category, warehouse=item2.warehouse,
                quantity=Decimal('8'), processed_quantity=Decimal('0'),
                status='Approved', request_type='Receipt',
                receipt_category='overissuance_return',
                supplier=suppliers['SUP-NLH'],
                linked_boq_item=target,
                requestor=actor.get_full_name() or actor.username,
                user=actor, created_by=actor,
                notes='Return offsetting the over-issued BoQ line.',
            )
        self.stdout.write("  + 2 MaterialOrder (Receipt: new supply + over-issuance return)")
