"""Historical requisitions: captured for the record, inert everywhere else.

The single most important property is **isolation**. `order_flow` decrements
`InventoryItem.quantity` when an order is processed, so a historical requisition
routed through the live models would deduct today's stock for materials that
physically left years ago — silently, and very hard to unpick. It would also
consume release codes from the sequence the Registry is adopting.

That is why this is a separate model rather than a flag, and why the first tests
below assert the isolation rather than the features.
"""

import io
from datetime import date

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from Inventory.models import (
    ArchivedRequisition, Category, InventoryItem, ReleaseCodeSequence, Unit, Warehouse,
)
from Inventory.services.archive_import import import_archive_rows, parse_document_date


def _row(**overrides):
    row = {
        'reference': 'MOEN/REQ/2023/0142',
        'description': 'Release of 2,000 sets stay equipment',
        'document_date': '2023-06-14',
        'request_type': 'Release',
        'community': 'ANTWIKROM',
        'region': 'Eastern',
    }
    row.update(overrides)
    return row


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class ArchiveIsolationTests(TestCase):
    """The properties that make backfilling safe at all."""

    def setUp(self):
        self.category = Category.objects.create(name='Poles')
        self.unit = Unit.objects.create(name='set')
        self.warehouse = Warehouse.objects.create(name='Tema Central')
        self.item = InventoryItem.objects.create(
            name='Stay Equipment C/W Accessories', quantity=5000, code='STY001',
            category=self.category, unit=self.unit, warehouse=self.warehouse)

    def test_archiving_never_moves_stock(self):
        """The materials left years ago; deducting them again would corrupt
        current inventory."""
        before = self.item.quantity
        import_archive_rows([_row()], user=None)
        self.item.refresh_from_db()
        self.assertEqual(self.item.quantity, before)

    def test_archiving_never_consumes_a_release_code(self):
        """That sequence is becoming the Registry's — burning numbers on old
        paper would corrupt it."""
        before = ReleaseCodeSequence.objects.count()
        import_archive_rows([_row()], user=None)
        self.assertEqual(ReleaseCodeSequence.objects.count(), before)
        self.assertFalse(ReleaseCodeSequence.objects.filter(last_sequence__gt=0).exists())

    def test_archived_records_are_not_material_orders(self):
        """A separate table cannot leak into dashboards, KPIs or work queues by
        accident — the isolation does not depend on anyone remembering a filter."""
        from Inventory.models import MaterialOrder
        import_archive_rows([_row()], user=None)
        self.assertEqual(MaterialOrder.objects.count(), 0)
        self.assertEqual(ArchivedRequisition.objects.count(), 1)

    def test_the_original_reference_is_preserved_verbatim(self):
        import_archive_rows([_row(reference='MOEN/REQ/2023/0142')], user=None)
        self.assertTrue(
            ArchivedRequisition.objects.filter(reference='MOEN/REQ/2023/0142').exists())


class DateParsingTests(TestCase):
    def test_iso_and_day_first_formats(self):
        self.assertEqual(parse_document_date('2023-06-14')[0], date(2023, 6, 14))
        self.assertEqual(parse_document_date('14/06/2023')[0], date(2023, 6, 14))

    def test_day_first_wins_for_ambiguous_dates(self):
        """05/08/2024 is 5 August here, not 8 May — misreading it misfiles the
        record."""
        self.assertEqual(parse_document_date('05/08/2024')[0], date(2024, 8, 5))

    def test_blank_is_allowed(self):
        """Old paper is often undated or illegible."""
        value, error = parse_document_date('')
        self.assertIsNone(value)
        self.assertIsNone(error)

    def test_nonsense_reports_an_error(self):
        value, error = parse_document_date('sometime in June')
        self.assertIsNone(value)
        self.assertIn('not a date', error)


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class BulkImportTests(TestCase):
    def test_a_clean_file_imports(self):
        result = import_archive_rows([_row(), _row(reference='MOEN/REQ/2023/0143')], user=None)
        self.assertEqual(result.created_count, 2)
        self.assertFalse(result.has_errors)

    def test_scans_are_matched_by_filename(self):
        scan = SimpleUploadedFile('req-0142.pdf', b'%PDF-1.4 scan', content_type='application/pdf')
        result = import_archive_rows(
            [_row(scan_filename='req-0142.pdf')],
            scans_by_name={'req-0142.pdf': scan}, user=None)
        self.assertEqual(result.created_count, 1)
        self.assertTrue(ArchivedRequisition.objects.get().has_scan)

    def test_a_missing_scan_is_an_error_not_a_silent_skip(self):
        """Silently importing without the scan would leave a record that looks
        complete but has no document behind it."""
        result = import_archive_rows([_row(scan_filename='not-uploaded.pdf')], user=None)
        self.assertTrue(result.has_errors)
        self.assertIn('No uploaded file', result.errors[0].message)

    def test_nothing_is_written_when_any_row_fails(self):
        """A half-loaded backlog is worse than none — nobody can tell which half
        is missing."""
        rows = [_row(), _row(reference='MOEN/REQ/2023/0143', description='')]
        result = import_archive_rows(rows, user=None)
        self.assertTrue(result.has_errors)
        self.assertEqual(ArchivedRequisition.objects.count(), 0)

    def test_duplicate_references_within_the_file_are_caught(self):
        result = import_archive_rows([_row(), _row()], user=None)
        self.assertTrue(result.has_errors)
        self.assertIn('more than once', result.errors[0].message)

    def test_re_importing_an_existing_reference_is_rejected(self):
        """Makes re-running a corrected file safe."""
        import_archive_rows([_row()], user=None)
        result = import_archive_rows([_row()], user=None)
        self.assertTrue(result.has_errors)
        self.assertIn('already archived', result.errors[0].message)

    def test_rows_are_tagged_with_a_batch(self):
        """So a bad load can be found and removed."""
        import_archive_rows([_row()], user=None, batch='abc123')
        self.assertEqual(ArchivedRequisition.objects.get().import_batch, 'abc123')

    def test_an_unknown_request_type_is_rejected(self):
        result = import_archive_rows([_row(request_type='Borrowed')], user=None)
        self.assertTrue(result.has_errors)

    def test_the_release_letter_is_captured(self):
        """The letter carries the authorising signature — archiving the
        requisition alone leaves half the record."""
        letter = SimpleUploadedFile('rl-0088.pdf', b'%PDF-1.4 letter',
                                    content_type='application/pdf')
        result = import_archive_rows(
            [_row(release_letter_reference='MOEN/RL/2023/0088',
                  release_letter_date='2023-06-21',
                  release_letter_filename='rl-0088.pdf')],
            scans_by_name={'rl-0088.pdf': letter}, user=None)

        self.assertEqual(result.created_count, 1)
        record = ArchivedRequisition.objects.get()
        self.assertEqual(record.release_letter_reference, 'MOEN/RL/2023/0088')
        self.assertEqual(record.release_letter_date, date(2023, 6, 21))
        self.assertTrue(record.release_letter_scan)
        self.assertTrue(record.has_release_letter)

    def test_a_missing_release_letter_scan_is_an_error(self):
        result = import_archive_rows(
            [_row(release_letter_filename='never-uploaded.pdf')], user=None)
        self.assertTrue(result.has_errors)
        self.assertEqual(result.errors[0].column, 'release_letter_filename')

    def test_a_requisition_with_no_release_letter_still_imports(self):
        """Not every requisition was actioned, and some letters are lost."""
        result = import_archive_rows([_row()], user=None)
        self.assertEqual(result.created_count, 1)
        self.assertFalse(ArchivedRequisition.objects.get().has_release_letter)


@override_settings(MEDIA_ROOT='/tmp/moen-ims-test-media')
class ArchiveViewTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user('records', password='pw')
        self.officer.groups.add(Group.objects.get_or_create(name='Schedule Officers')[0])
        self.outsider = User.objects.create_user('outsider', password='pw')
        self.outsider.groups.add(Group.objects.get_or_create(name='Consultants')[0])

        self.record = ArchivedRequisition.objects.create(
            reference='MOEN/REQ/2023/0142', description='Release of stay equipment',
            document_date=date(2023, 6, 14), community='ANTWIKROM', region='Eastern')

    def test_the_register_lists_records(self):
        self.client.force_login(self.officer)
        resp = self.client.get(reverse('archive_list'))
        self.assertContains(resp, 'MOEN/REQ/2023/0142')

    def test_the_register_states_records_are_inert(self):
        self.client.force_login(self.officer)
        resp = self.client.get(reverse('archive_list'))
        self.assertContains(resp, 'do not affect stock levels')

    def test_search_finds_by_community(self):
        self.client.force_login(self.officer)
        resp = self.client.get(reverse('archive_list'), {'q': 'antwikrom'})
        self.assertContains(resp, 'MOEN/REQ/2023/0142')

    def test_date_range_filters(self):
        self.client.force_login(self.officer)
        resp = self.client.get(reverse('archive_list'), {'from': '2024-01-01'})
        self.assertNotContains(resp, 'MOEN/REQ/2023/0142')

    def test_a_consultant_cannot_reach_the_register(self):
        self.client.force_login(self.outsider)
        self.assertIn(self.client.get(reverse('archive_list')).status_code, (302, 403))

    def test_model_column_lists_match_the_model(self):
        """Guards the class of bug that broke the single-entry form.

        The view builds `ArchivedRequisition(**data)` from MODEL_TEXT_COLUMNS.
        When `release_letter_filename` (a spreadsheet-only column naming an
        uploaded file) was added to the shared column list, it reached the model
        constructor and raised TypeError. Asserting the lists against the real
        model fields means a new import-only column cannot repeat it.
        """
        from Inventory.services.archive_import import (
            IMPORT_ONLY_COLUMNS, MODEL_DATE_COLUMNS, MODEL_TEXT_COLUMNS, ALL_COLUMNS,
        )
        field_names = {f.name for f in ArchivedRequisition._meta.get_fields()}

        for column in MODEL_TEXT_COLUMNS + MODEL_DATE_COLUMNS:
            self.assertIn(column, field_names,
                          f"'{column}' is listed as a model column but is not a field")

        for column in IMPORT_ONLY_COLUMNS:
            self.assertNotIn(column, field_names,
                             f"'{column}' is import-only but matches a model field")

        # Every column belongs to exactly one group, so none can be forgotten.
        grouped = set(MODEL_TEXT_COLUMNS) | set(MODEL_DATE_COLUMNS) | set(IMPORT_ONLY_COLUMNS)
        self.assertEqual(grouped, set(ALL_COLUMNS),
                         "ALL_COLUMNS and the grouped lists have diverged")

    def test_single_entry_creates_a_record_with_every_field(self):
        """The failing case: a full submission, including the release letter."""
        self.client.force_login(self.officer)
        resp = self.client.post(reverse('archive_create'), {
            'reference': 'MOEN/REQ/2021/0099',
            'description': 'Release of conductors',
            'document_date': '2021-05-04',
            'request_type': 'Release',
            'quantity_summary': '300 drums',
            'requested_by_name': 'A. Officer',
            'approved_by_name': 'B. Director',
            'community': 'Nkawkaw', 'district': 'Kwahu West', 'region': 'Eastern',
            'package_number': 'PKG-001', 'project_type': 'SHEP',
            'release_letter_reference': 'MOEN/RL/2021/0044',
            'release_letter_date': '2021-05-11',
            'notes': 'Recovered from the 2021 file',
        })
        self.assertEqual(resp.status_code, 302, "the form should redirect on success")

        record = ArchivedRequisition.objects.get(reference='MOEN/REQ/2021/0099')
        self.assertEqual(record.release_letter_reference, 'MOEN/RL/2021/0044')
        self.assertEqual(record.release_letter_date, date(2021, 5, 11))
        self.assertEqual(record.document_date, date(2021, 5, 4))

    def test_single_entry_creates_a_record(self):
        self.client.force_login(self.officer)
        self.client.post(reverse('archive_create'), {
            'reference': 'MOEN/REQ/2022/0007',
            'description': 'Release of conductors',
            'document_date': '2022-03-01',
            'request_type': 'Release',
        })
        self.assertTrue(ArchivedRequisition.objects.filter(
            reference='MOEN/REQ/2022/0007').exists())

    def test_a_duplicate_reference_is_refused(self):
        self.client.force_login(self.officer)
        self.client.post(reverse('archive_create'), {
            'reference': 'MOEN/REQ/2023/0142', 'description': 'Duplicate attempt'})
        self.assertEqual(ArchivedRequisition.objects.count(), 1)

    def test_the_template_downloads(self):
        self.client.force_login(self.officer)
        resp = self.client.get(reverse('archive_template'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('reference', resp.content.decode())


class ArchiveVerificationTests(TestCase):
    """An old paper reference should not read as 'no such document'."""

    def setUp(self):
        ArchivedRequisition.objects.create(
            reference='MOEN/REQ/2023/0142', description='Release of stay equipment',
            document_date=date(2023, 6, 14))

    def test_an_archived_reference_resolves(self):
        resp = self.client.get(reverse('verify_document', args=['MOEN/REQ/2023/0142']))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Archived historical record')

    def test_it_does_not_claim_the_system_issued_it(self):
        """The system cannot vouch for paper it never handled."""
        resp = self.client.get(reverse('verify_document', args=['MOEN/REQ/2023/0142']))
        self.assertContains(resp, 'not issued or processed by MOEN-IMS')
        self.assertNotContains(resp, 'Verified genuine document')

    def test_an_unknown_reference_still_reports_not_found(self):
        resp = self.client.get(reverse('verify_document', args=['MOEN/REQ/1999/0001']))
        self.assertEqual(resp.status_code, 404)
