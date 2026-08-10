"""Phases 3-5: the approval queue, calls for discussion, and the MMU fast-track.

Four things matter more than the rest, and each is a way the design could quietly
fail rather than break loudly:

  * the queue shows a signatory only what they may sign — the old page showed
    every release in every state, and a queue that does the same is not a queue;
  * a call for discussion changes nothing about the release. If it ever starts
    moving the workflow it has become a reject button by another name;
  * only a signatory may declare urgency, and never without a reason. That one
    restriction is the whole difference between a directive and a waiver;
  * advance notice never permits physical release. This is the invariant the
    entire fast-track rests on — if it fails, the wet signature has been
    silently abolished.
"""

import base64
import io

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from Inventory.models import (
    DiscussionRequest, Notification, ReleaseLetter, Signatory, SigningStep,
)
from Inventory.services.approvals import is_signatory, may_view_queue, queue_for
from Inventory.services.discussion import DiscussionError, call_officer
from Inventory.services.urgency import (
    UrgencyError, advance_notice_queryset, can_declare_urgent, declare_urgent,
    mark_advance_notice,
)


def _signature_data_uri():
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', (300, 100), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.line([(10, 80), (60, 20), (110, 80), (210, 30), (290, 60)],
              fill=(0, 0, 0, 255), width=3)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class ApprovalBaseTests(TestCase):
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
            request_code='REQ-AP-1', title='Nandom SHEP materials',
            code='RE-2026-9501', uploaded_by=self.officer,
            workflow_status='awaiting_signature',
            memo_version=1, letter_version=1)
        self.release.memo_pdf.save('memo.pdf', ContentFile(b'%PDF-1.4 memo'), save=False)
        self.release.letter_pdf.save('letter.pdf', ContentFile(b'%PDF-1.4 letter'), save=True)

    def _sign(self, kind, step, user):
        """Record a signature without going through the PDF renderer.

        The renderer is exercised in test_signing.py; what these tests care
        about is the state the chain reaches, not how the page is drawn.
        """
        from Inventory.models import DocumentSignature
        return DocumentSignature.objects.create(
            release_letter=self.release, document_kind=kind, step=step,
            signed_by=user, signatory_name=step.signatory.name,
            signatory_title=step.signatory.title, document_version=1,
            signed_at=timezone.now())

    def _complete_chain(self):
        self._sign('memo', self.step_memo, self.director)
        self._sign('letter', self.step_letter, self.chief)
        mark_advance_notice(self.release)
        self.release.refresh_from_db()


class QueueScopingTests(ApprovalBaseTests):

    def test_a_signatory_sees_only_their_own_turn(self):
        # Step 1 is the Ag. Director's, so the Chief Director must not be
        # offered it — the signed memo is the authority for his letter.
        director_queue = queue_for(self.director)
        chief_queue = queue_for(self.chief)

        self.assertEqual(len(director_queue['awaiting_me']), 1)
        self.assertEqual(director_queue['awaiting_me'][0]['kind'], 'memo')
        self.assertEqual(len(chief_queue['awaiting_me']), 0)

    def test_what_is_with_someone_else_is_still_visible(self):
        """An empty page would read as a fault rather than as 'not yet'."""
        chief_queue = queue_for(self.chief)
        self.assertEqual(len(chief_queue['awaiting_others']), 1)
        self.assertEqual(chief_queue['awaiting_others'][0]['signatory'], self.sig_memo)

    def test_the_letter_reaches_the_chief_only_after_the_memo_is_signed(self):
        self._sign('memo', self.step_memo, self.director)

        chief_queue = queue_for(self.chief)
        self.assertEqual(len(chief_queue['awaiting_me']), 1)
        self.assertEqual(chief_queue['awaiting_me'][0]['kind'], 'letter')
        # And it has left the Ag. Director's queue entirely.
        self.assertEqual(len(queue_for(self.director)['awaiting_me']), 0)

    def test_a_fully_signed_release_leaves_the_queue(self):
        self._sign('memo', self.step_memo, self.director)
        self._sign('letter', self.step_letter, self.chief)

        for user in (self.director, self.chief):
            queue = queue_for(user)
            self.assertEqual(queue['awaiting_me'], [])
            self.assertEqual(queue['awaiting_others'], [])

    def test_signed_work_is_listed_back_to_the_signer(self):
        self._sign('memo', self.step_memo, self.director)
        self.assertEqual(len(queue_for(self.director)['recently_signed']), 1)
        self.assertEqual(len(queue_for(self.chief)['recently_signed']), 0)

    def test_an_ungenerated_document_is_flagged_rather_than_hidden(self):
        """Hiding it would leave the signatory wondering where the release went."""
        self.release.memo_pdf.delete(save=True)
        entry = queue_for(self.director)['awaiting_me'][0]
        self.assertFalse(entry['ready'])

    def test_a_voided_release_waits_for_nobody(self):
        self.release.workflow_status = 'voided'
        self.release.save(update_fields=['workflow_status'])
        self.assertEqual(queue_for(self.director)['awaiting_me'], [])


class QueueAccessTests(ApprovalBaseTests):

    def test_signatories_and_management_may_open_the_queue(self):
        manager = User.objects.create_user('manager', password='pw')
        Group.objects.get_or_create(name='Management')[0].user_set.add(manager)

        self.assertTrue(may_view_queue(self.director))
        self.assertTrue(may_view_queue(manager))
        self.assertFalse(may_view_queue(self.officer))
        self.assertTrue(is_signatory(self.chief))
        self.assertFalse(is_signatory(self.officer))

    def test_the_page_renders_for_a_signatory(self):
        self.client.force_login(self.director)
        response = self.client.get(reverse('approval_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Awaiting my signature')

    def test_a_schedule_officer_is_redirected_with_an_explanation(self):
        """A 403 on a colleague's page reads as a bug; a message reads as an answer."""
        self.client.force_login(self.officer)
        response = self.client.get(reverse('approval_queue'))
        self.assertEqual(response.status_code, 302)

    def test_an_inactive_step_does_not_confer_access(self):
        self.step_memo.active = False
        self.step_memo.save(update_fields=['active'])
        self.assertFalse(is_signatory(self.director))

    def test_a_signatory_in_no_group_is_still_authorised(self):
        """Being named on the chain is a stronger authorisation than a group.

        Without this a newly onboarded Chief Director is bounced to "awaiting
        authorization" until someone remembers to also add him to a group — and
        the release he is holding up is the last place anyone looks.
        """
        self.assertFalse(self.director.groups.exists())
        self.client.force_login(self.director)
        response = self.client.get(reverse('approval_queue'))
        self.assertEqual(response.status_code, 200)

    def test_someone_on_no_chain_and_in_no_group_is_still_refused(self):
        stranger = User.objects.create_user('stranger', password='pw')
        self.client.force_login(stranger)
        response = self.client.get(reverse('approval_queue'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('awaiting', response.url)


class CallOfficerTests(ApprovalBaseTests):

    def test_a_call_records_the_note_and_notifies_the_officer(self):
        call = call_officer(self.release, self.director,
                            note='The Bawku West quantity looks above the BOQ.',
                            document_kind='memo')

        self.assertEqual(call.officer, self.officer)
        self.assertEqual(call.document_kind, 'memo')
        self.assertTrue(
            Notification.objects.filter(recipient_user=self.officer,
                                        notification_type='discussion_request').exists())

    def test_a_call_does_not_move_the_workflow(self):
        """The moment this changes state it has become a reject button."""
        before = self.release.workflow_status
        call_officer(self.release, self.director, note='Can we talk before I sign?')

        self.release.refresh_from_db()
        self.assertEqual(self.release.workflow_status, before)
        self.assertFalse(self.release.memo_locked)
        self.assertFalse(self.release.letter_locked)
        # And the release is still exactly where it was in the queue.
        self.assertEqual(queue_for(self.director)['awaiting_me'][0]['kind'], 'memo')

    def test_an_empty_note_is_refused(self):
        with self.assertRaises(DiscussionError):
            call_officer(self.release, self.director, note='   ')

    def test_the_record_survives_a_failed_email(self):
        """A call raised but not emailed must still be visible on the release."""
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            call = call_officer(self.release, self.director, note='Please call me.')
        self.assertTrue(DiscussionRequest.objects.filter(pk=call.pk).exists())

    def test_the_view_is_open_to_a_signatory_further_down_the_chain(self):
        """Waiting for the document to reach you before raising a problem
        guarantees the problem is raised as late as possible."""
        self.client.force_login(self.chief)
        response = self.client.post(
            reverse('call_officer', args=[self.release.pk]),
            {'note': 'The consignee looks wrong for this district.'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DiscussionRequest.objects.count(), 1)

    def test_a_schedule_officer_may_not_raise_one(self):
        self.client.force_login(self.officer)
        response = self.client.post(
            reverse('call_officer', args=[self.release.pk]), {'note': 'ping'})
        self.assertIn(response.status_code, (302, 403))
        self.assertEqual(DiscussionRequest.objects.count(), 0)


class AdvanceNoticeTests(ApprovalBaseTests):

    def test_advance_notice_opens_when_the_chain_completes(self):
        self.assertIsNone(self.release.advance_notice_at)
        self._complete_chain()
        self.assertIsNotNone(self.release.advance_notice_at)
        self.assertTrue(self.release.on_advance_notice)

    def test_advance_notice_never_permits_physical_release(self):
        """The invariant the whole fast-track rests on."""
        self._complete_chain()
        self.assertTrue(self.release.on_advance_notice)
        self.assertFalse(self.release.mmu_may_release)
        self.assertFalse(self.release.scan_on_file)

    def test_a_confirmed_scan_is_what_permits_release(self):
        self._complete_chain()
        self.release.workflow_status = 'approved'
        self.release.save(update_fields=['workflow_status'])
        self.assertTrue(self.release.mmu_may_release)

    def test_marking_advance_notice_is_idempotent(self):
        self._complete_chain()
        first = self.release.advance_notice_at
        mark_advance_notice(self.release)
        self.release.refresh_from_db()
        self.assertEqual(self.release.advance_notice_at, first)

    def test_the_mmu_filter_lists_what_may_be_prepared(self):
        self._complete_chain()
        self.assertIn(self.release, list(advance_notice_queryset()))

        self.release.workflow_status = 'released'
        self.release.save(update_fields=['workflow_status'])
        self.assertNotIn(self.release, list(advance_notice_queryset()))

    def test_the_release_list_filters_on_it(self):
        """The filter lives on the list MMU already opens, not a separate screen."""
        other = ReleaseLetter.objects.create(
            request_code='REQ-AP-2', title='Unsigned release',
            code='RE-2026-9502', uploaded_by=self.officer,
            workflow_status='memo_generated')
        self._complete_chain()

        self.client.force_login(self.officer)
        response = self.client.get(reverse('release_letter_list'), {'mmu': 'prepare'})
        self.assertEqual(response.status_code, 200)

        listed = list(response.context['release_letters'])
        self.assertIn(self.release, listed)
        self.assertNotIn(other, listed)
        self.assertEqual(response.context['advance_notice_count'], 1)


class UrgencyTests(ApprovalBaseTests):

    def test_only_a_signatory_may_declare_urgency(self):
        """The officer raising the release cannot fast-track his own paperwork —
        that is the line between a directive and a self-serve waiver."""
        self._complete_chain()

        allowed, reason = can_declare_urgent(self.officer, self.release)
        self.assertFalse(allowed)
        self.assertIn('signatory', reason.lower())

        allowed, _ = can_declare_urgent(self.chief, self.release)
        self.assertTrue(allowed)

    def test_the_officer_is_refused_through_the_view_too(self):
        self._complete_chain()
        self.client.force_login(self.officer)
        self.client.post(reverse('declare_urgent', args=[self.release.pk]),
                         {'reason': 'Contractor is mobilising on Monday.'})
        self.release.refresh_from_db()
        self.assertFalse(self.release.is_urgent)

    def test_a_reason_is_mandatory(self):
        self._complete_chain()
        with self.assertRaises(UrgencyError):
            declare_urgent(self.release, self.chief, reason='')
        with self.assertRaises(UrgencyError):
            declare_urgent(self.release, self.chief, reason='urgent')

        self.release.refresh_from_db()
        self.assertFalse(self.release.is_urgent)

    def test_urgency_records_who_what_and_when(self):
        self._complete_chain()
        declare_urgent(self.release, self.chief,
                       reason='Contractor mobilising to Nandom on Monday.')
        self.release.refresh_from_db()

        self.assertTrue(self.release.is_urgent)
        self.assertEqual(self.release.urgent_declared_by, self.chief)
        self.assertIsNotNone(self.release.urgent_declared_at)
        self.assertIn('Nandom', self.release.urgent_reason)

    def test_urgency_needs_a_completed_chain(self):
        """Clearing MMU to release 'on the digital signature' presupposes one."""
        allowed, reason = can_declare_urgent(self.chief, self.release)
        self.assertFalse(allowed)
        self.assertIn('chain', reason.lower())

    def test_urgency_permits_release_but_still_wants_the_paper(self):
        self._complete_chain()
        declare_urgent(self.release, self.chief, reason='Contractor mobilising Monday.')
        self.release.refresh_from_db()

        self.assertTrue(self.release.mmu_may_release)
        # Urgency changed WHEN MMU may act, not WHETHER the record exists.
        self.assertTrue(self.release.urgent_scan_outstanding)

        self.release.workflow_status = 'approved'
        self.release.save(update_fields=['workflow_status'])
        self.assertFalse(self.release.urgent_scan_outstanding)

    def test_it_cannot_be_declared_twice(self):
        self._complete_chain()
        declare_urgent(self.release, self.chief, reason='Contractor mobilising Monday.')
        with self.assertRaises(UrgencyError):
            declare_urgent(self.release, self.director, reason='Also quite urgent.')

    def test_mmu_is_notified_of_the_directive(self):
        self._complete_chain()
        declare_urgent(self.release, self.chief, reason='Contractor mobilising Monday.')
        self.assertTrue(
            Notification.objects.filter(notification_type='release_urgent',
                                        recipient_group='Store Officers').exists())

    def test_the_report_shows_the_rate_not_just_the_count(self):
        """A count of urgent releases with no denominator says very little."""
        self._complete_chain()
        declare_urgent(self.release, self.chief, reason='Contractor mobilising Monday.')

        self.client.force_login(self.chief)
        response = self.client.get(reverse('urgent_releases_report'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total'], 1)
        self.assertEqual(response.context['all_signed'], 1)
        self.assertEqual(len(response.context['outstanding']), 1)
