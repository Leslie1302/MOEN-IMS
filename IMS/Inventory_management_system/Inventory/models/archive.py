from django.contrib.auth.models import User
from django.db import models
import auto_prefetch


class ArchivedRequisition(auto_prefetch.Model):
    """
    A historical paper requisition, captured for the record.

    MOEN-IMS is a "today onwards" system: everything in it flows through a live
    workflow that allocates release codes, moves stock and drives reporting.
    Years of paper requisitions predate it and still have to be findable.

    **This is a deliberately separate model, not a flag on MaterialOrder.**
    That is the whole safety argument:

      * `order_flow` decrements `InventoryItem.quantity` when an order is
        processed. A historical requisition pushed through that path would
        deduct today's stock for materials that physically left years ago —
        silently, and very hard to unpick afterwards.
      * The release workflow would try to allocate a code from the sequence the
        Registry is adopting, burning live reference numbers on old paper.
      * Dashboards, KPIs and access-rate figures query the live models. A
        separate table cannot contaminate them by accident.

    Isolation by construction beats isolation by filtering, because a filter has
    to be remembered at every future call site and this does not.

    The scan is the record. Index fields exist to find it again, not to
    reconstruct it — line items stay in the image (see
    IMPLEMENTATION decisions, 2026-08-06).
    """

    REQUEST_TYPE_CHOICES = [
        ('Release', 'Release'),
        ('Receipt', 'Receipt'),
        ('Unknown', 'Unknown'),
    ]

    # ── Identity ────────────────────────────────────────────────────────────
    # The reference printed on the original paper. Historical documents keep
    # their own reference and are NEVER issued a code from the live sequence:
    # that sequence is becoming the Registry's, and consuming numbers for
    # archived paper would corrupt it.
    reference = models.CharField(
        max_length=100, unique=True, db_index=True,
        help_text="Reference exactly as printed on the original document.")
    document_date = models.DateField(
        db_index=True, null=True, blank=True,
        help_text="Date on the document. Leave blank if illegible.")
    request_type = models.CharField(
        max_length=20, choices=REQUEST_TYPE_CHOICES, default='Release', db_index=True)

    # ── Index fields — enough to find it, not to rebuild it ────────────────
    description = models.TextField(
        help_text="What the requisition was for, in a line or two. Searchable.")
    quantity_summary = models.CharField(
        max_length=300, blank=True,
        help_text="Free text, e.g. '2,000 sets stay equipment'. Not used in any calculation.")
    requested_by_name = models.CharField(
        max_length=200, blank=True,
        help_text="Name as written on the document. Not linked to a system user — "
                  "the requester may have left the Ministry.")
    approved_by_name = models.CharField(max_length=200, blank=True)

    community = models.CharField(max_length=200, blank=True, db_index=True)
    district = models.CharField(max_length=200, blank=True)
    region = models.CharField(max_length=200, blank=True, db_index=True)
    package_number = models.CharField(max_length=200, blank=True, db_index=True)
    project_type = models.CharField(max_length=50, blank=True)

    # ── The record itself ───────────────────────────────────────────────────
    scan = models.FileField(
        upload_to='archive/requisitions/%Y/', blank=True, null=True,
        help_text="Scan of the original requisition (PDF or image).")

    # A requisition and the release letter it produced are two documents, and
    # the letter is usually the one an auditor asks for — it carries the
    # authorising signature. Archiving the requisition alone would leave half
    # the record. Kept on the same row rather than a separate model because
    # they are one event in the file, and are always retrieved together.
    release_letter_reference = models.CharField(
        max_length=100, blank=True, db_index=True,
        help_text="Reference of the release letter issued against this requisition.")
    release_letter_date = models.DateField(null=True, blank=True)
    release_letter_scan = models.FileField(
        upload_to='archive/release_letters/%Y/', blank=True, null=True,
        help_text="Scan of the signed release letter.")

    notes = models.TextField(blank=True)

    # ── Provenance ──────────────────────────────────────────────────────────
    archived_by = auto_prefetch.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='archived_requisitions')
    archived_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    import_batch = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="Groups rows loaded together, so a bad bulk import can be found and undone.")

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-document_date', '-archived_at']
        verbose_name = 'archived requisition'
        verbose_name_plural = 'archived requisitions'
        indexes = [
            models.Index(fields=['document_date', 'request_type']),
        ]

    def __str__(self):
        return f"{self.reference} ({self.document_date or 'undated'})"

    @property
    def has_scan(self):
        return bool(self.scan)

    @property
    def has_release_letter(self):
        return bool(self.release_letter_scan or self.release_letter_reference)

    @property
    def display_location(self):
        parts = [p for p in (self.community, self.district, self.region) if p]
        return ', '.join(parts)
