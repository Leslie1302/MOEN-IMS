"""
Generic bulk-import infrastructure for Excel uploads.

Each importer is a callable that:
  - takes a pandas DataFrame plus a request user (for audit fields)
  - validates each row, accumulating per-row errors
  - inside a transaction, persists every successful row OR rolls back on any error
    (configurable via `partial_commit`)
  - returns a BulkImportResult with counts and a list of row errors

The result object can be turned into a downloadable CSV via `errors_as_csv()`,
which the upload view exposes as an attachment so users can see exactly which
rows failed and why.

Schemas are defined per importer rather than via a generic spec language --
keeping it simple and inline. Each importer lives next to its model for
discoverability.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional, Tuple
import csv
import io


@dataclass
class RowError:
    row_number: int        # 1-indexed, matches Excel row (header is row 1, first data row is 2)
    column: str            # column name or '*' for whole-row errors
    message: str
    raw_value: str = ''


@dataclass
class BulkImportResult:
    total_rows: int = 0
    created_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: List[RowError] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.error_count == 0 and self.created_count > 0

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def add_error(self, row_number: int, column: str, message: str, raw_value: Any = '') -> None:
        self.errors.append(RowError(
            row_number=row_number,
            column=column,
            message=str(message),
            raw_value=str(raw_value) if raw_value is not None else '',
        ))
        self.error_count += 1

    def summary(self) -> str:
        parts = []
        if self.created_count:
            parts.append(f"{self.created_count} created")
        if self.skipped_count:
            parts.append(f"{self.skipped_count} skipped")
        if self.error_count:
            parts.append(f"{self.error_count} error{'s' if self.error_count != 1 else ''}")
        if not parts:
            parts.append("no rows processed")
        return ", ".join(parts) + "."

    def errors_as_csv(self) -> bytes:
        """Render errors as a CSV the user can download to fix their file."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['row_number', 'column', 'message', 'raw_value'])
        for err in self.errors:
            writer.writerow([err.row_number, err.column, err.message, err.raw_value])
        return buf.getvalue().encode('utf-8')


def normalize_cell(value: Any) -> str:
    """
    pandas reads empty cells as float('nan') and numeric cells as floats.
    Normalize to a stripped string suitable for CharField storage.
    """
    if value is None:
        return ''
    # pandas NaN: float('nan') != float('nan')
    if isinstance(value, float) and value != value:
        return ''
    s = str(value).strip()
    if s.lower() == 'nan':
        return ''
    return s


def require_columns(df, required: Iterable[str]) -> Optional[List[str]]:
    """
    Return a list of missing required column names, or None if all present.
    Column matching is case-insensitive against df.columns.
    """
    cols = {c.strip().lower(): c for c in df.columns}
    missing = [r for r in required if r.lower() not in cols]
    return missing or None
