"""
Set up a release that can actually run to completion, and the consultants to
receive it.

The earlier testbed deliberately seeded a messy Bill of Quantity — one line in
five over-issued, one material per community with no BoQ entry — because the
interesting cases were the exceptions. That succeeded: both now block document
generation, which means no release in that dataset can be issued at all.

This adds the other case. One community, three materials that each have a BoQ
line with room in it, and quantities well inside the balance. Nothing to
justify, nothing unmatched, nothing to block.

It also does two things the workflow needs downstream:

  * **Consultants, bound to Areas.** SHEP names the consultant as consignee, and
    the resolver finds them by matching the community's region to an Area. With
    no consultant the release has nobody to be released *to*, and the letter
    says so.

  * **Collapses the signing chain onto one account.** Both steps, one user.
    This is a testing compromise and not how the Ministry works — the whole
    point of the sequence is that two different officers sign. It is acceptable
    here only because the cross-user handoff has already been observed: signing
    the memo notified the Chief Director automatically, with nobody emailing
    anyone by hand. What cannot be observed on a single M365 login is the rest
    of the chain, so this trades the part already proven for the part that is not.

    `--restore-chain` puts it back.

Usage:
    python manage.py seed_clean_release --confirm
    python manage.py seed_clean_release --restore-chain
"""

from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

# One consultancy per operational Area. Names are firms, not people, because
# that is what a consignee line on a release letter actually reads.
CONSULTANCIES = [
    ('Greater Accra & Eastern', 'Adjei & Partners Ltd', 'consultant.gae'),
    ('Ashanti', 'Kumasi Power Engineering Ltd', 'consultant.ashanti'),
    ('Volta & Oti', 'Volta Basin Electricals Ltd', 'consultant.volta'),
    ('Northern & Savannah', 'Northern Grid Services Ltd', 'consultant.northern'),
    ('Upper East', 'Bolga Electrical Works Ltd', 'consultant.uppereast'),
    ('Western & Western North', 'Takoradi Power Contractors Ltd', 'consultant.western'),
    ('Ahafo, Bono & Bono East', 'Sunyani Energy Services Ltd', 'consultant.bono'),
]


class Command(BaseCommand):
    help = "Seed consultants by area and one release that reconciles cleanly."

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Required unless --restore-chain.')
        parser.add_argument('--restore-chain', action='store_true',
                            help='Put the two signing steps back on two people and exit.')
        parser.add_argument('--password', default='Testbed2026!')
        parser.add_argument('--signer', default=None,
                            help='Username to hold both signing steps. '
                                 'Defaults to the first superuser with an email.')

    def handle(self, *args, **opts):
        if opts['restore_chain']:
            return self._restore_chain()
        if not opts['confirm']:
            raise CommandError(
                "Refusing to run without --confirm. This creates consultant users, "
                "creates material orders, and COLLAPSES the signing chain onto one "
                "account so the workflow can be run to completion on a single login. "
                "Use --restore-chain afterwards to undo the chain change.")

        self.password = opts['password']
        consultants = self._seed_consultants()
        signer = self._collapse_chain(opts['signer'])
        batch, community, lines = self._seed_clean_request(signer)
        self._report(batch, community, lines, consultants, signer)

    # ── consultants ──────────────────────────────────────────────────────────

    def _seed_consultants(self):
        from Inventory.models import Area, ProjectConsultant

        group, _ = Group.objects.get_or_create(name='Consultants')
        created = []
        for area_name, firm, username in CONSULTANCIES:
            area = Area.objects.filter(name=area_name).first()
            if area is None:
                self.stdout.write(self.style.WARNING(
                    f"  ! no Area named {area_name!r} — skipping {firm}"))
                continue

            user, is_new = User.objects.get_or_create(
                username=username,
                defaults={'first_name': firm.split()[0],
                          'last_name': 'Consultant',
                          'email': f"{username}@example.gh"})
            if is_new:
                user.set_password(self.password)
                user.save()
            group.user_set.add(user)

            consultant, _ = ProjectConsultant.objects.update_or_create(
                name=firm,
                defaults={
                    'firm': firm,
                    'area': area,
                    'active': True,
                    'user': user,
                    'contact_email': user.email,
                    'contact_phone': '+233200000000',
                    # `region`/`district` are the legacy fallback. Left blank on
                    # purpose so the Area binding is the thing under test — if
                    # the resolver is quietly falling back to a region string,
                    # this dataset will show it as "unresolved" rather than
                    # appearing to work.
                    'region': '',
                    'district': '',
                },
            )
            created.append((area_name, consultant))
            self.stdout.write(f"  + {firm} → {area_name} (login {username})")
        return created

    # ── signing chain ────────────────────────────────────────────────────────

    def _collapse_chain(self, username):
        from Inventory.models import SigningStep

        if username:
            signer = User.objects.filter(username=username).first()
            if signer is None:
                raise CommandError(f"No user named {username!r}.")
        else:
            signer = (User.objects.filter(is_superuser=True, is_active=True)
                      .exclude(email='').order_by('id').first())
        if signer is None:
            raise CommandError("No superuser with an email address to sign as.")

        steps = SigningStep.objects.filter(active=True).order_by('order')
        for step in steps:
            step.user = signer
            step.save(update_fields=['user'])
            # The printed name follows the login, or the document would carry a
            # name that never signed it.
            if step.signatory and step.signatory.user_id != signer.pk:
                step.signatory.user = signer
                step.signatory.name = signer.get_full_name() or signer.username
                step.signatory.save(update_fields=['user', 'name'])

        self.stdout.write(self.style.WARNING(
            f"  ! signing chain collapsed onto {signer.username} "
            f"({steps.count()} step(s)) — testing only, run --restore-chain after"))
        return signer

    def _restore_chain(self):
        """Put the chain back on two different officers."""
        from Inventory.models import Signatory, SigningStep

        pairs = [
            ('Ag. Director, Power', 'Director_Power', 'Ing. Sulemana Abubakari'),
            ('Chief Director', 'Chief_Director', 'Solomon Adjetey Sowah'),
        ]
        for title, username, name in pairs:
            user = User.objects.filter(username=username).first()
            signatory = Signatory.objects.filter(title=title).first()
            if user is None or signatory is None:
                self.stdout.write(self.style.WARNING(
                    f"  ! could not restore {title} — user or signatory missing"))
                continue
            signatory.user = user
            signatory.name = name
            signatory.save(update_fields=['user', 'name'])
            SigningStep.objects.filter(signatory=signatory).update(user=user)
            self.stdout.write(f"  + {title} → {username} ({name})")
        self.stdout.write(self.style.SUCCESS(
            "\nSigning chain restored to two officers. The handoff is observable "
            "again, but the letter can only be signed by Chief_Director."))

    # ── a release that reconciles ────────────────────────────────────────────

    def _seed_clean_request(self, officer):
        """One community, three materials, every line inside its BoQ balance.

        The community is chosen by query rather than hard-coded: it has to be one
        where three materials each have a BoQ line with room, and hard-coding a
        name would silently produce a blocked release the moment the BoQ data
        changed underneath it.
        """
        from django.db.models import F

        from Inventory.models import BillOfQuantity, Community, MaterialOrder

        healthy = (BillOfQuantity.objects
                   .filter(contract_quantity__gt=F('quantity_received') + 150)
                   .order_by('community', 'item_code'))

        by_community = {}
        for row in healthy:
            by_community.setdefault(row.community, []).append(row)

        chosen = next(((name, rows) for name, rows in by_community.items()
                       if len(rows) >= 3), (None, None))
        community_name, rows = chosen
        if community_name is None:
            raise CommandError(
                "No community has three Bill of Quantity lines with at least 150 "
                "spare. Re-run seed_release_testbed, or lower the threshold.")

        rows = rows[:3]
        community = Community.objects.filter(community__iexact=community_name).first()
        batch = self._batch_code()

        lines = []
        for index, row in enumerate(rows, 1):
            item = self._inventory_for(row.item_code)
            if item is None:
                continue
            available = Decimal(str(row.contract_quantity)) - Decimal(str(row.quantity_received))
            # Comfortably inside the balance, so this stays clean even if a
            # little stock moves before anyone gets round to running it.
            quantity = min(Decimal('100'), available - Decimal('20'))
            MaterialOrder.objects.create(
                request_code=f"{batch}-{index}",
                name=item.name, code=item.code, unit=item.unit,
                category=item.category, warehouse=item.warehouse,
                quantity=quantity, status='Approved', request_type='Release',
                project_type='SHEP',
                region=row.region, district=row.district, community=row.community,
                package_number=row.package_number,
                consultant=row.consultant, contractor=row.contractor,
                requestor=officer.get_full_name() or officer.username,
                user=officer, created_by=officer,
            )
            lines.append((item.name, quantity, item.unit.name if item.unit_id else '',
                          available))

        return batch, (community.community if community else community_name), lines

    @staticmethod
    def _inventory_for(item_code):
        from Inventory.models import InventoryItem
        return InventoryItem.objects.filter(code=item_code).first()

    @staticmethod
    def _batch_code():
        import uuid
        return f"REQ-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"

    # ── report ───────────────────────────────────────────────────────────────

    def _report(self, batch, community, lines, consultants, signer):
        detail = "\n".join(
            f"    {name:38s} {qty} {unit:4s}  (BoQ balance {avail})"
            for name, qty, unit, avail in lines)
        self.stdout.write(self.style.SUCCESS(f"""
=== A release that can complete ===

  Request   {batch}
  Community {community}
  Signer    {signer.username} — holds BOTH signing steps

{detail}

  Every line sits inside its Bill of Quantity balance, so generation will not be
  blocked. {len(consultants)} consultancy(ies) are now bound to areas, so the
  consignee resolves.

Walk it:
  1. /release-letter/upload/           pick {batch} → generates → lands on the letter
  2. Send for signature → sign the MEMO → sign the LETTER (chain completes, locks)
  3. Print on letterhead stock → upload that same PDF as the signed scan
     (its QR carries the release code, so validation passes) → confirm it
  4. Mark released → transport → waybill → site receipt
  5. Record a verified meter installation at {community} to flip the site to
     Energised, which is what the Ghana map and the access rate read.

Afterwards:
  python manage.py seed_clean_release --restore-chain
"""))
