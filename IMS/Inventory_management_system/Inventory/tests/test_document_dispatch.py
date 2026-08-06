"""Emailing release documents via Microsoft Graph.

The Graph call itself is mocked throughout — these tests are about the contract
around it:
  * attachments are the real stored PDFs, base64-encoded as Graph expects;
  * recipients resolve from user records and typed addresses, and a user with
    no address on file is reported rather than silently dropped;
  * a send that hasn't got documents yet is refused with a usable message;
  * every attempt is recorded, successes AND failures, so an un-actioned
    release is distinguishable from a rejected send;
  * a successful send moves the release to awaiting_signature; a failed one
    must not.
"""

import base64
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from Inventory.models import DocumentDispatch, ReleaseLetter
from Inventory.services.document_dispatch import (
    DispatchError, resolve_recipients, send_release_documents,
)

SEND = 'Inventory.services.document_dispatch.send_email_notification'


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class DispatchServiceTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(
            'sender', email='officer@energymin.gov.gh', password='pw',
            first_name='Ama', last_name='Owusu')
        self.director = User.objects.create_user(
            'director', email='cd@energymin.gov.gh', password='pw',
            first_name='Kwame', last_name='Mensah')
        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-SEND-1', title='Send Test', code='RE-2026-9301')
        self.letter.memo_pdf.save('memo.pdf', ContentFile(b'%PDF-1.4 memo'), save=False)
        self.letter.letter_pdf.save('letter.pdf', ContentFile(b'%PDF-1.4 letter'), save=True)

    # -- recipients -------------------------------------------------------
    def test_resolves_users_and_typed_addresses(self):
        addresses, matched = resolve_recipients(
            [self.director], ['external@example.com'])
        self.assertEqual(addresses, ['cd@energymin.gov.gh', 'external@example.com'])
        self.assertEqual(matched, [self.director])

    def test_duplicate_addresses_are_collapsed(self):
        addresses, _ = resolve_recipients([self.director], ['CD@energymin.gov.gh'])
        self.assertEqual(len(addresses), 1)

    def test_user_without_an_email_is_reported_not_dropped(self):
        nobody = User.objects.create_user('nomail', password='pw', first_name='No', last_name='Mail')
        with self.assertRaises(DispatchError) as cm:
            resolve_recipients([nobody], [])
        self.assertIn('No Mail', str(cm.exception))

    def test_invalid_typed_address_is_rejected(self):
        with self.assertRaises(DispatchError) as cm:
            resolve_recipients([], ['not-an-email'])
        self.assertIn('not-an-email', str(cm.exception))

    def test_no_recipients_at_all(self):
        with self.assertRaises(DispatchError):
            resolve_recipients([], [])

    # -- sending ----------------------------------------------------------
    def test_attaches_the_real_pdfs_base64_encoded(self):
        with patch(SEND, return_value={'success': True}) as mock:
            send_release_documents(self.letter, self.officer, users=[self.director])

        kwargs = mock.call_args.kwargs
        self.assertEqual(kwargs['to'], ['cd@energymin.gov.gh'])
        self.assertEqual(len(kwargs['attachments']), 2)
        decoded = [base64.b64decode(a['contentBytes']) for a in kwargs['attachments']]
        self.assertIn(b'%PDF-1.4 memo', decoded)
        self.assertIn(b'%PDF-1.4 letter', decoded)
        for att in kwargs['attachments']:
            self.assertEqual(att['@odata.type'], '#microsoft.graph.fileAttachment')
            self.assertEqual(att['contentType'], 'application/pdf')

    def test_only_the_selected_document_is_attached(self):
        with patch(SEND, return_value={'success': True}) as mock:
            send_release_documents(self.letter, self.officer, users=[self.director],
                                   include_memo=False, include_letter=True)
        attachments = mock.call_args.kwargs['attachments']
        self.assertEqual(len(attachments), 1)
        self.assertIn('letter', attachments[0]['name'])

    def test_refuses_when_nothing_is_selected(self):
        with self.assertRaises(DispatchError):
            send_release_documents(self.letter, self.officer, users=[self.director],
                                   include_memo=False, include_letter=False)

    def test_refuses_when_the_document_has_not_been_generated(self):
        blank = ReleaseLetter.objects.create(request_code='REQ-SEND-2', code='RE-2026-9302')
        with self.assertRaises(DispatchError) as cm:
            send_release_documents(blank, self.officer, users=[self.director])
        self.assertIn('generated', str(cm.exception).lower())

    def test_covering_note_is_html_escaped(self):
        with patch(SEND, return_value={'success': True}) as mock:
            send_release_documents(self.letter, self.officer, users=[self.director],
                                   message='Urgent <script>x</script> & fast')
        body = mock.call_args.kwargs['body']
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('<script>', body)

    # -- audit + workflow -------------------------------------------------
    def test_success_is_recorded_and_advances_the_workflow(self):
        self.letter.workflow_status = 'memo_generated'
        self.letter.save(update_fields=['workflow_status'])

        with patch(SEND, return_value={'success': True}):
            dispatch = send_release_documents(self.letter, self.officer, users=[self.director])

        self.assertEqual(dispatch.status, 'sent')
        self.assertEqual(dispatch.sent_by, self.officer)
        self.assertIn(self.director, dispatch.recipient_users.all())

        self.letter.refresh_from_db()
        self.assertEqual(self.letter.workflow_status, 'awaiting_signature')

    def test_failure_is_recorded_and_does_not_advance_the_workflow(self):
        self.letter.workflow_status = 'memo_generated'
        self.letter.save(update_fields=['workflow_status'])

        with patch(SEND, side_effect=RuntimeError('Graph API error [ErrorAccessDenied]')):
            with self.assertRaises(DispatchError):
                send_release_documents(self.letter, self.officer, users=[self.director])

        dispatch = DocumentDispatch.objects.get(release_letter=self.letter)
        self.assertEqual(dispatch.status, 'failed')
        self.assertIn('ErrorAccessDenied', dispatch.error)

        self.letter.refresh_from_db()
        self.assertEqual(self.letter.workflow_status, 'memo_generated')

    def test_missing_microsoft_login_gives_an_actionable_message(self):
        with patch(SEND, side_effect=RuntimeError('No Microsoft credentials found for user 1.')):
            with self.assertRaises(DispatchError) as cm:
                send_release_documents(self.letter, self.officer, users=[self.director])
        self.assertIn('Sign in with Microsoft', str(cm.exception))

    def test_memo_only_send_does_not_advance_the_workflow(self):
        """Only the letter goes for signature — a memo-only send isn't that."""
        self.letter.workflow_status = 'memo_generated'
        self.letter.save(update_fields=['workflow_status'])
        with patch(SEND, return_value={'success': True}):
            send_release_documents(self.letter, self.officer, users=[self.director],
                                   include_memo=True, include_letter=False)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.workflow_status, 'memo_generated')

    def test_an_approved_release_is_not_regressed(self):
        self.letter.workflow_status = 'approved'
        self.letter.save(update_fields=['workflow_status'])
        with patch(SEND, return_value={'success': True}):
            send_release_documents(self.letter, self.officer, users=[self.director])
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.workflow_status, 'approved')


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class DispatchViewTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(
            'officer2', email='o2@energymin.gov.gh', password='pw')
        self.officer.groups.add(Group.objects.get_or_create(name='Schedule Officers')[0])
        self.outsider = User.objects.create_user(
            'store2', email='s2@energymin.gov.gh', password='pw')
        self.outsider.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        self.director = User.objects.create_user(
            'cd2', email='cd2@energymin.gov.gh', password='pw')

        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-SEND-3', code='RE-2026-9303')
        self.letter.memo_pdf.save('memo.pdf', ContentFile(b'%PDF-1.4 memo'), save=False)
        self.letter.letter_pdf.save('letter.pdf', ContentFile(b'%PDF-1.4 letter'), save=True)

    def _url(self):
        return reverse('send_release_documents', args=[self.letter.pk])

    def test_officer_can_send(self):
        self.client.force_login(self.officer)
        with patch(SEND, return_value={'success': True}) as mock:
            resp = self.client.post(self._url(), {
                'recipient_users': [str(self.director.pk)],
                'include_memo': 'on', 'include_letter': 'on',
                'subject': 'Please sign', 'message': 'Thanks',
            })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(mock.called)
        self.assertEqual(DocumentDispatch.objects.filter(status='sent').count(), 1)

    def test_typed_addresses_split_on_commas_and_semicolons(self):
        self.client.force_login(self.officer)
        with patch(SEND, return_value={'success': True}) as mock:
            self.client.post(self._url(), {
                'recipient_emails': 'a@example.com; b@example.com,c@example.com',
                'include_letter': 'on',
            })
        self.assertEqual(sorted(mock.call_args.kwargs['to']),
                         ['a@example.com', 'b@example.com', 'c@example.com'])

    def test_bad_address_does_not_send_and_records_nothing(self):
        self.client.force_login(self.officer)
        with patch(SEND) as mock:
            self.client.post(self._url(), {
                'recipient_emails': 'nonsense', 'include_letter': 'on'})
        self.assertFalse(mock.called)
        self.assertEqual(DocumentDispatch.objects.count(), 0)

    def test_outsider_cannot_send(self):
        self.client.force_login(self.outsider)
        with patch(SEND) as mock:
            resp = self.client.post(self._url(), {
                'recipient_users': [str(self.director.pk)], 'include_letter': 'on'})
        self.assertIn(resp.status_code, (302, 403))
        self.assertFalse(mock.called)

    def test_history_appears_on_the_detail_page(self):
        self.client.force_login(self.officer)
        with patch(SEND, return_value={'success': True}):
            self.client.post(self._url(), {
                'recipient_users': [str(self.director.pk)], 'include_letter': 'on'})
        resp = self.client.get(reverse('release_letter_detail', args=[self.letter.pk]))
        self.assertContains(resp, 'cd2@energymin.gov.gh')
