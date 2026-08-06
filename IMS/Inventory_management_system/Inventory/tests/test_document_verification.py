"""QR payload + the public verify page.

The QR used to encode the bare release code, so scanning a printed document with
a phone produced the string `RE-2026-0001` and an offer to web-search it. It now
encodes a link to the verify page, so anyone holding a physical copy can check
the document's status without an account.

The risk in that change is backwards compatibility: documents already printed,
signed and filed carry the OLD payload and must keep validating forever. Hence
the matcher tests below — they matter more than the new behaviour, because
breaking them would mean rejecting genuine signed scans.
"""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from Inventory.models import (
    DocumentSignature, Profile, ReleaseLetter, Signatory, SigningStep,
)
from Inventory.services.document_render import qr_payload
from Inventory.services.scan_validation import payload_matches_code


class QrPayloadTests(TestCase):
    @override_settings(PUBLIC_BASE_URL='https://moen-ims.org')
    def test_payload_is_a_verify_url_when_the_host_is_configured(self):
        self.assertEqual(qr_payload('RE-2026-0001'),
                         'https://moen-ims.org/verify/RE-2026-0001/')

    @override_settings(PUBLIC_BASE_URL='https://moen-ims.org')
    def test_payload_carries_the_unguessable_token(self):
        """Without it, scanning proves nothing a forger couldn't fake by
        enumerating codes."""
        self.assertEqual(qr_payload('RE-2026-0001', 'abc123XYZ'),
                         'https://moen-ims.org/verify/RE-2026-0001/?t=abc123XYZ')

    @override_settings(PUBLIC_BASE_URL='https://moen-ims.org/')
    def test_trailing_slash_on_the_setting_does_not_double_up(self):
        self.assertNotIn('//verify', qr_payload('RE-2026-0001'))

    @override_settings(PUBLIC_BASE_URL='')
    def test_falls_back_to_the_bare_code_when_unconfigured(self):
        """A QR pointing at localhost on a printed Ministry letter would be
        worse than no link — and the PDF is permanent."""
        self.assertEqual(qr_payload('RE-2026-0001'), 'RE-2026-0001')


class ScanMatcherCompatibilityTests(TestCase):
    """Both payload generations must validate against the same release."""

    CODE = 'RE-2026-0001'

    def test_legacy_bare_code_still_matches(self):
        self.assertTrue(payload_matches_code('RE-2026-0001', self.CODE))

    def test_new_verify_url_matches(self):
        self.assertTrue(payload_matches_code(
            'https://moen-ims.org/verify/RE-2026-0001/', self.CODE))

    def test_url_without_trailing_slash_matches(self):
        self.assertTrue(payload_matches_code(
            'https://moen-ims.org/verify/RE-2026-0001', self.CODE))

    def test_query_string_form_matches(self):
        self.assertTrue(payload_matches_code(
            'https://moen-ims.org/v?code=RE-2026-0001', self.CODE))

    def test_case_and_whitespace_are_tolerated(self):
        self.assertTrue(payload_matches_code('  re-2026-0001 ', self.CODE))

    # -- the dangerous cases ---------------------------------------------
    def test_a_longer_code_must_not_match(self):
        """RE-2026-0001 matching RE-2026-00012 would let one release validate
        another's signed scan. Anchored matching, not substring."""
        self.assertFalse(payload_matches_code('RE-2026-00012', self.CODE))
        self.assertFalse(payload_matches_code(
            'https://moen-ims.org/verify/RE-2026-00012/', self.CODE))

    def test_a_prefixed_code_must_not_match(self):
        self.assertFalse(payload_matches_code('XRE-2026-0001', self.CODE))

    def test_a_different_release_does_not_match(self):
        self.assertFalse(payload_matches_code('RE-2026-0002', self.CODE))

    def test_empty_inputs_do_not_match(self):
        self.assertFalse(payload_matches_code('', self.CODE))
        self.assertFalse(payload_matches_code(self.CODE, ''))


class VerifyTierTests(TestCase):
    """Codes are enumerable; tokens are not. The page must not conflate them.

    A forger who walks RE-2026-0001..9999 finds real approved codes. If a bare
    code lookup answered "genuine document", printing that code on a fake letter
    would pass the very check meant to catch it.
    """

    def setUp(self):
        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-TIER-1', code='RE-2026-0100',
            workflow_status='approved', letter_version=3)
        self.token = self.letter.ensure_verify_token()
        self.letter.refresh_from_db()

    def _url(self, ref='RE-2026-0100'):
        return reverse('verify_document', args=[ref])

    def test_a_token_is_minted_and_is_not_guessable(self):
        self.assertTrue(self.token)
        self.assertGreaterEqual(len(self.token), 12)
        self.assertNotIn(self.letter.code, self.token)

    def test_the_token_never_rotates(self):
        """Rotating would invalidate the QR on every copy already printed."""
        self.assertEqual(self.letter.ensure_verify_token(), self.token)

    # -- code only ---------------------------------------------------------
    def test_code_only_does_not_claim_the_document_is_genuine(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'not verified')
        self.assertNotContains(resp, 'Verified genuine document')

    def test_code_only_says_plainly_what_it_has_not_done(self):
        resp = self.client.get(self._url())
        self.assertContains(resp, 'reference lookup, not a document check')
        self.assertContains(resp, 'can be guessed')

    def test_code_only_withholds_the_signatories(self):
        Signatory.objects.create(name='Kwame Mensah', title='Ag. Chief Director')
        DocumentSignature.objects.create(
            release_letter=self.letter, document_kind='letter',
            signatory_name='Kwame Mensah', signatory_title='Ag. Chief Director',
            document_version=3)
        resp = self.client.get(self._url())
        self.assertNotContains(resp, 'Kwame Mensah')

    # -- with the token ----------------------------------------------------
    def test_a_valid_token_verifies_the_document(self):
        resp = self.client.get(f"{self._url()}?t={self.token}")
        self.assertContains(resp, 'Verified genuine document')
        self.assertContains(resp, 'v3')

    def test_a_wrong_token_falls_back_rather_than_erroring(self):
        """A mistyped token should degrade to the code-only answer, not 500 or
        wrongly claim verification."""
        resp = self.client.get(f"{self._url()}?t=totally-wrong-token")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'not verified')
        self.assertNotContains(resp, 'Verified genuine document')

    def test_another_documents_token_does_not_verify_this_one(self):
        other = ReleaseLetter.objects.create(
            request_code='REQ-TIER-2', code='RE-2026-0101')
        resp = self.client.get(f"{self._url()}?t={other.ensure_verify_token()}")
        self.assertNotContains(resp, 'Verified genuine document')

    def test_an_empty_token_does_not_verify(self):
        """Guards against a blank verify_token matching a blank query value."""
        ReleaseLetter.objects.filter(pk=self.letter.pk).update(verify_token='')
        resp = self.client.get(f"{self._url()}?t=")
        self.assertNotContains(resp, 'Verified genuine document')


class VerifyPageTests(TestCase):
    def setUp(self):
        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-VER-1', code='RE-2026-0001',
            workflow_status='approved', letter_version=2)
        self.token = self.letter.ensure_verify_token()

    def _url(self, ref):
        return reverse('verify_document', args=[ref])

    def test_a_known_code_resolves_without_login(self):
        resp = self.client.get(f"{self._url('RE-2026-0001')}?t={self.token}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Verified genuine document')
        self.assertContains(resp, 'RE-2026-0001')

    def test_lookup_is_case_insensitive(self):
        self.assertEqual(self.client.get(self._url('re-2026-0001')).status_code, 200)

    def test_an_unknown_code_says_so_plainly(self):
        """404-ing into ambiguity is the wrong answer when the question is
        'is this document genuine?'"""
        resp = self.client.get(self._url('RE-2026-9999'))
        self.assertEqual(resp.status_code, 404)
        self.assertContains(resp, 'No document found', status_code=404)
        self.assertContains(resp, 'not genuine', status_code=404)

    def test_a_voided_document_is_called_out(self):
        self.letter.workflow_status = 'voided'
        self.letter.save(update_fields=['workflow_status'])
        resp = self.client.get(self._url('RE-2026-0001'))
        self.assertContains(resp, 'has been voided')
        self.assertContains(resp, 'Do not act on it')

    def test_the_page_does_not_leak_document_contents(self):
        """Readable by anyone who can point a camera at a QR — so it must not
        disclose materials, quantities or destinations."""
        self.letter.title = 'Release of 2000 sets Stay Equipment at ANTWIKROM'
        self.letter.save(update_fields=['title'])
        body = self.client.get(self._url('RE-2026-0001')).content.decode()
        self.assertNotIn('ANTWIKROM', body)
        self.assertNotIn('Stay Equipment', body)
        self.assertNotIn('2000', body)

    def test_an_over_long_reference_is_rejected(self):
        self.assertEqual(self.client.get(self._url('x' * 100)).status_code, 404)


class VerifySignatureTokenTests(TestCase):
    def setUp(self):
        self.chief = User.objects.create_user('chief', password='pw')
        Profile.objects.update_or_create(
            user=self.chief, defaults={'designation': 'Director, Finance'})
        signatory = Signatory.objects.create(
            name='Kwame Mensah', title='Ag. Chief Director', user=self.chief, active=True)
        step = SigningStep.objects.create(
            document_kind='letter', order=1, signatory=signatory, user=self.chief)
        self.letter = ReleaseLetter.objects.create(
            request_code='REQ-VER-2', code='RE-2026-0002', workflow_status='approved')
        self.signature = DocumentSignature.objects.create(
            release_letter=self.letter, document_kind='letter', step=step,
            signed_by=self.chief, signatory_name='Kwame Mensah',
            signatory_title='Ag. Chief Director',
            signatory_designation='Director, Finance', document_version=1)

    def test_a_signature_token_resolves_to_its_document(self):
        resp = self.client.get(
            reverse('verify_document', args=[self.signature.verification_token]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'RE-2026-0002')
        self.assertContains(resp, 'Kwame Mensah')

    def _verified_url(self):
        """Signatory detail is only disclosed once possession is proved."""
        return (reverse('verify_document', args=['RE-2026-0002'])
                + f"?t={self.letter.ensure_verify_token()}")

    def test_the_stamp_shows_office_and_substantive_post(self):
        """The whole point of the designation split: an acting officer's record
        must say who signed and under what authority."""
        resp = self.client.get(self._verified_url())
        self.assertContains(resp, 'Ag. Chief Director')
        self.assertContains(resp, 'Director, Finance')

    def test_the_signature_image_is_never_served(self):
        """It is a picture of a real signature; this page is public — so it must
        not appear even at the verified tier."""
        body = self.client.get(self._verified_url()).content.decode()
        self.assertNotIn('signature_image', body)
        self.assertNotIn('data:image/png', body)

    def test_a_superseded_signature_is_not_presented_as_current(self):
        self.signature.superseded = True
        self.signature.save(update_fields=['superseded'])
        resp = self.client.get(self._verified_url())
        self.assertContains(resp, 'Superseded version exists')
