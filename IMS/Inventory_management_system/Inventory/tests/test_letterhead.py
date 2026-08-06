"""Letterhead: PDF/image upload, preview rasterisation, point insets, stamping.

The contract:
  * a PDF letterhead is accepted and page 1 is rasterised into `preview_image`
    so the drag-to-calibrate editor has something to show;
  * insets are points, validated so opposing guides can never cross;
  * the letterhead is stamped underneath EVERY page of the generated PDF (an
    inline <img> only ever reached page 1) and a PDF letterhead stays vector;
  * anything missing or corrupt degrades to a plain document — a broken
    letterhead must never block a release.
"""

import importlib.util
import io

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from Inventory.models import Letterhead, ReleaseLetter
from Inventory.models.letterhead import A4_HEIGHT_PT, A4_WIDTH_PT

PYMUPDF = importlib.util.find_spec('fitz') is not None
WEASYPRINT = importlib.util.find_spec('weasyprint') is not None


def _png_bytes(size=(600, 160), colour=(27, 94, 32)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, colour).save(buf, format='PNG')
    return buf.getvalue()


def _pdf_bytes(text='MINISTRY LETTERHEAD'):
    """A one-page A4 PDF standing in for a scanned letterhead."""
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    page.insert_text((72, 96), text, fontsize=24)
    data = doc.tobytes()
    doc.close()
    return data


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class LetterheadUploadTests(TestCase):
    def test_image_upload_uses_itself_as_the_preview(self):
        lh = Letterhead.objects.create(name='Ministry', active=True)
        lh.file.save('lh.png', SimpleUploadedFile('lh.png', _png_bytes(),
                                                  content_type='image/png'), save=True)
        lh.refresh_from_db()
        self.assertFalse(lh.is_pdf)
        self.assertTrue(lh.preview_image)

    def test_pdf_upload_is_rasterised_to_a_preview(self):
        if not PYMUPDF:
            self.skipTest('PyMuPDF not installed in this environment')
        lh = Letterhead.objects.create(name='Ministry', active=True)
        lh.file.save('lh.pdf', SimpleUploadedFile('lh.pdf', _pdf_bytes(),
                                                  content_type='application/pdf'), save=True)
        lh.refresh_from_db()
        self.assertTrue(lh.is_pdf)
        self.assertTrue(lh.preview_image, "PDF page 1 should have been rasterised")
        self.assertTrue(lh.preview_image.name.endswith('.png'))

    def test_corrupt_pdf_does_not_raise(self):
        """A bad upload loses its preview, it does not break the save."""
        lh = Letterhead.objects.create(name='Ministry', active=True)
        lh.file.save('bad.pdf', SimpleUploadedFile('bad.pdf', b'not a pdf at all',
                                                   content_type='application/pdf'), save=True)
        lh.refresh_from_db()
        self.assertTrue(lh.file)
        self.assertFalse(lh.preview_image)

    def test_insets_default_to_points(self):
        lh = Letterhead.objects.create(name='Ministry', active=True)
        self.assertEqual(lh.insets_pt,
                         {'top': 184, 'right': 62, 'bottom': 106, 'left': 73})

    def test_memo_margins_are_independent_of_the_letterhead_insets(self):
        lh = Letterhead.objects.create(name='Ministry', active=True)
        self.assertEqual(lh.memo_insets_pt,
                         {'top': 62, 'right': 62, 'bottom': 62, 'left': 62})


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class LetterheadSettingsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user('lhmanager', password='pw')
        cls.manager.groups.add(Group.objects.get_or_create(name='Management')[0])
        cls.other = User.objects.create_user('lhother', password='pw')
        cls.other.groups.add(Group.objects.get_or_create(name='Store Officers')[0])

    def test_page_loads_for_a_manager(self):
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('letterhead_settings'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Printable area')

    def test_page_denied_to_others(self):
        self.client.force_login(self.other)
        resp = self.client.get(reverse('letterhead_settings'))
        self.assertIn(resp.status_code, (302, 403))

    def test_upload_creates_the_active_letterhead(self):
        self.client.force_login(self.manager)
        resp = self.client.post(reverse('letterhead_settings'), {
            'action': 'upload',
            'file': SimpleUploadedFile('lh.png', _png_bytes(), content_type='image/png'),
        })
        self.assertEqual(resp.status_code, 302)
        lh = Letterhead.current()
        self.assertIsNotNone(lh)
        self.assertTrue(lh.file)

    def test_unsupported_extension_is_rejected(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('letterhead_settings'), {
            'action': 'upload',
            'file': SimpleUploadedFile('lh.svg', b'<svg/>', content_type='image/svg+xml'),
        })
        self.assertIsNone(Letterhead.current())

    def test_saving_both_inset_groups(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('letterhead_settings'), {
            'action': 'insets',
            'inset_top': '200', 'inset_bottom': '90', 'inset_left': '70', 'inset_right': '60',
            'memo_inset_top': '72', 'memo_inset_bottom': '58',
            'memo_inset_left': '65', 'memo_inset_right': '55',
        })
        lh = Letterhead.current()
        self.assertEqual(lh.insets_pt, {'top': 200, 'right': 60, 'bottom': 90, 'left': 70})
        self.assertEqual(lh.memo_insets_pt, {'top': 72, 'right': 55, 'bottom': 58, 'left': 65})

    def test_bad_memo_margins_are_rejected_too(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('letterhead_settings'), {
            'action': 'insets',
            'inset_top': '184', 'inset_bottom': '106', 'inset_left': '73', 'inset_right': '62',
            'memo_inset_top': str(A4_HEIGHT_PT), 'memo_inset_bottom': str(A4_HEIGHT_PT),
            'memo_inset_left': '62', 'memo_inset_right': '62',
        })
        self.assertIsNone(Letterhead.current())

    def test_overlapping_insets_are_rejected(self):
        """Crossed guides mean a negative printable area — WeasyPrint would
        silently emit a blank page, so the view refuses instead."""
        self.client.force_login(self.manager)
        self.client.post(reverse('letterhead_settings'), {
            'action': 'insets',
            'inset_top': str(A4_HEIGHT_PT), 'inset_bottom': str(A4_HEIGHT_PT),
            'inset_left': '70', 'inset_right': '60',
        })
        self.assertIsNone(Letterhead.current())

    def test_negative_insets_are_rejected(self):
        self.client.force_login(self.manager)
        self.client.post(reverse('letterhead_settings'), {
            'action': 'insets', 'inset_top': '-5', 'inset_bottom': '90',
            'inset_left': '70', 'inset_right': '60',
        })
        self.assertIsNone(Letterhead.current())


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class LetterheadStampingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.letter = ReleaseLetter.objects.create(
            request_code='REQ-LH-1', title='Stamp Test', code='RE-2026-9201')

    def _blank_pdf(self, pages=2):
        import fitz
        doc = fitz.open()
        for _ in range(pages):
            doc.new_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
        data = doc.tobytes()
        doc.close()
        return data

    def test_no_letterhead_returns_the_pdf_untouched(self):
        if not PYMUPDF:
            self.skipTest('PyMuPDF not installed in this environment')
        from Inventory.services.document_render import _stamp_letterhead
        original = self._blank_pdf(1)
        self.assertEqual(_stamp_letterhead(original), original)

    def test_pre_printed_returns_the_pdf_untouched(self):
        if not PYMUPDF:
            self.skipTest('PyMuPDF not installed in this environment')
        from Inventory.services.document_render import _stamp_letterhead
        Letterhead.objects.create(name='Pre', active=True, pre_printed=True)
        original = self._blank_pdf(1)
        self.assertEqual(_stamp_letterhead(original), original)

    def test_pdf_letterhead_is_stamped_on_page_one_only(self):
        """Page 1 is printed on letterhead stock; continuation pages are plain
        paper. Stamping page 2 would produce a PDF that never matches the
        wet-signed original."""
        if not PYMUPDF:
            self.skipTest('PyMuPDF not installed in this environment')
        import fitz
        from Inventory.services.document_render import _stamp_letterhead

        lh = Letterhead.objects.create(name='Ministry', active=True)
        lh.file.save('lh.pdf', SimpleUploadedFile(
            'lh.pdf', _pdf_bytes('MINISTRY LETTERHEAD'),
            content_type='application/pdf'), save=True)

        stamped = _stamp_letterhead(self._blank_pdf(pages=3))
        doc = fitz.open(stream=stamped, filetype='pdf')
        try:
            self.assertEqual(doc.page_count, 3)
            self.assertIn('MINISTRY LETTERHEAD', doc.load_page(0).get_text())
            self.assertNotIn('MINISTRY LETTERHEAD', doc.load_page(1).get_text())
            self.assertNotIn('MINISTRY LETTERHEAD', doc.load_page(2).get_text())
        finally:
            doc.close()

    def test_single_page_document_is_still_stamped(self):
        if not PYMUPDF:
            self.skipTest('PyMuPDF not installed in this environment')
        import fitz
        from Inventory.services.document_render import _stamp_letterhead

        lh = Letterhead.objects.create(name='Ministry', active=True)
        lh.file.save('lh.pdf', SimpleUploadedFile(
            'lh.pdf', _pdf_bytes('MINISTRY LETTERHEAD'),
            content_type='application/pdf'), save=True)

        doc = fitz.open(stream=_stamp_letterhead(self._blank_pdf(1)), filetype='pdf')
        try:
            self.assertIn('MINISTRY LETTERHEAD', doc.load_page(0).get_text())
        finally:
            doc.close()

    def test_image_letterhead_is_stamped_on_page_one_only(self):
        if not PYMUPDF:
            self.skipTest('PyMuPDF not installed in this environment')
        import fitz
        from Inventory.services.document_render import _stamp_letterhead

        lh = Letterhead.objects.create(name='Ministry', active=True)
        lh.file.save('lh.png', SimpleUploadedFile('lh.png', _png_bytes(),
                                                  content_type='image/png'), save=True)
        stamped = _stamp_letterhead(self._blank_pdf(2))
        doc = fitz.open(stream=stamped, filetype='pdf')
        try:
            self.assertTrue(doc.load_page(0).get_images(), "expected an image on page 1")
            self.assertFalse(doc.load_page(1).get_images(), "page 2 is plain paper")
        finally:
            doc.close()

    def test_memo_is_never_stamped(self):
        """The memo prints on a plain sheet — the letterhead must not reach it."""
        if not PYMUPDF:
            self.skipTest('PyMuPDF not installed in this environment')
        from Inventory.services.document_render import _stamp_letterhead
        lh = Letterhead.objects.create(name='Ministry', active=True)
        lh.file.save('lh.pdf', SimpleUploadedFile('lh.pdf', _pdf_bytes(),
                                                  content_type='application/pdf'), save=True)
        original = self._blank_pdf(1)
        self.assertEqual(_stamp_letterhead(original, 'memo'), original)
        self.assertNotEqual(_stamp_letterhead(original, 'letter'), original)

    def test_unreadable_letterhead_returns_the_original(self):
        if not PYMUPDF:
            self.skipTest('PyMuPDF not installed in this environment')
        from Inventory.services.document_render import _stamp_letterhead
        lh = Letterhead.objects.create(name='Ministry', active=True)
        Letterhead.objects.filter(pk=lh.pk).update(file='letterhead/missing.pdf')
        original = self._blank_pdf(1)
        self.assertEqual(_stamp_letterhead(original), original)

    def test_full_generation_with_a_pdf_letterhead_keeps_the_qr(self):
        if not (PYMUPDF and WEASYPRINT):
            self.skipTest('WeasyPrint and PyMuPDF both required')
        from Inventory.services.pdf_generator import generate_release_letter
        from Inventory.services.scan_validation import decode_qr_outcome, decoder_status

        lh = Letterhead.objects.create(name='Ministry', active=True)
        lh.file.save('lh.pdf', SimpleUploadedFile('lh.pdf', _pdf_bytes(),
                                                  content_type='application/pdf'), save=True)

        data = generate_release_letter(self.letter).read()
        self.assertTrue(data.startswith(b'%PDF-'))
        if not decoder_status().get('has_viable_path'):
            self.skipTest('No QR decoder backend available in this environment')
        # Stamping must not obscure the QR — the scan-matching audit needs it.
        self.assertEqual(
            decode_qr_outcome(data, 'letter.pdf', self.letter.code), 'match')
