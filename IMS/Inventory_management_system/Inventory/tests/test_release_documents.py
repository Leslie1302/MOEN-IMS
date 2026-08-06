"""Phase 4 — HTML-template release documents.

Covers the three things the rework must not get wrong:
  1. Letterhead resolution — the active row wins, and each of the three modes
     (uploaded image / pre-printed paper / text fallback) renders.
  2. The live preview carries the officer's edits, and it is the *same* template
     the PDF uses, so what is previewed is what prints.
  3. The generated PDF is a real PDF whose QR still decodes back to the release
     code — the scan-upload audit workflow depends on that round trip.

PDF-level tests skip when WeasyPrint (or the QR decoder) is absent, so the suite
stays green in a sandbox without the native Pango/cairo libs.
"""

import importlib.util
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from Inventory.models import ReleaseLetter, Letterhead, Signatory
from Inventory.services.document_render import render_memo_html, render_letter_html

WEASYPRINT = importlib.util.find_spec('weasyprint') is not None


def _png_bytes(size=(600, 160), colour=(27, 94, 32)):
    """A tiny in-memory PNG to stand in for the Ministry letterhead scan."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, colour).save(buf, format='PNG')
    return buf.getvalue()


class LetterheadCurrentTests(TestCase):
    def test_current_returns_active_latest(self):
        Letterhead.objects.create(name='Old', active=False)
        current = Letterhead.objects.create(name='Ministry', active=True)
        self.assertEqual(Letterhead.current(), current)

    def test_current_none_when_no_active(self):
        Letterhead.objects.create(name='Inactive', active=False)
        self.assertIsNone(Letterhead.current())


class PreviewHtmlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.letter = ReleaseLetter.objects.create(
            request_code='REQ-DOC-1', title='Doc Test', code='RE-2026-9001',
            memo_to_override='AG. CHIEF DIRECTOR',
            memo_notes='Kindly expedite this release.',
            letter_notes='Delivery is time-critical.',
        )

    def test_memo_html_carries_edits(self):
        html = render_memo_html(self.letter)
        self.assertIn('MEMORANDUM', html)
        self.assertIn('AG. CHIEF DIRECTOR', html)             # edited TO line
        self.assertIn('Kindly expedite this release.', html)  # edited note
        self.assertIn('RE-2026-9001', html)                   # release code

    def test_letter_html_carries_note(self):
        html = render_letter_html(self.letter)
        self.assertIn('MATERIALS MANAGEMENT UNIT', html)
        self.assertIn('Delivery is time-critical.', html)

    def test_text_letterhead_header_when_no_image(self):
        # No Letterhead row → falls back to the built-in Ministry text header.
        html = render_memo_html(self.letter)
        self.assertIn('Ministry of Energy and Green Transition', html)

    def test_notes_are_html_escaped(self):
        """Officer free-text must not be able to inject markup into the document."""
        self.letter.memo_notes = 'Release <b>now</b> & confirm'
        self.letter.save(update_fields=['memo_notes'])
        html = render_memo_html(self.letter)
        self.assertIn('&lt;b&gt;now&lt;/b&gt;', html)
        self.assertNotIn('Release <b>now</b>', html)

    def test_footer_is_not_html_escaped_inside_css(self):
        """The @page footer is a CSS string — entities there would print literally."""
        html = render_memo_html(self.letter)
        self.assertIn('@bottom-center', html)
        css = html.split('@bottom-center', 1)[1].split('}', 1)[0]
        self.assertNotIn('&amp;', css)
        self.assertNotIn('&#x27;', css)
        self.assertIn('RE-2026-9001', css)


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class LetterheadRenderModeTests(TestCase):
    """The letterhead belongs to the RELEASE LETTER. The memo is a plain sheet.

    Insets are POINTS since the drag-to-calibrate editor landed — the unit
    WeasyPrint's @page rule and the PyMuPDF stamping both work in.
    """

    @classmethod
    def setUpTestData(cls):
        cls.letter = ReleaseLetter.objects.create(
            request_code='REQ-DOC-3', title='LH Test', code='RE-2026-9003')

    def _letterhead(self, **kw):
        lh = Letterhead.objects.create(name='Ministry', active=True, **kw)
        lh.file.save('letterhead.png', SimpleUploadedFile(
            'letterhead.png', _png_bytes(), content_type='image/png'), save=True)
        return lh

    # -- release letter ---------------------------------------------------
    def test_letter_page_one_uses_the_calibrated_top_inset(self):
        """Page 1 sits on letterhead stock, so its top margin clears the artwork."""
        Letterhead.objects.create(name='Ministry', active=True, inset_top=184,
                                  inset_right=62, inset_bottom=106, inset_left=73,
                                  cont_inset_top=62)
        html = render_letter_html(self.letter)
        self.assertIn('@page :first { margin-top: 184pt; }', html)

    def test_letter_continuation_pages_use_a_normal_top_margin(self):
        """Pages 2+ print on plain paper — no header band to clear. Left, right
        and bottom stay calibrated so the text block lines up across pages."""
        Letterhead.objects.create(name='Ministry', active=True, inset_top=184,
                                  inset_right=62, inset_bottom=106, inset_left=73,
                                  cont_inset_top=62)
        html = render_letter_html(self.letter)
        self.assertIn('margin: 62pt 62pt 106pt 73pt', html)   # base @page rule

    def test_letter_image_backs_the_simulated_page_on_screen(self):
        self._letterhead()
        html = render_letter_html(self.letter)
        self.assertIn('class="page"', html)
        self.assertIn("background-image: url('data:image/png;base64,", html)
        self.assertNotIn('class="letterhead center"', html)   # no text fallback

    def test_letter_pdf_path_omits_the_inline_raster(self):
        """For the PDF the letterhead is stamped afterwards, not inlined."""
        from Inventory.services.document_render import render_document_html
        self._letterhead()
        html = render_document_html(self.letter, 'letter', for_pdf=True)
        self.assertNotIn('background-image', html)   # letterhead not inlined
        self.assertNotIn('class="page"', html)       # no screen page simulation
        self.assertIn('margin: 184pt', html)         # @page still does the insetting
        self.assertIn('class="qr"', html)            # the QR stays inline, as it must

    def test_letter_pre_printed_draws_no_header(self):
        Letterhead.objects.create(name='Pre-printed', active=True, pre_printed=True,
                                  inset_top=200)
        html = render_letter_html(self.letter)
        self.assertIn('margin: 200pt', html)
        self.assertNotIn('class="letterhead', html)

    def test_letter_missing_file_degrades_to_text_header(self):
        """A storage hiccup must not block document generation."""
        lh = Letterhead.objects.create(name='Ministry', active=True)
        Letterhead.objects.filter(pk=lh.pk).update(file='letterhead/gone.png')
        html = render_letter_html(self.letter)
        self.assertIn('Ministry of Energy and Green Transition', html)

    # -- approval memo: plain sheet ---------------------------------------
    def test_memo_never_carries_the_letterhead(self):
        self._letterhead()
        html = render_memo_html(self.letter)
        self.assertNotIn('background-image', html)          # no letterhead artwork
        self.assertNotIn('class="letterhead', html)         # no org text header
        self.assertIn('MEMORANDUM', html)

    def test_memo_uses_its_own_margins(self):
        self._letterhead(inset_top=184, inset_bottom=106, inset_left=73, inset_right=62,
                         memo_inset_top=70, memo_inset_bottom=55,
                         memo_inset_left=60, memo_inset_right=50)
        html = render_memo_html(self.letter)
        self.assertIn('margin: 70pt 50pt 55pt 60pt', html)
        self.assertNotIn('margin: 184pt', html)   # letterhead insets must not leak in

    def test_memo_defaults_when_no_letterhead_row_exists(self):
        html = render_memo_html(self.letter)
        self.assertIn('margin: 62pt 62pt 62pt 62pt', html)

    def test_memorandum_title_is_underlined(self):
        html = render_memo_html(self.letter)
        title_css = html.split('.doc-title {', 1)[1].split('}', 1)[0]
        self.assertIn('text-decoration: underline', title_css)
        self.assertIn('font-weight: bold', title_css)


class TemplateCommentTests(TestCase):
    """Django's {# #} is single-line only — a multi-line one renders as visible
    text in the finished document. Regression guard, because it is invisible in
    review and glaring on the page."""

    def test_no_raw_template_comments_in_rendered_documents(self):
        letter = ReleaseLetter.objects.create(
            request_code='REQ-DOC-6', title='Comment Test', code='RE-2026-9006')
        for html in (render_memo_html(letter), render_letter_html(letter)):
            self.assertNotIn('{#', html)
            self.assertNotIn('#}', html)
            self.assertNotIn('{%', html)


class SignatoryOverrideTests(TestCase):
    def test_letter_signatory_override_wins(self):
        sig = Signatory.objects.create(
            name='Kwame Mensah', title='Ag. Chief Director', active=True)
        letter = ReleaseLetter.objects.create(
            request_code='REQ-DOC-4', code='RE-2026-9004',
            letter_signatory_override=sig)
        html = render_letter_html(letter)
        self.assertIn('KWAME MENSAH', html)


class RendererAvailabilityTests(TestCase):
    """A missing renderer must fail loudly, never silently keep the old PDFs."""

    def test_status_matches_the_import(self):
        from Inventory.services.document_render import weasyprint_status
        ok, detail = weasyprint_status()
        self.assertEqual(ok, WEASYPRINT)
        if not ok:
            self.assertIn('weasyprint', detail.lower())

    def test_render_raises_a_typed_error_when_unavailable(self):
        if WEASYPRINT:
            self.skipTest('WeasyPrint is installed here — nothing to assert')
        from Inventory.services.document_render import (
            render_document_pdf, RendererUnavailable)
        letter = ReleaseLetter.objects.create(
            request_code='REQ-DOC-5', code='RE-2026-9005')
        with self.assertRaises(RendererUnavailable) as cm:
            render_document_pdf(letter, 'memo')
        # The message has to tell the officer the old files are still in place.
        self.assertIn('NOT updated', str(cm.exception))


class PdfRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.letter = ReleaseLetter.objects.create(
            request_code='REQ-DOC-2', title='PDF Test', code='RE-2026-9002')

    def _render(self, fn):
        if not WEASYPRINT:
            self.skipTest('WeasyPrint not installed in this environment')
        cf = fn(self.letter)
        data = cf.read()
        self.assertTrue(data.startswith(b'%PDF-'))
        self.assertGreater(len(data), 1000)
        return data

    def test_memo_pdf_renders(self):
        from Inventory.services.pdf_generator import generate_release_memo
        self._render(generate_release_memo)

    def test_letter_pdf_renders(self):
        from Inventory.services.pdf_generator import generate_release_letter
        self._render(generate_release_letter)

    def test_letter_pdf_qr_decodes_to_release_code(self):
        """The round trip the scan-upload workflow depends on."""
        from Inventory.services.pdf_generator import generate_release_letter
        from Inventory.services.scan_validation import decode_qr_outcome, decoder_status

        data = self._render(generate_release_letter)
        if not decoder_status().get('has_viable_path'):
            self.skipTest('No QR decoder backend available in this environment')
        self.assertEqual(
            decode_qr_outcome(data, 'letter.pdf', self.letter.code), 'match')

    def test_pdf_renders_with_a_letterhead_and_insets(self):
        Letterhead.objects.create(name='Ministry', active=True, inset_top=55)
        from Inventory.services.pdf_generator import generate_release_memo
        self._render(generate_release_memo)
