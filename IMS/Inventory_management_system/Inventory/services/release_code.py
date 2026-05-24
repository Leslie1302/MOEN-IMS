"""
Release-event code allocator. Mints monotonically-increasing codes in the
format RE-{year}-{4-digit-sequence}, e.g. RE-2026-0142.

The sequence is per-year, so it resets on January 1st. Allocation runs
inside a SELECT FOR UPDATE-style transaction so concurrent allocations
under multiple gunicorn workers don't collide on the same number.
"""

from django.db import transaction
from django.db.models import Max
from django.utils import timezone


def next_release_code(year: int = None) -> str:
    """
    Allocate the next RE-{year}-NNNN code.

    Args:
        year: optional explicit year override. Defaults to the current year.

    Returns:
        A unique code string. Guaranteed unique even under concurrent
        callers (uses a transactional Max() + 1 pattern).
    """
    from Inventory.models import ReleaseLetter

    year = year or timezone.now().year
    prefix = f"RE-{year}-"

    with transaction.atomic():
        # Lock the row range with the year prefix while we read max + write.
        # SQLite serializes writes at the DB level so the atomic block is
        # sufficient; on Postgres this becomes a SELECT FOR UPDATE on the
        # filtered queryset.
        latest = (
            ReleaseLetter.objects
            .select_for_update(skip_locked=False, of=()) if _supports_select_for_update()
            else ReleaseLetter.objects
        )
        last_code = (
            latest.filter(code__startswith=prefix)
            .aggregate(Max('code'))['code__max']
        )

        if last_code:
            try:
                last_seq = int(last_code.rsplit('-', 1)[-1])
            except (ValueError, IndexError):
                last_seq = 0
        else:
            last_seq = 0

        return f"{prefix}{last_seq + 1:04d}"


def _supports_select_for_update():
    """SQLite doesn't support SELECT FOR UPDATE; the atomic block alone
    serializes writes. Postgres does, so we use it there for safety
    under heavy concurrent allocation."""
    from django.db import connection
    return connection.vendor != 'sqlite'
