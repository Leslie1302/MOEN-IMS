"""
Release-event code allocator.

These codes are the Ministry Registry's **official outgoing reference** for
release letters — the same string is quoted by IMS, the Registry, MMU and
Internal Audit, printed on both documents, encoded in the QR used for scan
matching, and cited in the signature stamp. Allocation therefore has to behave
like a registry sequence rather than a convenience id:

  * **never a duplicate**, under any amount of concurrency;
  * **never reissued** — deleting a release must not free its number;
  * **every issued number resolves to a record**, including voided ones (a
    registry tolerates gaps, but not a reference that resolves to nothing);
  * **format is the Registry's to choose** and cannot be changed retrospectively
    once the sequence is in use — hence `RELEASE_CODE_FORMAT` rather than a
    literal.

Allocation locks a single `ReleaseCodeSequence` row for the year. That is valid
SQL on every backend and serialises concurrent allocators, unlike the previous
`Max(code) + 1`, which PostgreSQL rejected outright and which raced.
"""

import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

# Overridable in settings so the Registry's own convention can be adopted, e.g.
# 'MOEN/IEPS/RE/{year}/{seq:04d}'. Available placeholders: {year}, {seq}.
DEFAULT_RELEASE_CODE_FORMAT = 'RE-{year}-{seq:04d}'


def release_code_format():
    return getattr(settings, 'RELEASE_CODE_FORMAT', DEFAULT_RELEASE_CODE_FORMAT)


def format_release_code(year, sequence):
    """Render a code without allocating one. Used by tests and previews."""
    return release_code_format().format(year=year, seq=sequence)


def next_release_code(year=None):
    """Allocate and return the next release code.

    The counter is advanced inside the caller's transaction, so a rolled-back
    generation does not consume a number. A committed one does, permanently.

    Raises IntegrityError if a unique code cannot be produced after a retry —
    which should be impossible with the row lock held, and is worth surfacing
    loudly rather than papering over if it ever happens.
    """
    from Inventory.models import ReleaseCodeSequence, ReleaseLetter

    year = year or timezone.now().year

    for attempt in (1, 2):
        with transaction.atomic():
            # get_or_create then lock: the row must exist before it can be
            # locked, and the first allocation of a new year would otherwise
            # find nothing to lock.
            ReleaseCodeSequence.objects.get_or_create(year=year)
            row = (ReleaseCodeSequence.objects
                   .select_for_update()
                   .get(year=year))

            row.last_sequence += 1
            row.save(update_fields=['last_sequence', 'updated_at'])
            code = format_release_code(year, row.last_sequence)

            # Belt and braces. The lock makes a collision essentially
            # impossible, but codes predating this allocator were derived from
            # Max()+1 and could in principle sit ahead of the counter.
            if not ReleaseLetter.objects.filter(code=code).exists():
                return code

            logger.warning(
                "Release code %s already exists; advancing the counter (attempt %s).",
                code, attempt)

    raise IntegrityError(
        f"Could not allocate a unique release code for {year} after two attempts.")


def sync_sequence_from_existing(year=None):
    """Advance the counter past any pre-existing codes for `year`.

    One-off reconciliation for the switch away from `Max()+1`: without it the
    new counter starts at 0 and the first few allocations collide with codes
    already issued. Idempotent, and never lowers the counter.

    Returns the sequence value after syncing.
    """
    from Inventory.models import ReleaseCodeSequence, ReleaseLetter

    year = year or timezone.now().year
    highest = 0

    # Parse the trailing digit group of every existing code for the year rather
    # than assuming a format — codes issued before a format change must still
    # be understood.
    import re
    pattern = re.compile(r'(\d+)\D*$')
    for code in (ReleaseLetter.objects
                 .filter(code__isnull=False)
                 .values_list('code', flat=True)):
        if str(year) not in code:
            continue
        match = pattern.search(code)
        if match:
            highest = max(highest, int(match.group(1)))

    with transaction.atomic():
        row, _ = ReleaseCodeSequence.objects.get_or_create(year=year)
        row = ReleaseCodeSequence.objects.select_for_update().get(pk=row.pk)
        if highest > row.last_sequence:
            logger.info("Release code sequence for %s advanced %s -> %s to clear "
                        "existing codes.", year, row.last_sequence, highest)
            row.last_sequence = highest
            row.save(update_fields=['last_sequence', 'updated_at'])
        return row.last_sequence
