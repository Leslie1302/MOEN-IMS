"""
The historical requisition register.

MOEN-IMS only knows about work that started inside it. Years of paper
requisitions predate it and still have to be produced on request — for audit,
for a query about an old community, or simply to answer "what did we release to
this district in 2023?".

These records are inert by design: a separate model that no stock, workflow or
reporting code path touches. Everything here is read, search and capture.
"""

import csv
import io
import logging
import uuid

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView

from Inventory.models import ArchivedRequisition
from Inventory.services.archive_import import (
    ALL_COLUMNS, REQUIRED_COLUMNS, import_archive_rows, parse_document_date,
)

logger = logging.getLogger(__name__)

MAX_SCAN_BYTES = 25 * 1024 * 1024
ALLOWED_SCAN_EXTENSIONS = ('.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff')


def _may_archive(user):
    """Records work: registry and schedule staff, plus management."""
    return (user.is_superuser
            or user.groups.filter(
                name__in=['Management', 'Schedule Officers', 'Store Officers']).exists())


class ArchiveAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and _may_archive(self.request.user)


class ArchiveListView(ArchiveAccessMixin, ListView):
    """Searchable register of historical requisitions."""
    model = ArchivedRequisition
    template_name = 'Inventory/archive_list.html'
    context_object_name = 'records'
    paginate_by = 25

    def get_queryset(self):
        qs = ArchivedRequisition.objects.select_related('archived_by')

        query = (self.request.GET.get('q') or '').strip()
        if query:
            qs = qs.filter(
                Q(reference__icontains=query) |
                Q(description__icontains=query) |
                Q(community__icontains=query) |
                Q(district__icontains=query) |
                Q(package_number__icontains=query) |
                Q(requested_by_name__icontains=query))

        request_type = (self.request.GET.get('type') or '').strip()
        if request_type:
            qs = qs.filter(request_type=request_type)

        region = (self.request.GET.get('region') or '').strip()
        if region:
            qs = qs.filter(region__iexact=region)

        # Date range — the most common way anyone asks for old records.
        date_from, _ = parse_document_date(self.request.GET.get('from'))
        date_to, _ = parse_document_date(self.request.GET.get('to'))
        if date_from:
            qs = qs.filter(document_date__gte=date_from)
        if date_to:
            qs = qs.filter(document_date__lte=date_to)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['sel_type'] = self.request.GET.get('type', '')
        ctx['sel_region'] = self.request.GET.get('region', '')
        ctx['date_from'] = self.request.GET.get('from', '')
        ctx['date_to'] = self.request.GET.get('to', '')
        ctx['total_archived'] = ArchivedRequisition.objects.count()
        ctx['regions'] = (ArchivedRequisition.objects.exclude(region='')
                          .values_list('region', flat=True).distinct().order_by('region'))
        return ctx


class ArchiveDetailView(ArchiveAccessMixin, DetailView):
    model = ArchivedRequisition
    template_name = 'Inventory/archive_detail.html'
    context_object_name = 'record'


class ArchiveCreateView(ArchiveAccessMixin, View):
    """Capture one historical requisition — for stragglers and corrections."""
    template_name = 'Inventory/archive_form.html'

    def get(self, request):
        return render(request, self.template_name, {'record': None})

    TEXT_FIELDS = [f for f in ALL_COLUMNS
                   if f not in ('scan_filename', 'document_date', 'release_letter_date')]

    def post(self, request):
        data = {k: (request.POST.get(k) or '').strip() for k in self.TEXT_FIELDS}
        data['document_date'] = (request.POST.get('document_date') or '').strip()
        data['release_letter_date'] = (request.POST.get('release_letter_date') or '').strip()

        errors = []
        if not data.get('reference'):
            errors.append("Reference is required.")
        elif ArchivedRequisition.objects.filter(reference__iexact=data['reference']).exists():
            errors.append(f"'{data['reference']}' is already archived.")
        if not data.get('description'):
            errors.append("Describe what the requisition was for — this is what makes it findable.")

        document_date, date_error = parse_document_date(data.get('document_date'))
        if date_error:
            errors.append(date_error)
        letter_date, letter_date_error = parse_document_date(data.get('release_letter_date'))
        if letter_date_error:
            errors.append(f"Release letter date: {letter_date_error}")

        files = {}
        for field, label in (('scan', 'requisition scan'),
                             ('release_letter_scan', 'release letter scan')):
            uploaded = request.FILES.get(field)
            if not uploaded:
                continue
            if not uploaded.name.lower().endswith(ALLOWED_SCAN_EXTENSIONS):
                errors.append(f"The {label} must be a PDF or an image (PNG, JPG, TIFF).")
            elif uploaded.size > MAX_SCAN_BYTES:
                errors.append(
                    f"The {label} is {uploaded.size // (1024 * 1024)} MB. Keep it under 25 MB.")
            else:
                files[field] = uploaded

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, self.template_name, {'record': None, 'posted': data})

        record = ArchivedRequisition(
            archived_by=request.user,
            document_date=document_date,
            release_letter_date=letter_date,
            **{k: v for k, v in data.items()
               if k not in ('document_date', 'release_letter_date')})
        for field, uploaded in files.items():
            setattr(record, field, uploaded)
        record.save()

        messages.success(request, f"Archived {record.reference}.")
        return redirect('archive_detail', pk=record.pk)


class ArchiveBulkImportView(ArchiveAccessMixin, View):
    """Spreadsheet plus a folder of scans, matched on filename."""
    template_name = 'Inventory/archive_bulk_import.html'

    def get(self, request):
        return render(request, self.template_name, {
            'required_columns': REQUIRED_COLUMNS,
            'all_columns': ALL_COLUMNS,
        })

    def post(self, request):
        workbook = request.FILES.get('spreadsheet')
        if not workbook:
            messages.error(request, "Choose a spreadsheet to import.")
            return redirect('archive_bulk_import')

        try:
            rows = self._read_rows(workbook)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Archive import could not read the spreadsheet")
            messages.error(request, f"That file could not be read: {exc}")
            return redirect('archive_bulk_import')

        scans = {f.name: f for f in request.FILES.getlist('scans')}
        oversized = [n for n, f in scans.items() if f.size > MAX_SCAN_BYTES]
        if oversized:
            messages.error(
                request,
                "These scans are over 25 MB: " + ", ".join(oversized[:5]) +
                ("…" if len(oversized) > 5 else ""))
            return redirect('archive_bulk_import')

        result = import_archive_rows(
            rows, scans_by_name=scans, user=request.user, batch=uuid.uuid4().hex[:12])

        if result.has_errors:
            # Nothing was written — show every problem so the file is fixed in
            # one pass rather than row by row.
            request.session['archive_import_errors'] = [
                {'row': e.row_number, 'column': e.column, 'message': e.message,
                 'value': e.raw_value}
                for e in result.errors[:200]
            ]
            messages.error(
                request,
                f"Nothing was imported. {result.error_count} row"
                f"{'s' if result.error_count != 1 else ''} need attention — "
                "fix the spreadsheet and upload it again.")
            return redirect('archive_bulk_import')

        messages.success(
            request,
            f"Archived {result.created_count} historical requisition"
            f"{'s' if result.created_count != 1 else ''}.")
        return redirect(f"{reverse('archive_list')}?batch={getattr(result, 'batch', '')}")

    @staticmethod
    def _read_rows(uploaded):
        """Read .xlsx or .csv into dicts keyed by lower-cased column name."""
        name = (uploaded.name or '').lower()
        if name.endswith('.csv'):
            text = uploaded.read().decode('utf-8-sig', errors='replace')
            return list(csv.DictReader(io.StringIO(text)))

        import openpyxl
        workbook = openpyxl.load_workbook(uploaded, data_only=True, read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [str(h).strip().lower() if h is not None else '' for h in rows[0]]
        return [dict(zip(headers, row)) for row in rows[1:]
                if any(cell is not None and str(cell).strip() for cell in row)]


class ArchiveTemplateView(ArchiveAccessMixin, View):
    """Download the spreadsheet layout, so nobody has to guess the columns."""

    def get(self, request):
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(ALL_COLUMNS)
        writer.writerow([
            'MOEN/REQ/2023/0142', 'Release of 2,000 sets stay equipment',
            '2023-06-14', 'Release', '2,000 sets', 'K. Mensah', 'Ag. Director, Power',
            'ANTWIKROM', 'Kwehu West', 'Eastern', 'SP-BAR-TND-SMA-KSDA-11-08',
            'SHEP', 'Recovered from the 2023 registry file', 'req-2023-0142.pdf',
            'MOEN/RL/2023/0088', '2023-06-21', 'rl-2023-0088-signed.pdf',
        ])
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="archive_requisitions_template.csv"'
        return response


class ArchiveImportErrorsView(ArchiveAccessMixin, View):
    """Download the last import's errors as CSV, to fix alongside the file."""

    def get(self, request):
        errors = request.session.get('archive_import_errors') or []
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['row', 'column', 'message', 'value'])
        for error in errors:
            writer.writerow([error['row'], error['column'], error['message'], error['value']])
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="archive_import_errors.csv"'
        return response
