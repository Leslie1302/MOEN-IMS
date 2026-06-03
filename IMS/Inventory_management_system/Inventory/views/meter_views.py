"""
Views for the access-rate meter-install flow (Track B Phase B5).

Three things a user can do:

  * Log an install         -- :func:`meter_install_create`
  * Browse the queue       -- :func:`meter_install_list`
                              (own reports + verification queue for managers)
  * Verify a row           -- :func:`verify_meter_installation`
                              (manager-only; flips ``verified_at``)

Plus the bulk XLSX path:

  * Upload a file          -- :func:`meter_install_bulk_upload`

All write paths require login; verification additionally requires
``perm.add_accessrateconfig`` (used as a proxy for "manager who can move
the published rate"). Tighten via group membership in a follow-up if
needed.
"""

from __future__ import annotations

import datetime
import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms.meter import BulkMeterUploadForm, MeterInstallationForm
from ..models import Community, MeterInstallation
from ..services.bulk_import import (
    BulkImportResult, normalize_cell, require_columns,
)


# ---------------------------------------------------------------------------
# Single-row entry
# ---------------------------------------------------------------------------

@login_required
def meter_install_create(request):
    """Render the entry form / save a new MeterInstallation row."""
    if request.method == 'POST':
        form = MeterInstallationForm(request.POST, request.FILES)
        if form.is_valid():
            install = form.save(commit=False)
            install.reported_by = request.user
            install.save()
            messages.success(
                request,
                f"Logged {install.quantity} × {install.get_phase_type_display()} "
                f"meters at {install.community}. Awaiting verification.",
            )
            return redirect('meter_install_list')
    else:
        form = MeterInstallationForm(initial={'installation_date': timezone.localdate()})

    return render(request, 'Inventory/meter_install_form.html', {
        'form': form,
        'page_title': 'Log meter installation',
    })


# ---------------------------------------------------------------------------
# Listing & verification queue
# ---------------------------------------------------------------------------

@login_required
def meter_install_list(request):
    """Show recent installations + the verification queue.

    Non-managers see their own reports. Managers (anyone with
    ``Inventory.change_meterinstallation``) additionally see the
    unverified queue across the system.
    """
    can_verify = request.user.has_perm('Inventory.change_meterinstallation')

    own = (
        MeterInstallation.objects
        .filter(reported_by=request.user)
        .select_related('community', 'verified_by')
        .order_by('-installation_date', '-created_at')[:50]
    )
    queue = []
    if can_verify:
        queue = (
            MeterInstallation.objects
            .filter(verified_at__isnull=True)
            .select_related('community', 'reported_by')
            .order_by('installation_date', 'created_at')[:100]
        )

    return render(request, 'Inventory/meter_install_list.html', {
        'own_reports': own,
        'verification_queue': queue,
        'can_verify': can_verify,
        'page_title': 'Meter installations',
    })


@require_POST
@login_required
@permission_required('Inventory.change_meterinstallation', raise_exception=True)
def verify_meter_installation(request, pk: int):
    """Stamp verified_by + verified_at on a single install. Idempotent."""
    install = get_object_or_404(MeterInstallation, pk=pk)
    if install.is_verified:
        messages.info(request, f"#{install.pk} is already verified.")
    else:
        install.mark_verified(request.user)
        install.save(update_fields=['verified_by', 'verified_at'])
        messages.success(
            request,
            f"Verified #{install.pk}: {install.quantity} × "
            f"{install.get_phase_type_display()} at {install.community}.",
        )
    return redirect(request.POST.get('next') or 'meter_install_list')


# ---------------------------------------------------------------------------
# Bulk XLSX upload
# ---------------------------------------------------------------------------

REQUIRED_COLS = ('region', 'district', 'community', 'phase_type',
                 'quantity', 'installation_date')


def _parse_phase_type(raw: str) -> str | None:
    s = (raw or '').strip().lower().replace('-', '').replace(' ', '')
    if s in ('1ph', '1phase', 'single', 'singlephase', '1'):
        return '1ph'
    if s in ('3ph', '3phase', 'three', 'threephase', '3'):
        return '3ph'
    return None


def _parse_date(raw) -> datetime.date | None:
    if raw is None or raw == '':
        return None
    if isinstance(raw, datetime.datetime):
        return raw.date()
    if isinstance(raw, datetime.date):
        return raw
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.datetime.strptime(str(raw).strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def process_bulk_meter_upload(df, request_user) -> BulkImportResult:
    """Parse a pandas DataFrame of meter installs and persist valid rows.

    Returns a :class:`BulkImportResult`. Rows that fail validation are
    skipped and surfaced in the result's error list. The transaction is
    per-row so a single bad row doesn't roll back the rest -- consistent
    with the existing bulk-request behaviour.
    """
    result = BulkImportResult()

    missing = require_columns(df, REQUIRED_COLS)
    if missing:
        result.add_error(
            row_number=1, column='*',
            message=f'Missing required columns: {", ".join(missing)}',
        )
        return result

    # Build a case-insensitive column map so the rest of the loop can use
    # canonical names regardless of how the user cased their headers.
    canonical = {c.strip().lower(): c for c in df.columns}

    def cell(row, name):
        return normalize_cell(row.get(canonical[name.lower()], ''))

    for idx, row in df.iterrows():
        row_no = idx + 2  # 1-based with header row
        result.total_rows += 1

        region    = cell(row, 'region')
        district  = cell(row, 'district')
        community = cell(row, 'community')
        if not (region and district and community):
            result.add_error(
                row_no, 'community',
                'region / district / community are all required.',
                f"{region} / {district} / {community}",
            )
            continue

        phase = _parse_phase_type(cell(row, 'phase_type'))
        if phase is None:
            result.add_error(
                row_no, 'phase_type',
                "phase_type must be '1ph' or '3ph'.",
                cell(row, 'phase_type'),
            )
            continue

        try:
            quantity = int(float(cell(row, 'quantity') or 0))
        except (TypeError, ValueError):
            quantity = 0
        if quantity <= 0:
            result.add_error(
                row_no, 'quantity',
                'quantity must be a positive integer.',
                cell(row, 'quantity'),
            )
            continue

        install_date = _parse_date(row.get(canonical['installation_date']))
        if install_date is None:
            result.add_error(
                row_no, 'installation_date',
                "installation_date must be a real date (YYYY-MM-DD or DD/MM/YYYY).",
                cell(row, 'installation_date'),
            )
            continue

        community_obj = (
            Community.objects.filter(
                region__iexact=region, district__iexact=district,
                community__iexact=community, is_active=True,
            ).first()
        )
        if community_obj is None:
            result.add_error(
                row_no, 'community',
                f"No active Community matches {region}/{district}/{community}.",
                f"{region} / {district} / {community}",
            )
            continue

        notes = cell(row, 'notes') if 'notes' in canonical else ''

        try:
            with transaction.atomic():
                MeterInstallation.objects.create(
                    community=community_obj,
                    phase_type=phase,
                    quantity=quantity,
                    installation_date=install_date,
                    reported_by=request_user,
                    notes=notes,
                )
            result.created_count += 1
        except Exception as exc:  # pragma: no cover - defensive
            result.add_error(row_no, '*', f'Save failed: {exc}')

    return result


@login_required
def meter_install_bulk_upload(request):
    """File-picker view. POST runs the parser; GET renders the form."""
    import pandas as pd  # lazy import so module-load stays cheap

    form = BulkMeterUploadForm(request.POST or None, request.FILES or None)
    result: BulkImportResult | None = None

    if request.method == 'POST' and form.is_valid():
        upload = form.cleaned_data['file']
        try:
            df = pd.read_excel(io.BytesIO(upload.read()))
        except Exception as exc:
            messages.error(request, f"Could not read XLSX: {exc}")
            return redirect('meter_install_bulk_upload')

        result = process_bulk_meter_upload(df, request.user)
        if result.created_count:
            messages.success(request, result.summary())
        if result.has_errors:
            messages.warning(
                request,
                f"{result.error_count} row(s) had issues. Scroll down for "
                "the per-row report.",
            )

    return render(request, 'Inventory/meter_install_bulk_upload.html', {
        'form': form,
        'result': result,
        'page_title': 'Bulk upload meter installations',
    })


@login_required
def meter_install_bulk_errors_csv(request):
    """Return the most recent bulk-upload errors as a CSV.

    Stateless: requires the errors to be passed back via POST so we don't
    keep them in session. The bulk-upload template offers this as an
    optional download button after a failed upload.
    """
    # The simplest viable implementation: regenerate the CSV from a list
    # of error tuples posted back from the template. Keeping the API
    # narrow on purpose -- the result object isn't pickled into session.
    if request.method != 'POST':
        return HttpResponseRedirect(reverse('meter_install_bulk_upload'))

    import csv
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        'attachment; filename="meter_upload_errors.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(['row_number', 'column', 'message', 'raw_value'])
    for line in request.POST.getlist('error_lines'):
        writer.writerow(line.split('\t'))
    return response
