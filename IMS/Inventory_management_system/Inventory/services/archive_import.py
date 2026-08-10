"""
Bulk load of historical paper requisitions: one spreadsheet plus a folder of scans.

Matching is by filename — the spreadsheet names the scan file for each row, and
the officer uploads the scans alongside it. That is deliberately dumber than
parsing references out of filenames: registry scans are named inconsistently
(`REQ 142.pdf`, `req-142_signed.PDF`, `142.jpg`) and a clever matcher that gets
it subtly wrong would attach the wrong scan to the wrong record — a filing error
that is invisible until someone requests the document years later.

Rows are validated first and written in one transaction, so a spreadsheet with
errors imports nothing rather than half a backlog. Each run is tagged with an
`import_batch` so a bad load can be found and removed.
"""

import logging
import uuid
from datetime import date, datetime

from django.db import transaction

from .bulk_import import BulkImportResult, normalize_cell

logger = logging.getLogger(__name__)

# Columns are grouped by WHAT THEY ARE, not by whether they are required.
#
# The single-entry view builds model kwargs from these lists. It used to take
# "every column except a hardcoded exclusion list", which broke the moment a new
# import-only column was added (`release_letter_filename` went straight into
# ArchivedRequisition(**data) and raised TypeError). Naming each group
# explicitly means a new column cannot leak into the model constructor.

# Map 1:1 onto CharField/TextField on the model.
MODEL_TEXT_COLUMNS = [
    'reference', 'description', 'request_type', 'quantity_summary',
    'requested_by_name', 'approved_by_name', 'community', 'district', 'region',
    'package_number', 'project_type', 'notes',
    # The release letter issued against the requisition — usually the document
    # an auditor actually asks for, since it carries the authorising signature.
    'release_letter_reference',
]

# Parsed into date objects before they reach the model.
MODEL_DATE_COLUMNS = ['document_date', 'release_letter_date']

# Spreadsheet-only: they name an uploaded file and are NEVER model fields.
IMPORT_ONLY_COLUMNS = ['scan_filename', 'release_letter_filename']

REQUIRED_COLUMNS = ['reference', 'description']

# Order here is the order of the downloadable template, so keep it readable.
ALL_COLUMNS = [
    'reference', 'description', 'document_date', 'request_type',
    'quantity_summary', 'requested_by_name', 'approved_by_name',
    'community', 'district', 'region', 'package_number', 'project_type',
    'notes', 'scan_filename',
    'release_letter_reference', 'release_letter_date', 'release_letter_filename',
]

_DATE_FORMATS = ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%m/%d/%Y', '%d %b %Y', '%d %B %Y')


def parse_document_date(raw):
    """→ (date|None, error|None). Blank is allowed — old paper is often undated.

    Day-first is tried before month-first: these are Ghanaian records, and
    reading 05/08/2024 as 8 May rather than 5 August would misfile it.
    """
    text = normalize_cell(raw)
    if not text:
        return None, None
    if isinstance(raw, (datetime, date)):
        return (raw.date() if isinstance(raw, datetime) else raw), None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    return None, f"'{text}' is not a date we recognise (try YYYY-MM-DD or DD/MM/YYYY)."


def import_archive_rows(rows, scans_by_name=None, user=None, batch=None):
    """Validate and load historical requisitions.

    `rows` is an iterable of dicts keyed by column name (row 2 is the first).
    `scans_by_name` maps uploaded filenames to file objects.

    Nothing is written unless every row validates: a half-loaded backlog is
    worse than none, because nobody can tell which half is missing.
    """
    from Inventory.models import ArchivedRequisition

    result = BulkImportResult()
    scans_by_name = {k.strip().lower(): v for k, v in (scans_by_name or {}).items()}
    batch = batch or uuid.uuid4().hex[:12]

    prepared = []
    seen_references = set()

    for offset, row in enumerate(rows):
        row_number = offset + 2      # header is row 1
        result.total_rows += 1

        reference = normalize_cell(row.get('reference'))
        if not reference:
            result.add_error(row_number, 'reference', "Reference is required.")
            continue
        if reference.lower() in seen_references:
            result.add_error(row_number, 'reference',
                             f"'{reference}' appears more than once in this file.", reference)
            continue
        if ArchivedRequisition.objects.filter(reference__iexact=reference).exists():
            result.add_error(row_number, 'reference',
                             f"'{reference}' is already archived.", reference)
            continue
        seen_references.add(reference.lower())

        description = normalize_cell(row.get('description'))
        if not description:
            result.add_error(row_number, 'description',
                             "Describe what the requisition was for — this is what makes it findable.")
            continue

        document_date, date_error = parse_document_date(row.get('document_date'))
        if date_error:
            result.add_error(row_number, 'document_date', date_error, row.get('document_date'))
            continue

        request_type = normalize_cell(row.get('request_type')).title() or 'Release'
        if request_type not in ('Release', 'Receipt', 'Unknown'):
            result.add_error(row_number, 'request_type',
                             "Must be Release, Receipt or Unknown.", request_type)
            continue

        letter_date, letter_date_error = parse_document_date(row.get('release_letter_date'))
        if letter_date_error:
            result.add_error(row_number, 'release_letter_date', letter_date_error,
                             row.get('release_letter_date'))
            continue

        # A named-but-missing scan is an error, never a silent skip: importing
        # without it leaves a record that looks complete but has no document
        # behind it, discovered only when someone requests the file.
        attachments = {}
        missing_scan = False
        for column, field in (('scan_filename', 'scan'),
                              ('release_letter_filename', 'release_letter_scan')):
            name = normalize_cell(row.get(column))
            if not name:
                continue
            uploaded = scans_by_name.get(name.lower())
            if uploaded is None:
                result.add_error(
                    row_number, column,
                    f"No uploaded file named '{name}'. Check the spelling and "
                    "that the scan was included.", name)
                missing_scan = True
                break
            attachments[field] = (name, uploaded)
        if missing_scan:
            continue

        prepared.append((ArchivedRequisition(
            reference=reference,
            description=description,
            document_date=document_date,
            request_type=request_type,
            quantity_summary=normalize_cell(row.get('quantity_summary'))[:300],
            requested_by_name=normalize_cell(row.get('requested_by_name'))[:200],
            approved_by_name=normalize_cell(row.get('approved_by_name'))[:200],
            community=normalize_cell(row.get('community'))[:200],
            district=normalize_cell(row.get('district'))[:200],
            region=normalize_cell(row.get('region'))[:200],
            package_number=normalize_cell(row.get('package_number'))[:200],
            project_type=normalize_cell(row.get('project_type'))[:50],
            notes=normalize_cell(row.get('notes')),
            release_letter_reference=normalize_cell(row.get('release_letter_reference'))[:100],
            release_letter_date=letter_date,
            archived_by=user,
            import_batch=batch,
        ), attachments))

    if result.has_errors:
        # All-or-nothing: report every problem at once so the officer fixes the
        # spreadsheet in one pass rather than discovering errors row by row.
        result.skipped_count = len(prepared)
        return result

    with transaction.atomic():
        for record, attachments in prepared:
            for field, (name, uploaded) in attachments.items():
                getattr(record, field).save(name, uploaded, save=False)
            record.save()
            result.created_count += 1

    logger.info("Archived %s historical requisitions (batch %s) by %s",
                result.created_count, batch, user)
    result.batch = batch
    return result
