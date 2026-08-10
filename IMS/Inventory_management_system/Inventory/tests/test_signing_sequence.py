"""The signing chain spans BOTH documents in one sequence.

The bug this fixes: chains were per-document and independent, so nothing stopped
the Chief Director signing the release letter before the Ag. Director had
approved the memo. That is backwards — **the signed memo is the authority for
the letter.**

The sequence is: 1 = Ag. Director Power signs the memo, 2 = Chief Director signs
the letter. Adding a third approver is a row, not a code change.
"""

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from Inventory.models import (
    Profile, ReleaseLetter, Signatory, SigningStep,
)
from Inventory.services.signing import can_sign


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class SigningSequenceTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user('dp', password='pw')
        self.chief = User.objects.create_user('cd', password='pw')
        Profile.objects.update_or_create(
            user=self.director, defaults={'designation': 'Director, Power'})
        Profile.objects.update_or_create(
            user=self.chief, defaults={'designation': 'Director, Finance'})

        self.sig_dp = Signatory.objects.create(
            name='Ing. Sulemana Abubakari', title='Ag. Director, Power',
            user=self.director, active=True)
        self.sig_cd = Signatory.objects.create(
            name='Solomon Adjetey Sowah', title='Chief Director',
            signs_for='HON. MINISTER', user=self.chief, active=True)

        # One sequence across both documents.
        self.step_memo = SigningStep.objects.create(
            document_kind='memo', order=1, signatory=self.sig_dp, user=self.director)
        self.step_letter = SigningStep.objects.create(
            document_kind='letter', order=2, signatory=self.sig_cd, user=self.chief)

        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-SEQ-1', code='RE-2026-9601',
            memo_version=1, letter_version=1)
        self.letter.memo_pdf.save('memo.pdf', ContentFile(b'%PDF-1.4 memo'), save=False)
        self.letter.letter_pdf.save('letter.pdf', ContentFile(b'%PDF-1.4 letter'), save=True)

    def _sign(self, user, kind):
        from Inventory.tests.test_signing import _signature_data_uri
        from Inventory.services.signing import apply_signature
        return apply_signature(self.letter, user, kind, _signature_data_uri())

    # -- the ordering -------------------------------------------------------
    def test_the_memo_is_first_in_the_release_sequence(self):
        step = self.letter.next_signing_step()
        self.assertEqual(step, self.step_memo)

    def test_the_chief_director_cannot_sign_the_letter_first(self):
        """The bug. The signed memo is the authority for the letter."""
        allowed, _, reason = can_sign(self.chief, self.letter, 'letter')
        self.assertFalse(allowed)
        self.assertIn('must be signed first', reason)
        self.assertIn('Ag. Director, Power', reason)

    def test_the_director_can_sign_the_memo_first(self):
        allowed, step, reason = can_sign(self.director, self.letter, 'memo')
        self.assertTrue(allowed, reason)
        self.assertEqual(step, self.step_memo)

    def test_the_letter_unlocks_once_the_memo_is_signed(self):
        self._sign(self.director, 'memo')
        allowed, step, reason = can_sign(self.chief, self.letter, 'letter')
        self.assertTrue(allowed, reason)
        self.assertEqual(step, self.step_letter)

    def test_the_release_sequence_advances_to_the_letter(self):
        self._sign(self.director, 'memo')
        self.assertEqual(self.letter.next_signing_step(), self.step_letter)

    def test_the_chain_completes_after_both(self):
        self._sign(self.director, 'memo')
        self._sign(self.chief, 'letter')
        self.assertIsNone(self.letter.next_signing_step())
        self.assertTrue(self.letter.signing_complete())
        self.assertTrue(self.letter.signing_complete('memo'))
        self.assertTrue(self.letter.signing_complete('letter'))

    # -- per-document completeness -----------------------------------------
    def test_the_memo_alone_does_not_complete_the_release(self):
        self._sign(self.director, 'memo')
        self.assertTrue(self.letter.signing_complete('memo'))
        self.assertFalse(self.letter.signing_complete())

    def test_locking_is_per_document(self):
        """Signing the memo must not freeze the letter, which is still to be
        edited and signed."""
        self._sign(self.director, 'memo')
        self.letter.refresh_from_db()
        self.assertTrue(self.letter.memo_locked)
        self.assertFalse(self.letter.letter_locked)

    # -- the chain lives in data -------------------------------------------
    def test_a_third_approver_is_a_row_not_a_code_change(self):
        deputy = User.objects.create_user('deputy', password='pw')
        step3 = SigningStep.objects.create(
            document_kind='letter', order=3,
            signatory=Signatory.objects.create(
                name='A. Deputy', title='Deputy Minister', user=deputy),
            user=deputy)

        self._sign(self.director, 'memo')
        self._sign(self.chief, 'letter')

        self.assertEqual(self.letter.next_signing_step(), step3)
        self.assertFalse(self.letter.signing_complete())

    def test_an_inactive_step_is_skipped(self):
        self.step_memo.active = False
        self.step_memo.save(update_fields=['active'])
        self.assertEqual(self.letter.next_signing_step(), self.step_letter)

    def test_an_optional_step_does_not_block_the_chain(self):
        self.step_memo.required = False
        self.step_memo.save(update_fields=['required'])
        self.assertEqual(self.letter.next_signing_step(), self.step_letter)
