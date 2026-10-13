"""The 'raise a justification' link must open the form for a *prospective*
over-issuance (release not yet recorded, BoQ balance not yet negative)."""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from Inventory.models import BillOfQuantity, BoQOverissuanceJustification


class ProspectiveOverissuanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user('so', password='x')
        cls.user.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        # Contract 200, nothing received yet -> balance +200, NO persisted over-issuance.
        cls.boq = BillOfQuantity.objects.create(
            region='Greater Accra', district='Ga West', community='AMASAMAN',
            consultant='C', contractor='K', package_number='PKG1',
            material_description='HT Stay Insulator', item_code='SMA002',
            contract_quantity=200.0, quantity_received=0.0)

    def test_link_without_over_bounces(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('boq_overissuance_justification_create', args=[self.boq.pk]))
        self.assertEqual(r.status_code, 302)  # redirected to summary

    def test_prospective_over_opens_form(self):
        self.client.force_login(self.user)
        r = self.client.get(
            reverse('boq_overissuance_justification_create', args=[self.boq.pk]) + '?over=50')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'HT Stay Insulator')

    def test_submit_records_prospective_amount(self):
        self.client.force_login(self.user)
        url = reverse('boq_overissuance_justification_create', args=[self.boq.pk]) + '?over=50'
        r = self.client.post(url, {
            'justification_category': 'Site Condition',
            'reason': 'Extra span needed on site.',
            'over': '50'})
        self.assertEqual(r.status_code, 302)
        j = BoQOverissuanceJustification.objects.get(boq_item=self.boq)
        self.assertEqual(float(j.overissuance_quantity), 50.0)
