"""The release letter must surface on My Assigned Orders even when the order's
release_letter FK is null but a letter shares its request_code."""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from Inventory.models import MaterialOrder, ReleaseLetter, StoreOrderAssignment, Unit


class AssignedReleaseLetterTests(TestCase):
    def test_release_letter_resolved_by_request_code_fallback(self):
        officer = User.objects.create_user('so', password='x')
        officer.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        unit = Unit.objects.create(name='pcs')
        # Letter linked only by shared request_code (FK left null on the order).
        letter = ReleaseLetter.objects.create(
            request_code='REQ-XYZ', title='Poles', total_quantity=Decimal('10'),
            uploaded_by=officer,
            pdf_file=SimpleUploadedFile('s.pdf', b'%PDF-1.4', 'application/pdf'))
        order = MaterialOrder.objects.create(
            name='Pole', code='LHP006', quantity=Decimal('10'), unit=unit,
            request_type='Release', status='Approved', user=officer,
            assigned_to=officer, request_code='REQ-XYZ', release_letter=None)
        StoreOrderAssignment.objects.create(
            material_order=order, assigned_to=officer, assigned_by=officer,
            status='Assigned')

        self.client.force_login(officer)
        resp = self.client.get(reverse('stores_my_assigned_orders'))
        self.assertEqual(resp.status_code, 200)
        # The letter link is rendered (resolved via the request_code fallback).
        self.assertContains(resp, reverse('release_letter_detail', args=[letter.pk]))
