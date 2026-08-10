"""A confirmed signed scan closes the release, exactly as an in-system signature does.

Two defects this covers:

  * **The document stayed editable after being signed on paper.** Confirming a
    scan advanced the status but never locked, so an officer could alter wording
    the Chief Director had already put his name to — and the stored PDF would no
    longer match the scan filed beside it.

  * **The pipeline stalled at approved.** `MarkReleasedView` existed and worked,
    but no template linked to it. The automatic path depends on the consignee
    scanning the waybill QR; when that did not happen the release sat at
    Approved permanently with no way forward.
"""

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from Inventory.models import ReleaseLetter


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class ScanClosesWorkflowTests(TestCase):
    def setUp(self):
        group = Group.objects.get_or_create(name='Schedule Officers')[0]
        self.uploader = User.objects.create_user('uploader', password='pw')
        self.uploader.groups.add(group)
        self.confirmer = User.objects.create_user('confirmer', password='pw')
        self.confirmer.groups.add(group)

        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-SCAN-1', code='RE-2026-9501',
            workflow_status='awaiting_scan_upload', uploaded_by=self.uploader)
        self.letter.pdf_file.save('scan.pdf', ContentFile(b'%PDF-1.4 scan'), save=True)

    def _confirm(self):
        self.client.force_login(self.confirmer)
        return self.client.post(
            reverse('release_letter_confirm_scan', args=[self.letter.pk]))

    # -- locking -----------------------------------------------------------
    def test_confirming_a_scan_locks_both_documents(self):
        self._confirm()
        self.letter.refresh_from_db()
        self.assertTrue(self.letter.letter_locked)
        self.assertTrue(self.letter.memo_locked)

    def test_a_locked_document_cannot_be_edited_afterwards(self):
        """The whole point: no altering wording that has been signed on paper."""
        self._confirm()
        self.client.force_login(self.uploader)
        resp = self.client.post(
            reverse('save_document_html', args=[self.letter.pk, 'letter']),
            {'html': '<p>changed after the Chief Director signed</p>'})
        self.assertEqual(resp.status_code, 409)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.letter_html, '')

    def test_a_locked_document_cannot_be_regenerated(self):
        self._confirm()
        self.client.force_login(self.uploader)
        resp = self.client.post(
            reverse('generate_release_documents', args=[self.letter.pk]), follow=True)
        self.assertContains(resp, 'signed and is locked')

    def test_the_two_person_rule_still_holds(self):
        """Locking must not have loosened the confirmation control."""
        self.client.force_login(self.uploader)
        self.client.post(reverse('release_letter_confirm_scan', args=[self.letter.pk]))
        self.letter.refresh_from_db()
        self.assertNotEqual(self.letter.workflow_status, 'approved')
        self.assertFalse(self.letter.letter_locked)

    # -- the stall ---------------------------------------------------------
    def test_approved_offers_a_way_forward(self):
        """It previously stalled here: the view existed, the link did not."""
        self._confirm()
        self.client.force_login(self.confirmer)
        resp = self.client.get(reverse('release_letter_detail', args=[self.letter.pk]))
        self.assertContains(resp, 'Mark as released manually')

    def test_marking_released_advances_the_pipeline(self):
        self._confirm()
        self.client.force_login(self.confirmer)
        self.client.post(reverse('release_letter_mark_released', args=[self.letter.pk]))
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.workflow_status, 'released')
        self.assertGreater(self.letter.get_pipeline_step(), 5)
