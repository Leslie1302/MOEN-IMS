from django.db import models
import auto_prefetch


class ReleaseCodeSequence(auto_prefetch.Model):
    """
    The counter behind release-event codes, one row per year.

    Release codes are the Ministry Registry's official outgoing reference for
    release letters, so allocation has to behave like a registry sequence: no
    duplicates ever, and every issued number resolves to a record for good.

    The previous allocator derived the next number with `Max(code) + 1` over
    ReleaseLetter, which had two defects:

      * it emitted `SELECT MAX(code) ... FOR UPDATE`, which **PostgreSQL rejects
        outright** ("FOR UPDATE is not allowed with aggregate functions") — so it
        could not work on the production database at all;
      * it read the maximum and returned, leaving the caller to save later, so
        two concurrent generations could read the same value. The unique
        constraint on `ReleaseLetter.code` turned that into an IntegrityError
        rather than a duplicate, which is the right failure, but still a
        user-visible one.

    Locking a single dedicated row per year fixes both: `SELECT ... FOR UPDATE`
    on one row is valid SQL everywhere, serialises concurrent allocators, and the
    counter advances inside the same transaction that reads it.

    The counter is deliberately independent of the ReleaseLetter table. Deleting
    a release must never make its number available again — a registry reference
    cannot be reissued to a different document.
    """

    year = models.PositiveIntegerField(unique=True, db_index=True)
    last_sequence = models.PositiveIntegerField(
        default=0,
        help_text="Highest sequence number issued for this year. Never decreases.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-year']
        verbose_name = 'release code sequence'
        verbose_name_plural = 'release code sequences'

    def __str__(self):
        return f"{self.year}: {self.last_sequence} issued"
