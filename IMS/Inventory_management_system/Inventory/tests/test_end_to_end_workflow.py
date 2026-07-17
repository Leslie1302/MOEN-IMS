"""
End-to-end workflow test: walks one material release order through the
entire system lifecycle, hitting the real HTTP endpoints each role uses.

    request → assign to store officer → partial + full processing →
    auto placeholder + notification → transporter assignment (waybill) →
    in transit → site receipt → BoQ drawdown → project site completed →
    consultant progress → Ghana map + project dashboards → archived

Run with:
    python manage.py test Inventory.tests.test_end_to_end_workflow
"""
import tempfile
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from Inventory.models import (
    BillOfQuantity, MaterialOrder, MaterialTransport, Notification,
    Project, ProjectSite, ReleaseLetter, SiteReceipt, StoreOrderAssignment,
    Transporter, Unit,
)

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class EndToEndWorkflowTest(TestCase):
    """One order, front to back, through the real views."""

    @classmethod
    def setUpTestData(cls):
        # Groups (both singular/plural store variants are used in the code)
        # get_or_create: migration 0031 already seeds the canonical groups
        for name in ['Store Officer', 'Store Officers', 'Management',
                     'Schedule Officers', 'Consultant']:
            Group.objects.get_or_create(name=name)

        def make_user(username, *groups):
            u = User.objects.create_user(username, f'{username}@test.gh', 'pw')
            for g in groups:
                u.groups.add(Group.objects.get(name=g))
            return u

        cls.scheduler = make_user('scheduler', 'Schedule Officers')
        cls.manager = make_user('manager', 'Management')
        cls.storekeeper = make_user('storekeeper', 'Store Officer', 'Store Officers')
        cls.consultant = make_user('consultant', 'Consultant')

        cls.transporter = Transporter.objects.create(
            name='Volta Haulage Ltd', is_active=True,
        )
        cls.unit = Unit.objects.create(name='drums')

        # ── Geography / project spine (feeds Ghana map & project status) ──
        cls.project = Project.objects.create(
            name='SHEP-4 Volta Electrification',
            code='SHEP4-VOLTA',
            description='E2E test project',
            project_type='SHEP',
            status='Active',
            consultant='Volta Consult Ltd',
            contractor='PowerBuild Ltd',
            created_by=cls.manager,
        )
        cls.site = ProjectSite.objects.create(
            project=cls.project,
            name='Adidome Site',
            code='SITE-ADIDOME',
            region='Volta',
            district='Central Tongu',
            community='Adidome',
            status='Planned',
        )
        # Signed release letter — the signed-letter guard blocks Release
        # processing on every path until the scan is on file.
        cls.letter = ReleaseLetter.objects.create(
            request_code='REQ-E2E',
            title='Volta conductor release',
            total_quantity=100,
            uploaded_by=cls.manager,
            pdf_file=SimpleUploadedFile(
                'signed_letter.pdf', b'%PDF-1.4 signed', 'application/pdf'),
        )

        # One contract line — fully delivering it must flip the site to
        # Completed via the BoQ→site sync signal.
        cls.boq = BillOfQuantity.objects.create(
            region='Volta',
            district='Central Tongu',
            community='Adidome',
            consultant='Volta Consult Ltd',
            contractor='PowerBuild Ltd',
            package_number='PKG-VOLTA-7',
            project_type='SHEP',
            material_description='ABC Conductor 50mm',
            item_code='COND-50',
            contract_quantity=100,
        )

    def test_full_release_order_lifecycle(self):
        # ── Stage 1: Schedule officer files a release request ─────────
        # (mirrors what the request-material view sets on creation)
        order = MaterialOrder.objects.create(
            name='ABC Conductor 50mm',
            code='COND-50',                 # matches the BoQ item_code
            quantity=100,
            unit=self.unit,
            request_type='Release',
            status='Pending',
            user=self.scheduler,
            processed_quantity=0,
            remaining_quantity=100,
            # Destination — lets the site receipt post to the right BoQ line
            region='Volta',
            district='Central Tongu',
            community='Adidome',
            package_number='PKG-VOLTA-7',
            release_letter=self.letter,  # signed — processing is allowed
        )
        self.assertTrue(order.request_code.startswith('REQ-'))
        # Creation notified the store officers
        self.assertTrue(Notification.objects.filter(
            notification_type='material_request').exists())

        # ── Stage 2: Management assigns the order to a store officer ──
        self.client.force_login(self.manager)
        resp = self.client.post(reverse('stores_assign_orders'), {
            'order_ids[]': [order.id],
            'staff_id': self.storekeeper.id,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        order.refresh_from_db()
        self.assertEqual(order.status, 'Approved')
        self.assertEqual(order.assigned_to, self.storekeeper)
        self.assertTrue(StoreOrderAssignment.objects.filter(
            material_order=order, assigned_to=self.storekeeper,
            status='Assigned').exists())

        # ── Stage 3a: Store officer processes a partial quantity ──────
        self.client.force_login(self.storekeeper)
        resp = self.client.post(
            reverse('process_order_partial', args=[order.id]),
            {'quantity': '40'})
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'Partially Fulfilled')
        self.assertEqual(order.processed_quantity, Decimal('40'))
        self.assertEqual(order.remaining_quantity, Decimal('60'))

        # Partially processed order is now visible on Assign Transporter
        resp = self.client.get(reverse('transport_assignment'))
        self.assertIn(order, resp.context['material_orders'])

        # ── Stage 3b: Store officer processes the rest → Completed ────
        resp = self.client.post(
            reverse('process_order_partial', args=[order.id]),
            {'quantity': '60'})
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'Completed')
        self.assertEqual(order.remaining_quantity, Decimal('0'))

        # Completion auto-created an 'Awaiting Transporter' placeholder
        # and an honest awaiting-transporter notification (not "assigned")
        self.assertTrue(order.transports.filter(
            status='Awaiting Transporter').exists())
        self.assertTrue(Notification.objects.filter(
            title__startswith='Awaiting Transporter').exists())
        # Placeholder must NOT count as transported quantity...
        self.assertEqual(order.total_transported_quantity, 0)
        # ...so the completed order still shows on Assign Transporter
        resp = self.client.get(reverse('transport_assignment'))
        self.assertIn(order, resp.context['material_orders'])

        # ── Stage 4: Store officer assigns a real transporter ─────────
        resp = self.client.post(reverse('transport_assignment'), {
            'assign_transporter': '1',
            'order_id': order.id,
            'transporter': self.transporter.id,
            'transport_quantity': '100',
            'driver_name': 'Kwame Mensah',
            'driver_phone': '0244000000',
        }, **AJAX)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        transport = order.transports.get(status='Assigned')
        self.assertTrue(transport.waybill_number.startswith('WB-'))
        self.assertEqual(transport.quantity, 100)
        # Real assignment removed the placeholder and notified people
        self.assertFalse(order.transports.filter(
            status='Awaiting Transporter').exists())
        self.assertTrue(Notification.objects.filter(
            notification_type='transport_assigned',
            title__startswith='Transport Assignment').exists())
        # Order is now fully covered → drops off the Assign Transporter page
        resp = self.client.get(reverse('transport_assignment'))
        self.assertNotIn(order, resp.context['material_orders'])

        # ── Stage 5: Transport goes In Transit ────────────────────────
        resp = self.client.post(
            reverse('update_transport_status', args=[transport.pk]),
            {'status': 'In Transit'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        transport.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(transport.status, 'In Transit')
        # Status is explicit now (Phase 3): the In Transit transition set
        # by the transport flow sticks instead of being silently reverted
        # to 'Completed' by MaterialOrder.save().
        self.assertEqual(order.status, 'In Transit')
        # Visible on the live Transportation Status board
        resp = self.client.get(reverse('transportation_status'))
        self.assertIn(transport, resp.context['transports'])

        # ── Stage 6: Consultant logs the site receipt ─────────────────
        # The Delivered back door must be shut: status endpoint refuses it
        resp = self.client.post(
            reverse('update_transport_status', args=[transport.pk]),
            {'status': 'Delivered'})
        self.assertEqual(resp.status_code, 400)
        transport.refresh_from_db()
        self.assertEqual(transport.status, 'In Transit')

        # Receipt form is hidden from non-consultants (404, not 403)
        resp = self.client.get(
            reverse('site_receipt_create', args=[transport.id]))
        self.assertEqual(resp.status_code, 404)

        # Consultant sees the pending delivery and logs the receipt via HTTP
        self.client.force_login(self.consultant)
        resp = self.client.get(reverse('consultant_deliveries'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(transport, resp.context['transports'])

        resp = self.client.post(
            reverse('site_receipt_create', args=[transport.id]), {
                'received_quantity': '100',
                'condition': 'Good',
                'notes': 'All drums intact.',
                'site_photos': SimpleUploadedFile(
                    'site.jpg', b'fake-jpeg-bytes', 'image/jpeg'),
            })
        self.assertEqual(resp.status_code, 302)  # redirect on success
        receipt = SiteReceipt.objects.get(material_transport=transport)
        self.assertEqual(receipt.received_by, self.consultant)
        transport.refresh_from_db()
        self.assertEqual(transport.status, 'Delivered')
        self.assertIsNotNone(transport.date_delivered)

        # Receipt posted to the matching BoQ line (item code + package)
        receipt.refresh_from_db()
        self.assertTrue(receipt.boq_matched)
        self.boq.refresh_from_db()
        self.assertEqual(self.boq.quantity_received, 100.0)
        self.assertEqual(self.boq.balance, 0.0)

        # BoQ→site sync signal flipped the project site to Completed
        self.site.refresh_from_db()
        self.assertEqual(self.site.status, 'Completed')
        self.assertIsNotNone(self.site.actual_completion_date)

        # ── Stage 7: Consultant reports works progress ────────────────
        # (mirrors the Site Progress page — feeds the map's headline
        # access rate, which reads works_status, not material status)
        self.site.works_status = 'Energised'
        self.site.progress_percent = 100
        self.site.progress_updated_by = self.consultant
        self.site.save()

        # ── Stage 8: Ghana map & project dashboards reflect it all ────
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('ghana_map_data_api'))
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()

        volta = next(r for r in payload['data'] if r['name'] == 'Volta')
        self.assertEqual(volta['total_sites'], 1)
        self.assertEqual(volta['completed_sites'], 1)
        self.assertEqual(volta['site_completion_rate'], 100.0)   # BoQ signal
        self.assertEqual(volta['material_delivery_rate'], 100.0) # receipt
        self.assertEqual(volta['access_rate'], 100.0)            # consultant
        self.assertEqual(volta['energised_sites'], 1)
        shep = next(t for t in volta['by_project_type']
                    if t['project_type'] == 'SHEP')
        self.assertEqual(shep['completed_sites'], 1)

        national = payload['national']
        self.assertEqual(national['total_sites'], 1)
        self.assertEqual(national['completed_sites'], 1)
        self.assertEqual(national['material_delivery_rate'], 100.0)
        self.assertEqual(national['access_rate']['rate_pct'], 100.0)

        # Project status pages render with the data
        resp = self.client.get(reverse('project_management_dashboard'))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.get(reverse('project_detail',
                                       args=[self.project.code]))
        self.assertEqual(resp.status_code, 200)

        # ── Stage 9: Final state — archived, off the live board ───────
        self.client.force_login(self.storekeeper)
        resp = self.client.get(reverse('transportation_status'))
        self.assertNotIn(transport, resp.context['transports'])
        resp = self.client.get(reverse('transportation_archive'))
        self.assertIn(transport, resp.context['transports'])

        # Full audit trail exists for the order
        self.assertTrue(order.materialorderaudit_set.filter(
            action__icontains='Transporter assigned').exists())

    def test_site_progress_edit_gated_to_consultants_and_management(self):
        """The access-rate headline is only writable by the right roles."""
        url = reverse('site_progress_edit', args=[self.site.pk])

        # Storekeeper: bounced (user_passes_test redirects to login)
        self.client.force_login(self.storekeeper)
        self.assertEqual(self.client.post(url, {}).status_code, 302)
        self.site.refresh_from_db()
        self.assertEqual(self.site.progress_percent, 0)  # nothing written

        # Consultant and management: allowed through
        self.client.force_login(self.consultant)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(url).status_code, 200)
