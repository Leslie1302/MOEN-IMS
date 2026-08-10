"""
Flush the domain tables and reseed a consistent testbed for the release workflow.

Why this exists alongside `seed_demo_data`
------------------------------------------
`seed_demo_data` builds a broad demo of the whole system. This builds a narrow,
*internally consistent* dataset for walking the release workflow end to end, and
it fixes the one thing that made the existing data untestable:

**Region strings did not agree across tables.** Before this command:

    Community / ProjectSite   'UPPER EAST'      (real pilot import, uppercase)
    BillOfQuantity            'Greater Accra'   (seed_demo_data, title case)
    AreaRegion                'Upper East'      (title case)
    Region                    (empty table)

The request form builds its region/district/package dropdowns from
`BillOfQuantity` distinct values (`forms/orders.py`), while communities and
project sites carry the uppercase strings. So the form offered regions that no
community matched, and a BoQ line could never reconcile against a community.
Area scoping survives it only because `consignee_resolver` uses `iexact`.

This command therefore picks **one canonical casing — UPPERCASE — for every
region, district and community string**, and writes it to Community,
ProjectSite, BillOfQuantity, MaterialOrder and AreaRegion alike. `Area.name`
stays human-readable because it is a label, not a join key.

What it does NOT touch
----------------------
* **auth** — User, Group, Permission. Your test users survive.
* **Letterhead** — the drag-to-calibrate insets are real work; reseeding them
  would silently change every document's margins.
* **Profile, MicrosoftCredentials, PerformanceConfig, RolePerformanceTarget** —
  attached to users or to configuration, not to test data.

Usage
-----
    python manage.py seed_release_testbed --confirm
    python manage.py seed_release_testbed --confirm --password 'Testing123!'

`ponytail:` the canonical geography below is a curated slice — 8 regions, 2
districts each, 2 communities each — not all 16 regions and 261 districts. It is
sized to be readable in a dropdown while still spanning enough areas to exercise
region-scoped consultant authorisation. Swap in the full import when you need
the map populated for a demo rather than for a workflow test.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


# ── Canonical geography ──────────────────────────────────────────────────────
#
# UPPERCASE, because that is what the real pilot import produced and what the
# 99 communities already on the system used. Region → district → communities.
GEOGRAPHY = [
    ('GREATER ACCRA', [
        ('GA EAST',        ['ABOKOBI', 'DANFA']),
        ('GA WEST',        ['AMASAMAN', 'POKUASE']),
    ]),
    ('ASHANTI', [
        ('KUMASI METRO',   ['ASOKORE MAMPONG', 'OFORIKROM']),
        ('AHAFO ANO SOUTH', ['MANKRANSO', 'SABRONUM']),
    ]),
    ('EASTERN', [
        ('ABUAKWA NORTH',  ['KUKURANTUMI', 'OSIEM']),
        ('AKWAPIM SOUTH',  ['ABURI', 'NSAWAM']),
    ]),
    ('VOLTA', [
        ('HOHOE',          ['LIKPE MATE', 'GBI WEGBE']),
        ('KETA',           ['ANLOGA', 'DZELUKOPE']),
    ]),
    ('NORTHERN', [
        ('TAMALE METRO',   ['SAGNARIGU', 'KUKUO']),
        ('SAVELUGU',       ['DIARE', 'PONG TAMALE']),
    ]),
    ('UPPER EAST', [
        ('BOLGATANGA',     ['SUMBRUNGU', 'ZUARUNGU']),
        ('BAWKU WEST',     ['ZEBILLA', 'TILLI']),
    ]),
    ('WESTERN', [
        ('TARKWA-NSUAEM',  ['TARKWA', 'NSUAEM']),
        ('AHANTA WEST',    ['AGONA NKWANTA', 'DIXCOVE']),
    ]),
    ('BONO', [
        ('SUNYANI EAST',   ['ABESIM', 'YAWKROM']),
        ('WENCHI',         ['AWISA', 'DROBO']),
    ]),
]

# Operational areas. `Area.name` is a label; `AreaRegion.region` is a join key
# and must match GEOGRAPHY exactly.
AREAS = [
    ('Greater Accra & Eastern',  ['GREATER ACCRA', 'EASTERN']),
    ('Ashanti',                  ['ASHANTI']),
    ('Volta & Oti',              ['VOLTA']),
    ('Northern & Savannah',      ['NORTHERN']),
    ('Upper East',               ['UPPER EAST']),
    ('Western & Western North',  ['WESTERN']),
    ('Ahafo, Bono & Bono East',  ['BONO']),
]

# Real MOEN material codes and names, so the BoQ and the schedule read like the
# Ministry's own paperwork rather than like CEM-001.
MATERIALS = [
    ('SMA015', 'Stay Wire',                         'm',   40000),
    ('SMS001', 'Stay Equipment C/W Accessories',    'set', 12000),
    ('SMA001', 'LV Stay Insulator',                 'pcs', 15000),
    ('SMA002', 'HT Stay Insulator',                 'pcs',  9000),
    ('SMA004', 'Guy Grip (Preform) 50Sqmm',         'pcs', 11000),
    ('SMP001', '11m Concrete Pole',                 'pcs',  4200),
    ('SMC001', 'ABC Cable 4x35mm2',                 'm',   68000),
    ('SMT001', '50kVA Distribution Transformer',    'pcs',   180),
    ('SMF001', '30A Single Phase Fuse Unit',        'pcs',  7600),
    ('SMM001', 'Single Phase Meter',                'pcs', 22000),
]

CATEGORIES = ['Conductors & Cables', 'Poles & Structures', 'Transformers',
              'Metering', 'Stay & Accessories']

PROJECT_TYPES = [
    ('shep',                  'SHEP',                  'consultant', True,  10),
    ('cost_sharing',          'Cost Sharing',          'mp',         True,  20),
    ('streetlights',          'Streetlights',          'mp',         True,  30),
    ('turnkey',               'Turnkey',               'other',      False, 90),
    ('china_water',           'China Water',           'other',      False, 91),
    ('other_electrification', 'Other Electrification', 'other',      False, 92),
    ('special_other',         'Special / Other',       'other',      False, 93),
]


class Command(BaseCommand):
    help = "Flush domain tables and reseed a consistent release-workflow testbed."

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Required. Acknowledges the destructive wipe.')
        parser.add_argument('--password', default='Testbed2026!',
                            help='Password for any test user this command creates.')

    def handle(self, *args, **opts):
        if not opts['confirm']:
            raise CommandError(
                "Refusing to run without --confirm. This deletes every row in "
                "MaterialOrder, ReleaseLetter, DocumentSignature, Transport, "
                "SiteReceipt, BoQ, Inventory, Projects, Communities, Suppliers, "
                "Contracts, Warehouses, Areas, Regions and the signing chain.\n"
                "It does NOT touch users, groups or the letterhead.")

        self.password = opts['password']

        # Deliberately not wrapped in one transaction: on a network-mounted
        # filesystem a single large SQLite commit throws disk I/O errors, and a
        # half-seeded database you can inspect beats a rollback you cannot.
        self._wipe()
        ptypes      = self._seed_project_types()
        units       = self._seed_units()
        categories  = self._seed_categories()
        warehouses  = self._seed_warehouses()
        self._seed_areas()
        inventory   = self._seed_inventory(units, categories, warehouses)
        communities = self._seed_communities(ptypes)
        # No project/site seeding here. `sync_site_from_community` (signals.py)
        # already calls `ensure_site_for_community` on every Community save,
        # which creates one umbrella Project per programme and one idempotent
        # ProjectSite per community. Creating them again here bypassed that
        # idempotency check and produced two of everything — 64 sites for 32
        # communities, across a fourth Project the map does not expect.
        self._seed_boq(communities, inventory, warehouses)
        chain       = self._seed_signing_chain()
        self._seed_releases(inventory, warehouses, communities, chain)
        self._report(chain)

    # ── teardown ─────────────────────────────────────────────────────────────

    def _wipe(self):
        """Delete dependents before parents.

        Named explicitly rather than derived from `apps.get_models()` minus a
        keep-list. A subtraction would silently pull in every new model anyone
        adds later — including the ones holding configuration — and the failure
        would look like data loss with no cause.
        """
        from Inventory.models import (
            Area, AreaRegion, BillOfQuantity, Category, Community,
            DiscussionRequest, DocumentDispatch, DocumentSignature,
            InventoryItem, MaterialOrder, MaterialTransport, Notification,
            Project, ProjectConsultant, ProjectSite, ProjectType,
            ReleaseCodeSequence, ReleaseLetter, Signatory, SigningStep,
            SiteReceipt, Supplier, Unit, Warehouse,
        )
        from Inventory.models.access_rate import MeterInstallation, RegionPopulation
        from Inventory.models.geography import District, Region
        from Inventory.models.orders import MaterialOrderAudit
        from Inventory.models.suppliers import (
            SupplierInvoice, SupplierInvoiceItem, SupplyContract, SupplyContractItem,
        )

        ordered = [
            # release + signing layer
            SiteReceipt, MaterialTransport,
            DocumentSignature, DocumentDispatch, DiscussionRequest,
            MaterialOrderAudit, ReleaseLetter,
            SigningStep, Signatory, ReleaseCodeSequence,
            # ordering layer
            MaterialOrder,
            # supply layer
            SupplierInvoiceItem, SupplierInvoice,
            SupplyContractItem, SupplyContract,
            # project layer
            MeterInstallation, ProjectSite, ProjectConsultant, Project,
            # reference layer — Community before ProjectType (PROTECT FK)
            BillOfQuantity, Community, InventoryItem,
            Supplier, Warehouse, Category, Unit, ProjectType,
            # geography
            AreaRegion, Area, RegionPopulation, District, Region,
            # in-app messages referencing releases that no longer exist
            Notification,
        ]
        for model in ordered:
            count = model.objects.count()
            model.objects.all().delete()
            if count:
                self.stdout.write(f"  wiped {count:6d}  {model.__name__}")

    # ── reference data ───────────────────────────────────────────────────────

    def _seed_project_types(self):
        from Inventory.models import ProjectType
        types = {}
        for code, name, consignee_role, active, order in PROJECT_TYPES:
            types[code] = ProjectType.objects.create(
                code=code, name=name, consignee_role=consignee_role,
                active=active, sort_order=order)
        self.stdout.write(f"  + {len(types)} ProjectType")
        return types

    def _seed_units(self):
        from Inventory.models import Unit
        units = {n: Unit.objects.create(name=n) for n in ('m', 'set', 'pcs', 'pair', 'km')}
        self.stdout.write(f"  + {len(units)} Unit")
        return units

    def _seed_categories(self):
        from Inventory.models import Category
        cats = {n: Category.objects.create(name=n) for n in CATEGORIES}
        self.stdout.write(f"  + {len(cats)} Category")
        return cats

    def _seed_warehouses(self):
        # `code` and `location` are NOT NULL with no Django default, so they
        # have to be supplied explicitly — omitting them fails at the first save
        # rather than defaulting to blank.
        from Inventory.models import Warehouse
        spec = [
            ('Tema Central Warehouse', 'WH-TEMA', 'Heavy Industrial Area, Tema'),
            ('Kumasi Regional Store',  'WH-KSI',  'Kaase Industrial Area, Kumasi'),
        ]
        houses = {name: Warehouse.objects.create(name=name, code=code, location=location)
                  for name, code, location in spec}
        self.stdout.write(f"  + {len(houses)} Warehouse")
        return houses

    def _seed_areas(self):
        """Areas, region rows, districts and population baselines.

        `AreaRegion.region` is written from GEOGRAPHY, not typed again, so the
        scope filter and the community rows cannot drift apart — which is the
        exact failure this whole command exists to remove.
        """
        from Inventory.models import Area, AreaRegion
        from Inventory.models.access_rate import RegionPopulation
        from Inventory.models.geography import District, Region

        region_codes = {name: f"R{index:02d}" for index, (name, _) in enumerate(GEOGRAPHY, 1)}
        regions = {}
        for region_name, districts in GEOGRAPHY:
            region = Region.objects.create(
                name=region_name, code=region_codes[region_name])
            regions[region_name] = region
            for index, (district_name, _) in enumerate(districts, 1):
                District.objects.create(
                    region=region, name=district_name,
                    code=f"{region_codes[region_name]}D{index}")
            RegionPopulation.objects.create(
                region=region_name,
                total_population=500_000,
                baseline_population_access=350_000,
                effective_from=timezone.now().date().replace(month=1, day=1),
                notes='Seeded baseline for testing — not a real GSS figure.')

        for area_name, region_names in AREAS:
            area = Area.objects.create(name=area_name)
            for region_name in region_names:
                AreaRegion.objects.create(area=area, region=region_name)

        self.stdout.write(f"  + {len(regions)} Region, {len(AREAS)} Area, "
                          f"{sum(len(d) for _, d in GEOGRAPHY)} District")

    def _seed_inventory(self, units, categories, warehouses):
        """Every item gets a real code.

        A blank code is not cosmetic: the BoQ upload copies it straight onto
        every BoQ line (`item_code = inventory_item.code`), and
        `get_or_create(code='')` then merges unrelated materials into one item.
        Your current database has one such row.
        """
        from Inventory.models import InventoryItem
        category_cycle = list(categories.values())
        items = {}
        for index, (code, name, unit, quantity) in enumerate(MATERIALS):
            items[code] = InventoryItem.objects.create(
                name=name, code=code, quantity=quantity,
                unit=units[unit],
                category=category_cycle[index % len(category_cycle)],
                warehouse=warehouses['Tema Central Warehouse'])
        self.stdout.write(f"  + {len(items)} InventoryItem (all coded)")
        return items

    def _seed_communities(self, ptypes):
        from Inventory.models import Community
        communities = []
        counter = 0
        for region_name, districts in GEOGRAPHY:
            for district_name, names in districts:
                for community_name in names:
                    counter += 1
                    # Rotate the three active programmes so every project type
                    # has communities to request against.
                    ptype = [ptypes['shep'], ptypes['cost_sharing'],
                             ptypes['streetlights']][counter % 3]
                    communities.append(Community.objects.create(
                        region=region_name, district=district_name,
                        community=community_name,
                        package_number=f"PKG-{counter:03d}",
                        project_type=ptype))
        self.stdout.write(f"  + {len(communities)} Community (UPPERCASE, canonical)")
        return communities

    def _seed_boq(self, communities, inventory, warehouses):
        """BoQ lines that a community can actually reconcile against.

        Previously the BoQ carried title-case regions from `seed_demo_data`
        while every community was uppercase, so no BoQ line ever matched — which
        is what strands site receipts and leaves the over-issuance summary
        looking wrong.
        """
        from Inventory.models import BillOfQuantity
        codes = list(inventory.values())
        rows = 0
        for index, community in enumerate(communities):
            # Three materials per community, so over-issuance is reachable
            # without making the table unreadable.
            for offset in range(3):
                item = codes[(index + offset) % len(codes)]
                contract = Decimal('500')
                # Every fifth line is deliberately over-issued, so the
                # over-issuance summary has real rows AND a real item_code.
                received = Decimal('620') if index % 5 == 0 and offset == 0 else Decimal('300')
                BillOfQuantity.objects.create(
                    region=community.region, district=community.district,
                    community=community.community,
                    package_number=community.package_number,
                    consultant='Acme Engineers Ltd',
                    contractor='Beta Power Works',
                    material_description=item.name,
                    item_code=item.code,
                    contract_quantity=float(contract),
                    quantity_received=float(received),
                    project_type=community.project_type.name,
                    warehouse=warehouses['Tema Central Warehouse'])
                rows += 1
        self.stdout.write(f"  + {rows} BillOfQuantity (item_code populated, "
                          f"{rows // 15} over-issued)")

    # ── the signing chain ────────────────────────────────────────────────────

    def _seed_signing_chain(self):
        """Two signatories, two different logins, one ordered sequence.

        Both `SigningStep` rows previously pointed at the same user, so the same
        person signed the memo and the letter. That makes the sequence
        unobservable: the handoff notification fires into the signer's own
        queue, "awaiting others" is always empty, and the rule that the letter
        cannot be signed before the memo can never be seen to hold.
        """
        from Inventory.models import Signatory, SigningStep

        director = self._ensure_user(
            'Director_Power', 'Ing. Sulemana', 'Abubakari',
            'director.power@energymin.gov.gh', group='Management')
        chief = User.objects.filter(username='Chief_Director').first()
        if chief is None:
            chief = self._ensure_user(
                'Chief_Director', 'Solomon Adjetey', 'Sowah',
                'chief.director@energymin.gov.gh', group='Management')
        elif not chief.email:
            # The handoff email needs somewhere to go. Without an address the
            # notification is in-app only, which is easy to miss in testing and
            # reads as the email feature being broken.
            chief.email = 'chief.director@energymin.gov.gh'
            chief.save(update_fields=['email'])

        signatory_memo = Signatory.objects.create(
            name='Ing. Sulemana Abubakari', title='Ag. Director, Power',
            is_default_for_release_memo=True, is_default_for_payment_memo=True,
            active=True, user=director,
            notes='Signs the approval memo. Step 1 of the release chain.')
        signatory_letter = Signatory.objects.create(
            name='Solomon Adjetey Sowah', title='Chief Director',
            signs_for='HON. MINISTER', is_default_for_release_letter=True,
            active=True, user=chief,
            notes='Signs the release letter to MMU on the authority of the '
                  'approved memo. Step 2 of the release chain.')

        step_memo = SigningStep.objects.create(
            document_kind='memo', order=1, signatory=signatory_memo,
            user=director, required=True, active=True)
        step_letter = SigningStep.objects.create(
            document_kind='letter', order=2, signatory=signatory_letter,
            user=chief, required=True, active=True)

        self.stdout.write("  + signing chain: 1 memo → Director_Power, "
                          "2 letter → Chief_Director")
        return {'director': director, 'chief': chief,
                'step_memo': step_memo, 'step_letter': step_letter}

    def _ensure_user(self, username, first, last, email, group=None):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={'first_name': first, 'last_name': last, 'email': email})
        if created:
            user.set_password(self.password)
            user.save()
            self.stdout.write(f"  + user {username} (password: {self.password})")
        if group:
            grp, _ = Group.objects.get_or_create(name=group)
            grp.user_set.add(user)
        return user

    # ── the two releases under test ──────────────────────────────────────────

    def _seed_releases(self, inventory, warehouses, communities, chain):
        from Inventory.models import MaterialOrder, Notification, ReleaseLetter

        officer = (User.objects.filter(username='Schedule_Officer').first()
                   or User.objects.filter(is_superuser=True).first())
        if officer is None:
            raise CommandError("No Schedule_Officer and no superuser to act as the "
                               "preparing officer.")

        # ── A. Fresh draft: orders with no release letter ────────────────────
        # The whole new flow starts here — Material Orders → open the release
        # letter → generate → land on the document → edit → choose a route.
        batch_a = self._batch_code()
        self._make_orders(batch_a, communities[0], officer, inventory, warehouses,
                          ('SMA015', 'SMS001', 'SMP001'), Decimal('120'))

        # ── B. Awaiting signature: sitting on step 1 ─────────────────────────
        batch_b = self._batch_code()
        community_b = communities[3]
        orders_b = self._make_orders(batch_b, community_b, officer, inventory,
                                     warehouses, ('SMC001', 'SMF001'), Decimal('80'))

        from Inventory.services.release_code import next_release_code
        release = ReleaseLetter.objects.create(
            request_code=batch_b,
            title=f"Release of {orders_b[0].name} — {community_b.community}",
            total_quantity=sum(o.quantity for o in orders_b),
            material_type='Other', project_type='SHEP',
            workflow_status='memo_generated',
            code=next_release_code(),
            uploaded_by=officer)
        MaterialOrder.objects.filter(pk__in=[o.pk for o in orders_b]).update(
            release_letter=release)

        # Clear the notification backlog seeding itself produced.
        #
        # Creating 96 BoQ rows and 5 orders fires the "New BOQ Entry" / "New
        # Release Request" signals ~250 times. Left in place they bury the one
        # notification the test is actually about — the signature request — and
        # a signatory who cannot find it in his own list will reasonably report
        # that the handoff never fired. Cleared here, immediately before the
        # real one is sent, so what remains is only what the workflow produced.
        Notification.objects.all().delete()

        generated = self._generate_documents(release, officer)
        if generated:
            # Hand it to step 1 the way an officer would, so it lands in
            # Director_Power's queue as genuinely sent rather than merely
            # generated — the distinction the queue now shows.
            from Inventory.services.approvals import (
                SendForSignatureError, send_for_signature,
            )
            try:
                send_for_signature(release, officer)
                self.stdout.write("  + release B sent for signature to Director_Power")
            except SendForSignatureError as exc:
                self.stdout.write(self.style.WARNING(f"  ! could not send: {exc}"))

        self.stdout.write(f"  + release A (draft, no letter): {batch_a}")
        self.stdout.write(f"  + release B ({release.code}): {batch_b}")
        self.batch_a, self.release_b = batch_a, release

    @staticmethod
    def _batch_code():
        """A batch base code. Orders hang off it as -1, -2, …

        `MaterialOrder.request_code` is **unique**, so the orders in one batch
        cannot literally share a code. The system's own convention is a base
        plus a numeric suffix — `REQ-YYYYMMDD-XXXXXX-1`, `-2` — which
        `ReleaseLetterUploadView._base_code()` collapses back to the base, and
        which `CreateReleaseLetterFromRequestView` matches with its
        `startswith(f"{code}-")` fallback. `ReleaseLetter.request_code` is not
        unique and carries the base.
        """
        import uuid

        return f"REQ-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"

    def _make_orders(self, batch, community, officer, inventory, warehouses,
                     codes, quantity):
        """One MaterialOrder per material, all under one batch base."""
        from Inventory.models import MaterialOrder

        orders = []
        for index, code in enumerate(codes, 1):
            item = inventory[code]
            orders.append(MaterialOrder.objects.create(
                # Passed explicitly so save() does not mint its own — each row
                # needs the batch base plus its own suffix.
                request_code=f"{batch}-{index}",
                name=item.name, code=item.code, unit=item.unit,
                category=item.category,
                warehouse=warehouses['Tema Central Warehouse'],
                quantity=quantity, status='Approved', request_type='Release',
                project_type='SHEP',
                region=community.region, district=community.district,
                community=community.community,
                package_number=community.package_number,
                consultant='Acme Engineers Ltd', contractor='Beta Power Works',
                requestor=officer.get_full_name() or officer.username,
                user=officer, created_by=officer))
        return orders

    def _generate_documents(self, release, officer):
        """Mint both PDFs, and say plainly if the renderer cannot.

        Signing is refused outright when WeasyPrint is unavailable — `can_sign`
        checks the renderer before anything is recorded, because a signature
        that cannot reach the page would otherwise lock a document showing a
        blank signature line. So a failure here is not cosmetic: it means the
        signing half of the workflow cannot be tested on this machine at all,
        and it is worth saying so now rather than at the first click.
        """
        from Inventory.services.document_render import (
            RendererUnavailable, weasyprint_status,
        )
        from Inventory.services.pdf_generator import (
            generate_release_letter, generate_release_memo,
        )

        ok, detail = weasyprint_status()
        if not ok:
            self.stdout.write(self.style.ERROR(
                f"\n  ! PDF renderer unavailable: {detail}\n"
                "  ! Release B has NO documents, and signing will be refused for\n"
                "  ! every release until this is fixed. Everything upstream of\n"
                "  ! signing — requests, the queue, dashboards — still works.\n"))
            return False

        try:
            memo = generate_release_memo(release)
            letter = generate_release_letter(release)
            release.memo_pdf.save(memo.name, memo, save=False)
            release.letter_pdf.save(letter.name, letter, save=False)
            release.memo_version = 1
            release.letter_version = 1
            release.documents_generated_at = timezone.now()
            release.documents_generated_by = officer
            release.save()
            return True
        except RendererUnavailable as exc:
            self.stdout.write(self.style.ERROR(f"  ! {exc}"))
            return False

    # ── report ───────────────────────────────────────────────────────────────

    def _report(self, chain):
        director, chief = chain['director'], chain['chief']
        self.stdout.write(self.style.SUCCESS(f"""
=== Testbed ready ===

Signing chain (two different people, so the handoff is observable):
  step 1  memo    Ing. Sulemana Abubakari, Ag. Director, Power  -> {director.username}
  step 2  letter  Solomon Adjetey Sowah, Chief Director         -> {chief.username}

Walk it in this order:

  1. Sign in as Schedule_Officer
     /material-orders/            find {self.batch_a}, open the release letter
                                  -> both documents generate, you land on the
                                     release letter itself (no more 3-step strip)
     edit the wording live, then "Send for signature to Ag. Director, Power"

  2. Sign in as {director.username}
     /approvals/                  {self.batch_a} is under "Awaiting my signature";
                                  {self.release_b.code} is already there from the seed
     "Review and sign"            -> both documents side by side, sign the MEMO

  3. Sign in as {chief.username}
     /approvals/                  the letter arrived automatically when the memo
                                  was signed — nobody emailed anyone by hand
     sign the LETTER              -> chain completes, documents lock,
                                     MMU goes on advance notice

  4. Back as Schedule_Officer
     "Print on Ministry letterhead stock" for the wet-signature route,
     then upload the signed scan and have a DIFFERENT user confirm it.

Region strings are now identical across Community, ProjectSite,
BillOfQuantity, MaterialOrder and AreaRegion (UPPERCASE), so the request
form's dropdowns and the community records finally agree.

Passwords for users this command created: {self.password}
Existing users keep their current passwords.
"""))
