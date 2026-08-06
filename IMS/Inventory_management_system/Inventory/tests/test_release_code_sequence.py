"""The release code allocator, which now backs the Ministry Registry reference.

These codes are quoted by IMS, the Registry, MMU and Internal Audit, so the
allocator has to behave like a registry sequence: never a duplicate, never
reissued, and correct on PostgreSQL (the old Max()+1 emitted
`SELECT MAX(...) FOR UPDATE`, which Postgres rejects outright).
"""

from concurrent.futures import ThreadPoolExecutor

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings

from Inventory.models import ReleaseCodeSequence, ReleaseLetter
from Inventory.services.release_code import (
    format_release_code, next_release_code, sync_sequence_from_existing,
)


class FormatTests(TestCase):
    def test_default_format(self):
        self.assertEqual(format_release_code(2026, 1), 'RE-2026-0001')
        self.assertEqual(format_release_code(2026, 142), 'RE-2026-0142')

    @override_settings(RELEASE_CODE_FORMAT='MOEN/IEPS/RE/{year}/{seq:04d}')
    def test_registry_can_impose_its_own_format(self):
        """The Registry chooses the convention; it must not be a code change."""
        self.assertEqual(format_release_code(2026, 7), 'MOEN/IEPS/RE/2026/0007')


class AllocationTests(TestCase):
    def test_allocates_sequentially(self):
        self.assertEqual(next_release_code(2026), 'RE-2026-0001')
        self.assertEqual(next_release_code(2026), 'RE-2026-0002')
        self.assertEqual(next_release_code(2026), 'RE-2026-0003')

    def test_counter_is_per_year(self):
        next_release_code(2026)
        next_release_code(2026)
        self.assertEqual(next_release_code(2027), 'RE-2027-0001')
        self.assertEqual(next_release_code(2026), 'RE-2026-0003')

    def test_no_aggregate_so_it_works_on_postgres(self):
        """Regression guard for the defect that forced this rewrite.

        The old allocator built `SELECT MAX(code) ... FOR UPDATE`, which
        PostgreSQL rejects outright: "FOR UPDATE is not allowed with aggregate
        functions". Assert no aggregate reaches the database at all, rather than
        counting queries — the count is an implementation detail, the absence of
        an aggregate is the actual contract.
        """
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as captured:
            next_release_code(2026)

        sql = ' '.join(q['sql'].upper() for q in captured.captured_queries)
        self.assertNotIn('MAX(', sql)
        self.assertNotIn('AGGREGATE', sql)

    def test_deleting_a_release_does_not_free_its_number(self):
        """A registry reference must never be reissued to a different document."""
        code = next_release_code(2026)
        letter = ReleaseLetter.objects.create(request_code='REQ-SEQ-1', code=code)
        letter.delete()
        self.assertNotEqual(next_release_code(2026), code)

    def test_skips_a_code_that_already_exists(self):
        """Codes issued by the old Max()+1 allocator can sit ahead of the counter."""
        ReleaseCodeSequence.objects.create(year=2026, last_sequence=0)
        ReleaseLetter.objects.create(request_code='REQ-SEQ-2', code='RE-2026-0001')
        self.assertEqual(next_release_code(2026), 'RE-2026-0002')


class SyncTests(TestCase):
    def test_sync_advances_past_existing_codes(self):
        ReleaseLetter.objects.create(request_code='REQ-SYNC-1', code='RE-2026-0007')
        ReleaseLetter.objects.create(request_code='REQ-SYNC-2', code='RE-2026-0042')
        self.assertEqual(sync_sequence_from_existing(2026), 42)
        self.assertEqual(next_release_code(2026), 'RE-2026-0043')

    def test_sync_never_lowers_the_counter(self):
        ReleaseCodeSequence.objects.create(year=2026, last_sequence=99)
        ReleaseLetter.objects.create(request_code='REQ-SYNC-3', code='RE-2026-0007')
        self.assertEqual(sync_sequence_from_existing(2026), 99)

    def test_sync_is_idempotent(self):
        ReleaseLetter.objects.create(request_code='REQ-SYNC-4', code='RE-2026-0011')
        self.assertEqual(sync_sequence_from_existing(2026), 11)
        self.assertEqual(sync_sequence_from_existing(2026), 11)


class ConcurrentAllocationTests(TransactionTestCase):
    """The second defect that forced this rewrite: two generations reading the
    same maximum and producing the same code.

    Skipped on SQLite, which serialises writes at the database level and would
    raise "database is locked" under threads rather than exercising the row
    lock. The guarantee being tested is a PostgreSQL one — run this against
    Postgres (set DATABASE_URL) to exercise it for real.
    """

    reset_sequences = True

    def test_concurrent_allocation_yields_no_duplicates(self):
        if connection.vendor == 'sqlite':
            self.skipTest('Row-level locking is a PostgreSQL guarantee; '
                          'SQLite serialises writes and would flake here.')

        workers = 8

        def allocate(_):
            try:
                return next_release_code(2026)
            finally:
                connection.close()      # each thread needs its own connection

        with ThreadPoolExecutor(max_workers=workers) as pool:
            codes = list(pool.map(allocate, range(workers)))

        self.assertEqual(len(codes), workers)
        self.assertEqual(len(set(codes)), workers,
                         f"duplicate release codes allocated: {sorted(codes)}")

    def test_sequential_allocation_never_repeats(self):
        """Backend-independent companion to the threaded test above."""
        codes = [next_release_code(2026) for _ in range(25)]
        self.assertEqual(len(set(codes)), 25)
