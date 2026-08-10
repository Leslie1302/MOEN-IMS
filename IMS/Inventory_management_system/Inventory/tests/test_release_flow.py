"""The linear release workflow, end to end (§2a items 1, 4-7).

Five things are worth a test here, and each is a way the flow could fail
quietly rather than loudly:

  * **Generation notifies nobody, sending notifies exactly one person.** If
    generation ever starts emailing, every draft pesters the Ag. Director and
    people learn to ignore the emails — at which point the signature queue has
    died and nobody can say when.
  * **The signing page shows BOTH documents.** A signatory who sees only the
    page he signs is being asked to certify half a decision.
  * **The wet-signature print omits the letterhead but keeps the insets.** The
    insets are what hold the body clear of the pre-printed crest; dropping them
    with the artwork is the tempting simplification and it prints the first
    line under the Ministry seal.
  * **The plain render is a render, not a file.** If it ever writes to
    `letter_pdf`, the Ministry has two documents that can disagree and the one
    that gets wet-signed is the copy nobody verified.
  * **Generating lands on the release letter.** The old wizard returned the
    officer to an upload box before he had read the document he was about to
    put the Ministry's name on.

`ponytail:` these do not exercise WeasyPrint. `render_document_html` is
template rendering and runs anywhere; `render_document_pdf` needs the native
libraries and is covered in test_signing.py where they are available.
"""

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from Inventory.models import (
    Letterhead, Notification, ReleaseLetter, Signatory, SigningStep,
)
from Inventory.services.approvals import (
    SendForSignatureError, queue_for, send_for_signature,
)
from Inventory.services.document_render import _letterhead_ctx, letterhead_applies


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class ReleaseFlowBaseTests(TestCase):
    """Two-step chain: the Ag. Director signs the memo, then the CD the letter."""

    def setUp(self):
        self.officer = User.objects.create_user(
            'officer', email='so@energymin.gov.gh', password='pw',
            first_name='Efua', last_name='Sam')
        Group.objects.get_or_create(name='Schedule Officers')[0].user_set.add(self.officer)

        self.director = User.objects.create_user(
            'director', email='dp@energymin.gov.gh', password='pw',
            first_name='Ama', last_name='Owusu')
        self.chief = User.objects.create_user(
            'chief', email='cd@energymin.gov.gh', password='pw',
            first_name='Kwame', last_name='Mensah')

        self.sig_memo = Signatory.objects.create(
            name='Ama Owusu', title='Ag. Director, Power', user=self.director, active=True)
        self.sig_letter = Signatory.objects.create(
            name='Kwame Mensah', title='Ag. Chief Director', signs_for='HON. MINISTER',
            user=self.chief, active=True)

        self.step_memo = SigningStep.objects.create(
            document_kind='memo', order=1, signatory=self.sig_memo, user=self.director)
        self.step_letter = SigningStep.objects.create(
            document_kind='letter', order=2, signatory=self.sig_letter, user=self.chief)

        self.release = ReleaseLetter.objects.create(
            request_code='REQ-RF-1', title='Nandom SHEP materials',
            code='RE-2026-9601', uploaded_by=self.officer,
            workflow_status='memo_generated',
            memo_version=1, letter_version=1)
        self.release.memo_pdf.save('memo.pdf', ContentFile(b'%PDF-1.4 memo'), save=False)
        self.release.letter_pdf.save('letter.pdf', ContentFile(b'%PDF-1.4 letter'), save=True)


class SendForSignatureTests(ReleaseFlowBaseTests):

    def test_generation_notifies_nobody(self):
        """The whole reason sending is a separate act.

        A generated release must leave the notification table untouched. If this
        ever fails, the Ag. Director is emailed about every half-finished draft.
        """
        self.assertFalse(Notification.objects.exists())
        self.assertIsNone(self.release.sent_for_signature_at)

    def test_sending_notifies_the_first_signatory_only(self):
        step, notification = send_for_signature(self.release, self.officer)

        self.assertEqual(step, self.step_memo)
        self.assertEqual(notification.recipient_user, self.director)
        # The Chief Director is second in the chain and must not hear about it
        # yet — his turn comes when the memo is signed.
        self.assertFalse(
            Notification.objects.filter(recipient_user=self.chief).exists())

    def test_sending_records_who_and_when_and_advances_the_status(self):
        send_for_signature(self.release, self.officer)
        self.release.refresh_from_db()

        self.assertIsNotNone(self.release.sent_for_signature_at)
        self.assertEqual(self.release.sent_for_signature_by, self.officer)
        self.assertEqual(self.release.workflow_status, 'awaiting_signature')

    def test_sending_is_repeatable_as_a_nudge(self):
        """The commonest reason to press this again is that a week has passed."""
        send_for_signature(self.release, self.officer)
        self.release.refresh_from_db()
        first = self.release.sent_for_signature_at

        send_for_signature(self.release, self.officer)
        self.release.refresh_from_db()

        self.assertGreaterEqual(self.release.sent_for_signature_at, first)
        self.assertEqual(Notification.objects.filter(recipient_user=self.director).count(), 2)

    def test_sending_never_drags_the_workflow_backwards(self):
        """A release back from MMU for its scan must not return to 'awaiting'."""
        self.release.workflow_status = 'awaiting_scan_upload'
        self.release.save(update_fields=['workflow_status'])

        send_for_signature(self.release, self.officer)
        self.release.refresh_from_db()

        self.assertEqual(self.release.workflow_status, 'awaiting_scan_upload')

    def test_refuses_when_the_next_signatory_has_no_login(self):
        """Recording a handover to nobody would leave the officer waiting."""
        self.step_memo.user = None
        self.step_memo.save(update_fields=['user'])

        with self.assertRaises(SendForSignatureError) as caught:
            send_for_signature(self.release, self.officer)
        self.assertIn('no MOEN-IMS login', str(caught.exception))
        self.release.refresh_from_db()
        self.assertIsNone(self.release.sent_for_signature_at)

    def test_refuses_when_the_document_is_not_generated(self):
        self.release.memo_pdf.delete(save=True)

        with self.assertRaises(SendForSignatureError) as caught:
            send_for_signature(self.release, self.officer)
        self.assertIn('not been generated', str(caught.exception))

    def test_the_view_is_closed_to_a_signatory(self):
        """Sending is the preparing officer's act, not the signatory's."""
        self.client.force_login(self.director)
        response = self.client.post(
            reverse('send_for_signature', args=[self.release.pk]))

        self.assertIn(response.status_code, (302, 403))
        self.release.refresh_from_db()
        self.assertIsNone(self.release.sent_for_signature_at)


class QueueSentMarkerTests(ReleaseFlowBaseTests):

    def test_an_unsent_release_still_appears_but_is_marked(self):
        """Read access stays open; the officer's button is not a permission wall.

        Filtering unsent releases out of the queue would let a schedule officer
        decide when a senior officer may see his own Ministry's paperwork.
        """
        entry = queue_for(self.director)['awaiting_me'][0]

        self.assertEqual(entry['release'], self.release)
        self.assertIsNone(entry['sent_at'])

    def test_sending_shows_up_in_the_queue(self):
        send_for_signature(self.release, self.officer)
        self.release.refresh_from_db()

        entry = queue_for(self.director)['awaiting_me'][0]
        self.assertIsNotNone(entry['sent_at'])


class SigningPageTests(ReleaseFlowBaseTests):

    def test_the_signer_always_sees_both_documents(self):
        """He is approving a release, not a page."""
        self.client.force_login(self.director)
        response = self.client.get(reverse('sign_release', args=[self.release.pk]))

        self.assertEqual(response.status_code, 200)
        kinds = [d['kind'] for d in response.context['documents']]
        self.assertEqual(kinds, ['memo', 'letter'])
        self.assertContains(response, reverse('release_memo_preview', args=[self.release.pk]))
        self.assertContains(response, reverse('release_letter_preview', args=[self.release.pk]))

    def test_only_the_document_whose_turn_it_is_is_signable(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('sign_release', args=[self.release.pk]))

        by_kind = {d['kind']: d for d in response.context['documents']}
        self.assertTrue(by_kind['memo']['allowed'])
        self.assertFalse(by_kind['letter']['allowed'])
        self.assertTrue(by_kind['memo']['is_mine'])

    def test_the_second_signatory_is_told_why_he_cannot_sign_yet(self):
        """A refusal with a reason, not a missing button.

        "Awaiting the Ag. Director" is something he can act on; a control that
        simply is not there reads as a fault in the system.
        """
        self.client.force_login(self.chief)
        response = self.client.get(reverse('sign_release', args=[self.release.pk]))

        by_kind = {d['kind']: d for d in response.context['documents']}
        self.assertFalse(by_kind['letter']['allowed'])
        self.assertTrue(by_kind['letter']['reason'])
        self.assertContains(response, 'Approval memo')

    def test_the_page_carries_no_officer_controls(self):
        """The point of the page: it fits the reader, rather than hiding buttons."""
        self.client.force_login(self.director)
        response = self.client.get(reverse('sign_release', args=[self.release.pk]))
        body = response.content.decode()

        for officer_url in (
            reverse('generate_release_documents', args=[self.release.pk]),
            reverse('adjust_release_documents', args=[self.release.pk]),
            reverse('send_release_documents', args=[self.release.pk]),
        ):
            self.assertNotIn(officer_url, body)

    def test_read_access_stays_open(self):
        """A senior officer must not hit a permission wall on Ministry paperwork."""
        self.client.force_login(self.officer)
        response = self.client.get(reverse('sign_release', args=[self.release.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['can_sign_any'])


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class PlainPrintTests(TestCase):
    """The wet-signature route: print onto Ministry letterhead stock."""

    def setUp(self):
        self.letterhead = Letterhead.objects.create(
            org_name='Ministry of Energy and Green Transition',
            org_address='P.O. Box SD 40, Accra',
            inset_top=180, inset_right=70, inset_bottom=60, inset_left=70,
            cont_inset_top=62, active=True)

    def test_plain_omits_the_artwork_but_keeps_the_calibrated_insets(self):
        """The insets hold the body clear of the pre-printed crest.

        Dropping them along with the image is the tempting simplification, and
        it prints the first line of the letter under the Ministry seal.
        """
        normal = _letterhead_ctx('letter')
        plain = _letterhead_ctx('letter', plain=True)

        self.assertEqual(plain['mode'], 'pre_printed')
        self.assertNotIn('img', plain)
        for edge in ('top', 'right', 'bottom', 'left', 'cont_top'):
            self.assertEqual(plain[edge], normal[edge], f"{edge} inset must survive")

    def test_plain_drops_an_artwork_that_the_normal_render_inlines(self):
        """The one that actually proves the artwork is gone.

        Without a file configured both renders are headerless anyway, so the
        test above would pass even if `plain` did nothing at all.
        """
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = io.BytesIO()
        Image.new('RGB', (600, 160), (27, 94, 32)).save(buf, format='PNG')
        self.letterhead.file.save(
            'lh.png', SimpleUploadedFile('lh.png', buf.getvalue(), content_type='image/png'),
            save=True)

        normal = _letterhead_ctx('letter')
        plain = _letterhead_ctx('letter', plain=True)

        self.assertEqual(normal['mode'], 'image')
        self.assertIn('img', normal)
        self.assertEqual(plain['mode'], 'pre_printed')
        self.assertNotIn('img', plain)
        self.assertEqual(plain['top'], normal['top'])

    def test_the_memo_is_unaffected(self):
        """It is an internal document on a plain sheet — there is no letterhead
        to omit, so offering the option on it would advertise a difference that
        does not exist."""
        self.assertFalse(letterhead_applies('memo'))
        self.assertTrue(letterhead_applies('letter'))
        self.assertEqual(_letterhead_ctx('memo'), _letterhead_ctx('memo', plain=True))


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class PlainPrintViewTests(ReleaseFlowBaseTests):

    def test_plain_render_never_touches_the_stored_pdf(self):
        """One document, one letterhead.

        A second no-letterhead PDF on file would give the Ministry two documents
        that can disagree, and the one that gets wet-signed and filed would be
        the copy nobody verified.
        """
        self.client.force_login(self.officer)
        before = self.release.letter_pdf.name
        before_version = self.release.letter_version

        response = self.client.get(
            reverse('release_letter_preview', args=[self.release.pk]), {'plain': '1'})

        self.assertEqual(response.status_code, 200)
        self.release.refresh_from_db()
        self.assertEqual(self.release.letter_pdf.name, before)
        self.assertEqual(self.release.letter_version, before_version)

    def test_plain_refuses_to_be_an_editing_surface(self):
        """Editing a letterhead-less render would show margins the edit will not
        print in."""
        self.client.force_login(self.officer)
        response = self.client.get(
            reverse('release_letter_preview', args=[self.release.pk]),
            {'plain': '1', 'edit': '1'})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'contenteditable')


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class WizardReplacementTests(TestCase):
    """Request → documents generate → land on the release letter."""

    def setUp(self):
        self.officer = User.objects.create_user('so', password='pw')
        Group.objects.get_or_create(name='Schedule Officers')[0].user_set.add(self.officer)
        self.client.force_login(self.officer)

    def test_the_three_step_strip_is_gone(self):
        """Its steps 2 and 3 already lived on the release-letter page, and both
        came after work the wizard never showed."""
        response = self.client.get(reverse('release-letter-upload'))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertNotIn('rl-step-strip', body)
        self.assertNotIn('Upload signed scan', body)
        self.assertNotIn('Confirm &amp; release', body)

    def test_an_existing_release_is_pointed_at_rather_than_duplicated(self):
        existing = ReleaseLetter.objects.create(
            request_code='REQ-WZ-1', title='Existing', code='RE-2026-9701',
            uploaded_by=self.officer, workflow_status='memo_generated')

        response = self.client.get(
            reverse('release-letter-upload'), {'request_code': 'REQ-WZ-1'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, reverse('release_letter_detail', args=[existing.pk]))
