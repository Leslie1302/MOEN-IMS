"""Uploaded scans are stored under a deterministic, storage-safe name derived
from the release code — arbitrary scanner/phone filenames otherwise cause a
prod-only 'Bad Request (400)' on the Azure Blob backend."""

from django.test import TestCase

from Inventory.services.scan_validation import safe_scan_filename


class SafeScanFilenameTests(TestCase):
    def test_derives_name_from_code_and_keeps_extension(self):
        self.assertEqual(safe_scan_filename('Scan 2026-08-12 10:30:45.pdf', 'RE-2026-0002'),
                         'RE-2026-0002.pdf')
        self.assertEqual(safe_scan_filename('photo.JPEG', 'RE-2026-0002'),
                         'RE-2026-0002.jpeg')

    def test_strips_path_and_unsafe_characters(self):
        self.assertEqual(safe_scan_filename('../../etc/passwd', 'RE-2026-0002'),
                         'RE-2026-0002.pdf')          # no traversal, safe default ext
        self.assertNotIn('/', safe_scan_filename('a/b/c.png', 'RE 2026 0002'))

    def test_defaults_when_missing(self):
        self.assertEqual(safe_scan_filename('noext', ''), 'scan.pdf')

    def test_unknown_extension_defaults_to_pdf(self):
        self.assertTrue(safe_scan_filename('malware.exe', 'RE-1').endswith('.pdf'))
