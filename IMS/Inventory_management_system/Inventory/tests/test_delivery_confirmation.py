"""Delivery is marked by the consultant confirming receipt, not by the transporter.

Two things are being locked in here:

  * **The control.** A transporter saying "delivered" is a claim; the consultant
    confirming at site is evidence, and they are the one who can actually see
    what arrived. Same principle as the two-person rule on signed scans.

  * **The deadlock this fixed.** 'Delivered' is in MaterialTransport's
    STATUS_CHOICES but is deliberately absent from the transporter's status
    dropdown (Awaiting Transporter / Loading / Loaded / In Transit). The receipt
    form used to be gated behind `status == 'Delivered'`, so the state was
    unreachable, no receipt could ever be logged, and the release pipeline could
    not advance past dispatch. Regression guard below.
"""

from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from Inventory.models import (
    MaterialOrder, MaterialTransport, SiteReceipt, Transporter, Unit,
)


class DeliveryConfirmationTests(TestCase):
    def setUp(self):
        self.consultant = User.objects.create_user(
            'consultant', email='c@energymin.gov.gh', password='pw')
        self.consultant.groups.add(Group.objects.get_or_create(name='Consultants')[0])

        self.unit = Unit.objects.create(name='set')
        self.order = MaterialOrder.objects.create(
            name='Stay Equipment C/W Accessories', quantity=Decimal('2000'),
            unit=self.unit, request_type='Release', community='ANTWIKROM')
        self.transporter = Transporter.objects.create(name='NF3')
        self.transport = MaterialTransport.objects.create(
            material_order=self.order, transporter=self.transporter,
            status='In Transit')

    # -- the deadlock ------------------------------------------------------
    def test_delivered_is_not_offered_to_the_transporter(self):
        """Regression: if 'Delivered' ever reappears in the status form, the
        deliverer can self-attest and this control is gone."""
        with open('Inventory/templates/Inventory/transportation_status.html') as fh:
            markup = fh.read()
        form = markup.split('Update Status To')[1][:2000] if 'Update Status To' in markup else markup
        self.assertNotIn('value="Delivered"', form)

    def test_an_in_transit_delivery_can_be_confirmed(self):
        """The old template gated this on status == 'Delivered', which was
        unreachable — the button was permanently disabled."""
        self.client.force_login(self.consultant)
        resp = self.client.get(reverse('consultant_deliveries'))
        self.assertContains(resp, 'Confirm receipt at site')
        self.assertNotContains(resp, 'Awaiting Delivery')

    # -- the transition ----------------------------------------------------
    def test_confirming_receipt_marks_the_transport_delivered(self):
        self.client.force_login(self.consultant)
        self.client.post(
            reverse('site_receipt_create', args=[self.transport.id]),
            {'received_quantity': '2000', 'condition': 'Good'})

        self.transport.refresh_from_db()
        self.assertEqual(self.transport.status, 'Delivered')
        self.assertIsNotNone(self.transport.date_delivered,
                             "date_delivered must be stamped at confirmation")

    def test_the_receipt_records_who_confirmed_it(self):
        self.client.force_login(self.consultant)
        self.client.post(
            reverse('site_receipt_create', args=[self.transport.id]),
            {'received_quantity': '2000', 'condition': 'Good'})

        receipt = SiteReceipt.objects.get(material_transport=self.transport)
        self.assertEqual(receipt.received_by, self.consultant)

    def test_a_confirmed_delivery_leaves_the_pending_list(self):
        self.client.force_login(self.consultant)
        self.client.post(
            reverse('site_receipt_create', args=[self.transport.id]),
            {'received_quantity': '2000', 'condition': 'Good'})

        resp = self.client.get(reverse('consultant_deliveries'))
        self.assertNotIn(self.transport, resp.context['transports'])

    def test_confirmation_is_idempotent_on_date_delivered(self):
        """An already-delivered transport keeps its original delivery time."""
        from django.utils import timezone
        earlier = timezone.now() - timezone.timedelta(days=1)
        MaterialTransport.objects.filter(pk=self.transport.pk).update(
            status='Delivered', date_delivered=earlier)

        self.client.force_login(self.consultant)
        self.client.post(
            reverse('site_receipt_create', args=[self.transport.id]),
            {'received_quantity': '2000', 'condition': 'Good'})

        self.transport.refresh_from_db()
        self.assertEqual(self.transport.date_delivered.date(), earlier.date())

    # -- visibility --------------------------------------------------------
    def test_issue_flagged_deliveries_are_visible_to_the_consultant(self):
        """They are the person at site — an issue shouldn't vanish from their list."""
        self.transport.status = 'Issue'
        self.transport.save(update_fields=['status'])

        self.client.force_login(self.consultant)
        resp = self.client.get(reverse('consultant_deliveries'))
        self.assertIn(self.transport, resp.context['transports'])
        self.assertContains(resp, 'Issue reported')
