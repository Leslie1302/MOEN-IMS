"""Re-posting site receipts that were logged before their BoQ line existed.

`SiteReceipt.save()` resolves the BoQ match only `if is_new`, so a receipt
recorded ahead of its Bill of Quantity never draws down the contract — it sits
in the over-issuance summary as an off-BoQ delivery for good.

The property that matters most here is that a receipt can never post TWICE.
Double-posting would inflate `quantity_received` and manufacture an over-issue
out of nothing, which is worse than the problem being fixed.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from Inventory.models import (
    BillOfQuantity, MaterialOrder, MaterialTransport, SiteReceipt, Transporter, Unit,
)
from Inventory.services.boq_rematch import (
    count_unposted_receipts, rematch_unposted_receipts,
)


class BoqRematchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('consultant', password='pw')
        self.unit = Unit.objects.create(name='set')
        self.transporter = Transporter.objects.create(name='NF3')

    def _receipt(self, qty='100', code='STY001', community='ANTWIKROM'):
        order = MaterialOrder.objects.create(
            name='Stay Equipment', quantity=Decimal(qty), unit=self.unit,
            request_type='Release', code=code, community=community,
            district='Kwahu West', region='Eastern')
        transport = MaterialTransport.objects.create(
            material_order=order, transporter=self.transporter, status='In Transit')
        return SiteReceipt.objects.create(
            material_transport=transport, received_quantity=Decimal(qty),
            received_by=self.user, condition='Good')

    def _boq(self, contract='500', code='STY001', community='ANTWIKROM'):
        return BillOfQuantity.objects.create(
            item_code=code, material_description='Stay Equipment',
            contract_quantity=float(contract), quantity_received=0,
            community=community, district='Kwahu West', region='Eastern')

    # -- the stranding this fixes -----------------------------------------
    def test_a_receipt_logged_before_its_boq_line_does_not_post(self):
        """Baseline: this is the state that strands receipts."""
        receipt = self._receipt()
        self.assertFalse(receipt.boq_matched)
        self.assertEqual(count_unposted_receipts(), 1)

    def test_uploading_the_boq_afterwards_does_not_post_it_by_itself(self):
        receipt = self._receipt()
        self._boq()
        receipt.refresh_from_db()
        self.assertFalse(receipt.boq_matched,
                         "the match is resolved once, at creation")

    def test_rematch_posts_it(self):
        receipt = self._receipt(qty='100')
        boq = self._boq(contract='500')

        result = rematch_unposted_receipts()

        self.assertEqual(result.posted, 1)
        receipt.refresh_from_db()
        boq.refresh_from_db()
        self.assertTrue(receipt.boq_matched)
        self.assertEqual(boq.quantity_received, 100)

    # -- the property that matters ----------------------------------------
    def test_a_receipt_can_never_post_twice(self):
        """Double-posting would inflate quantity_received and manufacture an
        over-issue out of nothing."""
        self._receipt(qty='100')
        boq = self._boq(contract='500')

        rematch_unposted_receipts()
        rematch_unposted_receipts()
        rematch_unposted_receipts()

        boq.refresh_from_db()
        self.assertEqual(boq.quantity_received, 100)

    def test_already_matched_receipts_are_never_considered(self):
        self._boq(contract='500')
        receipt = self._receipt(qty='100')   # BoQ exists, so this posts on create
        self.assertTrue(receipt.boq_matched)

        result = rematch_unposted_receipts()
        self.assertEqual(result.considered, 0)

    # -- dry run -----------------------------------------------------------
    def test_a_dry_run_writes_nothing(self):
        receipt = self._receipt(qty='100')
        boq = self._boq(contract='500')

        result = rematch_unposted_receipts(dry_run=True)

        self.assertEqual(result.posted, 1, "it should report what would post")
        receipt.refresh_from_db()
        boq.refresh_from_db()
        self.assertFalse(receipt.boq_matched, "but change nothing")
        self.assertEqual(boq.quantity_received, 0,
                         "and crucially not increment the BoQ")

    # -- genuinely off-BoQ -------------------------------------------------
    def test_a_receipt_with_no_matching_line_stays_unmatched(self):
        self._receipt(code='NOSUCH', community='NOWHERE')
        result = rematch_unposted_receipts()
        self.assertEqual(result.posted, 0)
        self.assertEqual(result.still_unmatched, 1)

    def test_over_issue_is_still_reported(self):
        """Re-matching must not paper over a genuine over-issue."""
        self._receipt(qty='600')
        boq = self._boq(contract='500')

        rematch_unposted_receipts()

        boq.refresh_from_db()
        self.assertEqual(boq.quantity_received, 600)
        self.assertGreater(boq.quantity_received, boq.contract_quantity)

    # -- the command -------------------------------------------------------
    def test_the_management_command_runs(self):
        self._receipt(qty='100')
        self._boq(contract='500')
        call_command('rematch_site_receipts', '--dry-run')
        call_command('rematch_site_receipts', verbosity=0)
        self.assertEqual(count_unposted_receipts(), 0)
