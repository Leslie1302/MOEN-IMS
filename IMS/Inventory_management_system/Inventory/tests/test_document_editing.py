"""WYSIWYG document editing — sanitiser, stored-HTML precedence, drift detection.

The contract under test:
  * anything an officer types is sanitised before storage (the preview re-renders
    it in a same-origin iframe, so a surviving <script> would actually run);
  * once stored, the hand-edit is what renders — in the preview and in the PDF;
  * the letterhead band and QR stay template-driven and cannot be edited away;
  * reverting restores the generated document;
  * if the release data moves after an edit, `document_drift` says so rather
    than either overwriting the officer's wording or hiding the mismatch.
"""

import importlib.util
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from Inventory.models import ReleaseLetter, MaterialOrder, Unit, Category
from Inventory.services.document_render import (
    render_memo_html, render_letter_html, context_fingerprint,
)
from Inventory.services.html_sanitize import sanitize_document_html

WEASYPRINT = importlib.util.find_spec('weasyprint') is not None


class SanitizerTests(TestCase):
    def test_script_and_contents_are_dropped(self):
        self.assertEqual(
            sanitize_document_html('<script>alert(1)</script><p>ok</p>'), '<p>ok</p>')

    def test_event_handlers_are_stripped(self):
        out = sanitize_document_html('<p onclick="steal()">x</p>')
        self.assertNotIn('onclick', out)
        self.assertIn('x', out)

    def test_javascript_urls_are_stripped(self):
        out = sanitize_document_html('<a href="javascript:alert(1)">z</a>')
        self.assertNotIn('javascript', out)

    def test_inline_images_survive(self):
        """The letterhead and QR are data-URI images — they must not be eaten."""
        out = sanitize_document_html('<img src="data:image/png;base64,AAAA" alt="qr">')
        self.assertIn('data:image/png;base64,AAAA', out)

    def test_data_texthtml_is_rejected(self):
        out = sanitize_document_html('<img src="data:text/html,<script>x</script>">')
        self.assertNotIn('text/html', out)

    def test_document_structure_survives(self):
        src = ('<div class="doc-title">MEMORANDUM</div>'
               '<table class="sched"><tr><td colspan="2">Cable</td></tr></table>'
               '<p style="text-align: justify">Body</p>')
        out = sanitize_document_html(src)
        self.assertIn('MEMORANDUM', out)
        self.assertIn('colspan="2"', out)
        self.assertIn('text-align: justify', out)

    def test_dangerous_css_is_filtered(self):
        out = sanitize_document_html('<p style="text-align:left;background:url(//evil)">x</p>')
        self.assertIn('text-align: left', out)
        self.assertNotIn('evil', out)

    def test_unclosed_tags_are_balanced(self):
        """WeasyPrint is stricter than a browser about malformed markup."""
        out = sanitize_document_html('<div><p>unclosed')
        self.assertEqual(out, '<div><p>unclosed</p></div>')

    def test_empty_input(self):
        self.assertEqual(sanitize_document_html(''), '')
        self.assertEqual(sanitize_document_html(None), '')


class RichFormattingRoundTripTests(TestCase):
    """Everything the Word-style ribbon emits must survive the sanitiser.

    The editor runs with `styleWithCSS` on, so formatting arrives as inline CSS
    on <span>/<p> rather than legacy <font>/<strike> tags. If a declaration is
    missing from the allowlist the officer's formatting silently vanishes on
    save — which looks like the editor is broken. One case per control.
    """

    CONTROLS = {
        'bold':          '<span style="font-weight: bold;">x</span>',
        'italic':        '<span style="font-style: italic;">x</span>',
        'underline':     '<span style="text-decoration: underline;">x</span>',
        'strikethrough': '<span style="text-decoration: line-through;">x</span>',
        'font size':     '<span style="font-size: 14pt;">x</span>',
        'font family':   '<span style="font-family: Georgia, serif;">x</span>',
        'text colour':   '<span style="color: rgb(27, 94, 32);">x</span>',
        'highlight':     '<span style="background-color: rgb(255, 255, 0);">x</span>',
        'justify':       '<p style="text-align: justify;">x</p>',
        'centre':        '<p style="text-align: center;">x</p>',
        'indent':        '<blockquote style="margin-left: 40px;">x</blockquote>',
        'line spacing':  '<p style="line-height: 1.5;">x</p>',
        'page break':    '<div style="page-break-before: always;"></div>',
    }

    def test_every_control_survives(self):
        for label, html in self.CONTROLS.items():
            with self.subTest(control=label):
                prop = html.split('style="')[1].split(':')[0]
                self.assertIn(prop, sanitize_document_html(html),
                              f"{label} formatting was stripped on save")

    def test_superscript_and_subscript_survive(self):
        self.assertIn('<sup>2</sup>', sanitize_document_html('E = mc<sup>2</sup>'))
        self.assertIn('<sub>2</sub>', sanitize_document_html('H<sub>2</sub>O'))

    def test_headings_and_lists_survive(self):
        out = sanitize_document_html('<h2>Heading</h2><ol start="3"><li>a</li></ol>')
        self.assertIn('<h2>Heading</h2>', out)
        self.assertIn('start="3"', out)

    def test_inserted_table_survives(self):
        out = sanitize_document_html(
            '<table style="border-collapse: collapse;">'
            '<tr><th style="background-color: #e8f5e9;">H</th><td>c</td></tr></table>')
        self.assertIn('border-collapse', out)
        self.assertIn('background-color', out)
        self.assertIn('<th', out)

    def test_link_survives_but_javascript_does_not(self):
        self.assertIn('href="https://moen.gov.gh"',
                      sanitize_document_html('<a href="https://moen.gov.gh">x</a>'))
        self.assertNotIn('javascript',
                         sanitize_document_html('<a href="javascript:evil()">x</a>'))

    def test_formatting_does_not_smuggle_script_through(self):
        """A styled span is allowed; a script inside it still is not."""
        out = sanitize_document_html(
            '<span style="font-weight: bold;"><script>evil()</script>x</span>')
        self.assertIn('font-weight', out)
        self.assertNotIn('evil', out)

    def test_css_url_and_expression_are_still_stripped(self):
        out = sanitize_document_html(
            '<p style="page-break-before: always; background: url(//evil)">x</p>')
        self.assertIn('page-break-before', out)
        self.assertNotIn('evil', out)
        self.assertNotIn('expression',
                         sanitize_document_html('<p style="width: expression(evil())">x</p>'))


class StoredHtmlRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.letter = ReleaseLetter.objects.create(
            request_code='REQ-EDIT-1', title='Edit Test', code='RE-2026-9101')

    def test_stored_html_replaces_the_template_body(self):
        self.letter.memo_html = '<p>Bespoke wording approved by the Director.</p>'
        self.letter.save(update_fields=['memo_html'])
        html = render_memo_html(self.letter)
        self.assertIn('Bespoke wording approved by the Director.', html)
        self.assertNotIn('MEMORANDUM', html)   # template body no longer rendered

    def test_use_stored_false_shows_the_generated_original(self):
        self.letter.memo_html = '<p>Bespoke.</p>'
        self.letter.save(update_fields=['memo_html'])
        html = render_memo_html(self.letter, use_stored=False)
        self.assertIn('MEMORANDUM', html)
        self.assertNotIn('Bespoke.', html)

    def test_letterhead_and_qr_survive_an_edit(self):
        """The shell is template-driven — an edit cannot remove the audit QR."""
        self.letter.letter_html = '<p>Only this.</p>'
        self.letter.save(update_fields=['letter_html'])
        html = render_letter_html(self.letter)
        self.assertIn('Only this.', html)
        self.assertIn('Ministry of Energy and Green Transition', html)  # letterhead
        self.assertIn('class="qr"', html)                               # QR block
        self.assertIn('RE-2026-9101', html)

    def test_blank_stored_html_falls_back_to_template(self):
        self.letter.memo_html = '   '
        self.letter.save(update_fields=['memo_html'])
        self.assertIn('MEMORANDUM', render_memo_html(self.letter))

    def test_edit_mode_makes_the_body_editable(self):
        html = render_memo_html(self.letter, edit_mode=True)
        self.assertIn('id="doc-body"', html)
        self.assertIn('contenteditable="true"', html)

    def test_normal_render_is_not_editable(self):
        html = render_memo_html(self.letter)
        self.assertIn('id="doc-body"', html)
        self.assertNotIn('contenteditable="true"', html)
        self.assertNotIn('execCommand', html)   # no editor bridge in the PDF source


class FingerprintDriftTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name='Cables')
        cls.unit = Unit.objects.create(name='set')
        # total_quantity must cover the orders we attach below — the release
        # letter balance guard (release_letter_signals) rejects a MaterialOrder
        # that would overdraw the authorised quantity.
        cls.letter = ReleaseLetter.objects.create(
            request_code='REQ-EDIT-2', title='Drift Test', code='RE-2026-9102',
            total_quantity=Decimal('5000'))

    def test_fingerprint_is_stable(self):
        self.assertEqual(context_fingerprint(self.letter, 'memo'),
                         context_fingerprint(self.letter, 'memo'))

    def test_no_drift_without_an_edit(self):
        self.assertFalse(self.letter.document_drift('memo'))

    def test_no_drift_immediately_after_an_edit(self):
        self.letter.memo_html = '<p>Edited.</p>'
        self.letter.memo_html_fingerprint = context_fingerprint(self.letter, 'memo')
        self.letter.save(update_fields=['memo_html', 'memo_html_fingerprint'])
        self.assertFalse(self.letter.document_drift('memo'))

    def test_drift_detected_when_a_material_is_added(self):
        self.letter.memo_html = '<p>Edited.</p>'
        self.letter.memo_html_fingerprint = context_fingerprint(self.letter, 'memo')
        self.letter.save(update_fields=['memo_html', 'memo_html_fingerprint'])

        MaterialOrder.objects.create(
            name='Stay Equipment', quantity=2000, unit=self.unit,
            category=self.category, community='ANTWIKROM', release_letter=self.letter)

        self.letter.refresh_from_db()
        self.assertTrue(self.letter.document_drift('memo'))

    def test_drift_detected_when_the_note_changes(self):
        self.letter.memo_html = '<p>Edited.</p>'
        self.letter.memo_html_fingerprint = context_fingerprint(self.letter, 'memo')
        self.letter.save(update_fields=['memo_html', 'memo_html_fingerprint'])

        self.letter.memo_notes = 'A new instruction from the Director.'
        self.letter.save(update_fields=['memo_notes'])
        self.assertTrue(self.letter.document_drift('memo'))


class SaveRevertViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.officer = User.objects.create_user('officer', password='pw')
        cls.officer.groups.add(Group.objects.get_or_create(name='Schedule Officers')[0])
        # A logged-in user who may use the app but may NOT generate documents.
        # They need *a* group: UserRoleMiddleware bounces group-less users to
        # the awaiting-authorization page, so a group-less user would never
        # reach the view and would prove nothing about the view's own guard.
        cls.outsider = User.objects.create_user('storekeeper', password='pw')
        cls.outsider.groups.add(Group.objects.get_or_create(name='Store Officers')[0])
        cls.letter = ReleaseLetter.objects.create(
            request_code='REQ-EDIT-3', title='View Test', code='RE-2026-9103')

    def _save_url(self, kind='memo'):
        return reverse('save_document_html', args=[self.letter.pk, kind])

    def test_officer_can_save_an_edit(self):
        self.client.force_login(self.officer)
        resp = self.client.post(self._save_url(), {'html': '<p>Revised body.</p>'})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['ok'])

        self.letter.refresh_from_db()
        self.assertIn('Revised body.', self.letter.memo_html)
        self.assertIsNotNone(self.letter.memo_html_edited_at)
        self.assertEqual(self.letter.memo_html_edited_by, self.officer)
        self.assertTrue(self.letter.memo_html_fingerprint)

    def test_saved_html_is_sanitised(self):
        self.client.force_login(self.officer)
        self.client.post(self._save_url(),
                         {'html': '<p onclick="x()">hi</p><script>bad()</script>'})
        self.letter.refresh_from_db()
        self.assertNotIn('onclick', self.letter.memo_html)
        self.assertNotIn('bad()', self.letter.memo_html)
        self.assertIn('hi', self.letter.memo_html)

    def test_empty_save_is_rejected(self):
        self.client.force_login(self.officer)
        resp = self.client.post(self._save_url(), {'html': '   '})
        self.assertEqual(resp.status_code, 400)
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.memo_html, '')

    def test_unknown_kind_404s(self):
        self.client.force_login(self.officer)
        resp = self.client.post(
            reverse('save_document_html', args=[self.letter.pk, 'invoice']),
            {'html': '<p>x</p>'})
        self.assertEqual(resp.status_code, 404)

    def test_outsider_cannot_save(self):
        self.client.force_login(self.outsider)
        resp = self.client.post(self._save_url(), {'html': '<p>x</p>'})
        self.assertIn(resp.status_code, (302, 403))
        self.letter.refresh_from_db()
        self.assertEqual(self.letter.memo_html, '')

    def test_revert_clears_the_edit(self):
        self.letter.memo_html = '<p>Edited.</p>'
        self.letter.memo_html_fingerprint = 'abc'
        self.letter.save(update_fields=['memo_html', 'memo_html_fingerprint'])

        self.client.force_login(self.officer)
        resp = self.client.post(
            reverse('revert_document_html', args=[self.letter.pk, 'memo']))
        self.assertEqual(resp.status_code, 302)

        self.letter.refresh_from_db()
        self.assertEqual(self.letter.memo_html, '')
        self.assertEqual(self.letter.memo_html_fingerprint, '')
        self.assertIsNone(self.letter.memo_html_edited_at)

    def test_preview_edit_mode_requires_permission(self):
        """?edit=1 must not hand an editor to someone who cannot generate."""
        self.client.force_login(self.outsider)
        resp = self.client.get(
            reverse('release_memo_preview', args=[self.letter.pk]) + '?edit=1')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('contenteditable="true"', resp.content.decode())

    def test_preview_edit_mode_granted_to_officer(self):
        self.client.force_login(self.officer)
        resp = self.client.get(
            reverse('release_memo_preview', args=[self.letter.pk]) + '?edit=1')
        self.assertIn('contenteditable="true"', resp.content.decode())


class EditedPdfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.letter = ReleaseLetter.objects.create(
            request_code='REQ-EDIT-4', title='PDF Edit', code='RE-2026-9104',
            letter_html='<p>Hand-written directive to MMU.</p>')

    def test_edited_letter_still_mints_a_pdf_with_a_working_qr(self):
        if not WEASYPRINT:
            self.skipTest('WeasyPrint not installed in this environment')
        from Inventory.services.pdf_generator import generate_release_letter
        from Inventory.services.scan_validation import decode_qr_outcome, decoder_status

        data = generate_release_letter(self.letter).read()
        self.assertTrue(data.startswith(b'%PDF-'))
        if not decoder_status().get('has_viable_path'):
            self.skipTest('No QR decoder backend available in this environment')
        self.assertEqual(
            decode_qr_outcome(data, 'letter.pdf', self.letter.code), 'match')
