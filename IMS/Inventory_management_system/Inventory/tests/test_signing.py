"""In-app signing: chain order, the authority stamp, and the lock on signed documents.

Three invariants matter more than the rest:

  * a step cannot be signed out of turn;
  * a signed document cannot be regenerated — otherwise a signature ends up over
    content the signatory never saw;
  * the stamp records the office signed in AND the substantive designation, so
    an acting appointment is unambiguous on the record.
"""

import base64
import io
import importlib.util

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse

from Inventory.models import (
    DocumentSignature, Profile, ReleaseLetter, Signatory, SigningStep,
)
from Inventory.services.signing import (
    SigningError, apply_signature, can_sign, decode_signature_png, supersede_signatures,
)

WEASYPRINT = importlib.util.find_spec('weasyprint') is not None


def _signature_data_uri(size=(300, 100)):
    """A drawn-signature stand-in: a real PNG with enough content to pass the
    blank-canvas check."""
    from PIL import Image, ImageDraw
    img = Image.new('RGBA', size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.line([(10, 80), (60, 20), (110, 80), (160, 20), (210, 70), (290, 40)],
              fill=(0, 0, 0, 255), width=3)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class SigningChainTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(
            'director', email='dp@energymin.gov.gh', password='pw',
            first_name='Ama', last_name='Owusu')
        self.chief = User.objects.create_user(
            'chief', email='cd@energymin.gov.gh', password='pw',
            first_name='Kwame', last_name='Mensah')
        # Acting appointment: substantive post differs from the office signed in.
        Profile.objects.update_or_create(
            user=self.chief, defaults={'designation': 'Director, Finance'})
        Profile.objects.update_or_create(
            user=self.director, defaults={'designation': 'Director, Power'})

        self.sig_memo = Signatory.objects.create(
            name='Ama Owusu', title='Ag. Director, Power', user=self.director, active=True)
        self.sig_letter = Signatory.objects.create(
            name='Kwame Mensah', title='Ag. Chief Director', signs_for='HON. MINISTER',
            user=self.chief, active=True)

        # One sequence across both documents: memo first, then letter. Both
        # used to be order=1, which is what allowed the letter to be signed
        # before the memo — see test_signing_sequence.py.
        self.step_memo = SigningStep.objects.create(
            document_kind='memo', order=1, signatory=self.sig_memo, user=self.director)
        self.step_letter = SigningStep.objects.create(
            document_kind='letter', order=2, signatory=self.sig_letter, user=self.chief)

        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-SIGN-1', code='RE-2026-9401',
            memo_version=1, letter_version=1)
        self.letter.memo_pdf.save('memo.pdf', ContentFile(b'%PDF-1.4 memo'), save=False)
        self.letter.letter_pdf.save('letter.pdf', ContentFile(b'%PDF-1.4 letter'), save=True)


    def _memo_signed(self):
        """The letter cannot be signed until the memo is — the signed memo is
        its authority. Letter-focused tests call this first."""
        apply_signature(self.letter, self.director, 'memo', _signature_data_uri())

    # -- permission -------------------------------------------------------
    def test_the_named_signatory_may_sign(self):
        allowed, step, reason = can_sign(self.director, self.letter, 'memo')
        self.assertTrue(allowed, reason)
        self.assertEqual(step, self.step_memo)

    def test_someone_else_may_not(self):
        allowed, _, reason = can_sign(self.chief, self.letter, 'memo')
        self.assertFalse(allowed)
        self.assertIn('Ag. Director, Power', reason)

    def test_cannot_sign_an_ungenerated_document(self):
        blank = ReleaseLetter.objects.create(request_code='REQ-SIGN-2', code='RE-2026-9402')
        allowed, _, reason = can_sign(self.director, blank, 'memo')
        self.assertFalse(allowed)
        self.assertIn('not been generated', reason)

    def test_order_is_enforced(self):
        """A second step cannot be signed while the first is outstanding."""
        second = User.objects.create_user('second', password='pw')
        SigningStep.objects.create(
            document_kind='memo', order=3,
            signatory=Signatory.objects.create(name='Second', title='Deputy', user=second),
            user=second)
        allowed, _, reason = can_sign(second, self.letter, 'memo')
        self.assertFalse(allowed)
        self.assertIn('awaiting', reason.lower())

    # -- applying ---------------------------------------------------------
    def test_signing_records_office_and_substantive_designation(self):
        self._memo_signed()
        signature = apply_signature(
            self.letter, self.chief, 'letter', _signature_data_uri(),
            ip_address='10.0.0.1', user_agent='pytest')

        self.assertEqual(signature.signatory_name, 'Kwame Mensah')
        self.assertEqual(signature.signatory_title, 'Ag. Chief Director')
        self.assertEqual(signature.signatory_designation, 'Director, Finance')
        self.assertEqual(signature.signs_for, 'HON. MINISTER')
        self.assertTrue(signature.signature_image)
        self.assertTrue(signature.verification_token)
        self.assertEqual(signature.document_version, 1)
        self.assertEqual(signature.ip_address, '10.0.0.1')

    def test_stamp_shows_both_offices_when_acting(self):
        self._memo_signed()
        signature = apply_signature(self.letter, self.chief, 'letter', _signature_data_uri())
        lines = signature.stamp_lines
        self.assertIn('KWAME MENSAH', lines)
        self.assertIn('Ag. Chief Director', lines)
        self.assertIn('(substantive: Director, Finance)', lines)
        self.assertIn('FOR: HON. MINISTER', lines)
        self.assertTrue(any('RE-2026-9401' in line and 'v1' in line for line in lines))
        self.assertTrue(any(signature.verification_token in line for line in lines))

    def test_signing_locks_the_document(self):
        self._memo_signed()
        apply_signature(self.letter, self.chief, 'letter', _signature_data_uri())
        self.letter.refresh_from_db()
        self.assertTrue(self.letter.letter_locked)
        self.assertTrue(self.letter.signing_complete('letter'))
        # One chain, but locking is per document: the memo locked when it was
        # signed, and the letter locks separately when its own step completes.
        self.assertTrue(self.letter.memo_locked)

    def test_cannot_sign_twice(self):
        self._memo_signed()
        apply_signature(self.letter, self.chief, 'letter', _signature_data_uri())
        with self.assertRaises(SigningError):
            apply_signature(self.letter, self.chief, 'letter', _signature_data_uri())

    def test_tokens_are_unique(self):
        apply_signature(self.letter, self.director, 'memo', _signature_data_uri())
        apply_signature(self.letter, self.chief, 'letter', _signature_data_uri())
        tokens = set(DocumentSignature.objects.values_list('verification_token', flat=True))
        self.assertEqual(len(tokens), 2)

    # -- drawing validation ----------------------------------------------
    def test_rejects_a_non_png_payload(self):
        with self.assertRaises(SigningError):
            decode_signature_png('data:text/html;base64,PHNjcmlwdD4=')

    def test_rejects_an_empty_drawing(self):
        with self.assertRaises(SigningError):
            decode_signature_png('')

    def test_rejects_a_blank_canvas(self):
        """A blank canvas is still a valid PNG — size is what gives it away."""
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGBA', (2, 2), (255, 255, 255, 0)).save(buf, format='PNG')
        tiny = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
        with self.assertRaises(SigningError) as cm:
            decode_signature_png(tiny)
        self.assertIn('blank', str(cm.exception).lower())

    # -- supersede --------------------------------------------------------
    def test_supersede_unlocks_and_keeps_the_record(self):
        self._memo_signed()
        apply_signature(self.letter, self.chief, 'letter', _signature_data_uri())
        supersede_signatures(self.letter, 'letter')

        self.letter.refresh_from_db()
        self.assertFalse(self.letter.letter_locked)
        self.assertEqual(self.letter.signatures_for('letter').count(), 0)
        # The record survives — someone did sign version 1.
        self.assertEqual(DocumentSignature.objects.filter(superseded=True).count(), 1)


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class SignedDocumentLockTests(TestCase):
    """Regenerating a signed document would place a signature over content the
    signatory never saw. The view must refuse."""

    def setUp(self):
        self.officer = User.objects.create_user('officer', password='pw')
        self.officer.groups.add(Group.objects.get_or_create(name='Schedule Officers')[0])
        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-LOCK-1', code='RE-2026-9403', letter_locked=True)

    def test_generation_is_refused_for_a_locked_document(self):
        self.client.force_login(self.officer)
        resp = self.client.post(
            reverse('generate_release_documents', args=[self.letter.pk]), follow=True)
        self.assertContains(resp, 'signed and is locked')

    def test_the_generate_button_is_hidden_when_locked(self):
        """Server-side refusal is not enough — offering a button that always
        fails is how the officer ends up reporting a bug."""
        self.client.force_login(self.officer)
        resp = self.client.get(reverse('release_letter_detail', args=[self.letter.pk]))
        self.assertContains(resp, 'Regenerate (locked)')
        self.assertNotContains(resp, 'Regenerate documents')

    def test_editing_a_locked_document_is_refused(self):
        self.client.force_login(self.officer)
        resp = self.client.post(
            reverse('save_document_html', args=[self.letter.pk, 'letter']),
            {'html': '<p>changed after signing</p>'})
        self.assertEqual(resp.status_code, 409)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.letter_html, '')

    def test_edit_mode_is_denied_on_a_locked_document(self):
        self.client.force_login(self.officer)
        resp = self.client.get(
            reverse('release_letter_preview', args=[self.letter.pk]) + '?edit=1')
        self.assertNotIn('contenteditable="true"', resp.content.decode())

    def test_generation_increments_the_version(self):
        unlocked = ReleaseLetter.objects.create(
            request_code='REQ-LOCK-2', code='RE-2026-9404')
        self.client.force_login(self.officer)
        self.client.post(reverse('generate_release_documents', args=[unlocked.pk]))
        unlocked.refresh_from_db()
        if WEASYPRINT:
            self.assertEqual(unlocked.memo_version, 1)
        else:
            # Without a renderer generation fails; the version must not advance.
            self.assertEqual(unlocked.memo_version, 0)


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class SignatureRenderingTests(TestCase):
    def setUp(self):
        self.chief = User.objects.create_user('chief2', password='pw')
        Profile.objects.update_or_create(
            user=self.chief, defaults={'designation': 'Director, Finance'})
        signatory = Signatory.objects.create(
            name='Kwame Mensah', title='Ag. Chief Director', user=self.chief, active=True)
        SigningStep.objects.create(
            document_kind='letter', order=1, signatory=signatory, user=self.chief)

        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-REND-1', code='RE-2026-9405', letter_version=1)
        self.letter.letter_pdf.save('letter.pdf', ContentFile(b'%PDF-1.4'), save=True)

    def test_signature_and_stamp_render_into_the_document(self):
        from Inventory.services.document_render import render_letter_html
        apply_signature(self.letter, self.chief, 'letter', _signature_data_uri())

        html = render_letter_html(self.letter)
        self.assertIn('class="esign"', html)
        self.assertIn('KWAME MENSAH', html)
        self.assertIn('Ag. Chief Director', html)
        self.assertIn('(substantive: Director, Finance)', html)
        self.assertIn('data:image/png;base64,', html)   # the drawn mark, inlined

    def test_unsigned_document_keeps_the_blank_wet_signature_line(self):
        from Inventory.services.document_render import render_letter_html
        html = render_letter_html(self.letter)
        self.assertIn('class="sign-block"', html)
        self.assertNotIn('class="esign"', html)


class RendererUnavailableSigningTests(TestCase):
    """Regression: a signature must never be recorded if the signed PDF cannot
    be produced.

    The original code treated re-minting as best-effort. When WeasyPrint was
    missing it logged, carried on, completed the chain and locked the document —
    leaving a locked release whose PDF showed no signature, with the lock
    blocking the only button that could have fixed it.
    """

    def setUp(self):
        self.chief = User.objects.create_user('chief3', password='pw')
        signatory = Signatory.objects.create(
            name='Kwame Mensah', title='Ag. Chief Director', user=self.chief, active=True)
        SigningStep.objects.create(
            document_kind='letter', order=1, signatory=signatory, user=self.chief)
        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-RU-1', code='RE-2026-9406', letter_version=1)
        self.letter.letter_pdf.save('letter.pdf', ContentFile(b'%PDF-1.4'), save=True)

    def test_signing_is_refused_up_front_when_the_renderer_is_missing(self):
        from unittest.mock import patch
        with patch('Inventory.services.document_render.weasyprint_status',
                   return_value=(False, 'WeasyPrint is not installed.')):
            allowed, _, reason = can_sign(self.chief, self.letter, 'letter')
        self.assertFalse(allowed)
        self.assertIn('cannot produce PDFs', reason)

    def test_a_failed_remint_rolls_the_signature_back(self):
        from unittest.mock import patch
        with patch('Inventory.services.document_render.weasyprint_status',
                   return_value=(True, 'ok')), \
             patch('Inventory.services.signing.rebuild_signed_pdf',
                   side_effect=RuntimeError('renderer exploded')):
            with self.assertRaises(SigningError):
                apply_signature(self.letter, self.chief, 'letter', _signature_data_uri())

        self.letter.refresh_from_db()
        self.assertEqual(DocumentSignature.objects.count(), 0)
        self.assertFalse(self.letter.letter_locked,
                         "a failed signing must not leave the document locked")
