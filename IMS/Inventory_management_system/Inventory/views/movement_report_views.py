"""Materials movement report — page + Excel export.

What moved in a period (week / month / year / custom), where it was designated,
and the status. Sourced from the StockMovement ledger (tally cards).
"""
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.views.generic import TemplateView, View

from Inventory.models import Warehouse
from Inventory.services.movement_report import build_report, resolve_period
from Inventory.utils import can_access_stores
from Inventory.utils.report_pdf import preparer_context, render_pdf


class _AccessMixin(UserPassesTestMixin):
    def test_func(self):
        return can_access_stores(self.request.user)


def _params(request):
    period = (request.GET.get('period') or 'week').strip()
    if period not in ('week', 'month', 'year', 'custom'):
        period = 'week'
    d_from, d_to, label = resolve_period(
        period, request.GET.get('from', ''), request.GET.get('to', ''))
    wh = (request.GET.get('warehouse') or '').strip()
    return period, d_from, d_to, label, (wh or None)


class MaterialsMovementReportView(LoginRequiredMixin, _AccessMixin, TemplateView):
    template_name = 'Inventory/materials_movement_report.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        period, d_from, d_to, label, wh = _params(self.request)
        ctx['report'] = build_report(d_from, d_to, wh)
        ctx['period'] = period
        ctx['period_label'] = label
        ctx['from'] = d_from.isoformat()
        ctx['to'] = d_to.isoformat()
        ctx['selected_warehouse'] = wh or ''
        ctx['warehouses'] = Warehouse.objects.order_by('name')
        return ctx


class MaterialsMovementReportExcelView(LoginRequiredMixin, _AccessMixin, View):
    def get(self, request):
        import openpyxl
        from openpyxl.styles import Font, PatternFill

        _, d_from, d_to, label, wh = _params(request)
        rep = build_report(d_from, d_to, wh)

        wb = openpyxl.Workbook()
        hdr_fill = PatternFill('solid', fgColor='0C4B33')
        hdr_font = Font(color='FFFFFF', bold=True)

        def _header(ws, cols):
            ws.append(cols)
            for c in ws[1]:
                c.fill = hdr_fill
                c.font = hdr_font

        ws1 = wb.active
        ws1.title = 'Summary'
        ws1.append([f"Materials Movement — {label}"])
        ws1.append([])
        _start = ws1.max_row + 1
        _header(ws1, ['Code', 'Material', 'Store', 'Unit', 'Received', 'Issued',
                      'Transfer In', 'Transfer Out', 'Adjustment', 'Write-off',
                      'Reversal', 'Net', 'Closing Balance'])
        # re-bold the actual header row (not row 1)
        for c in ws1[_start]:
            c.fill = hdr_fill
            c.font = hdr_font
        for r in rep['summary']:
            ws1.append([r['code'], r['material'], r['warehouse'], r['unit'],
                        r['received'], r['issued'], r['transfer_in'], r['transfer_out'],
                        r['adjustment'], r['write_off'], r['reversal'], r['net'],
                        r['closing_balance']])

        ws2 = wb.create_sheet('Detail')
        _header(ws2, ['Date', 'Material', 'Code', 'Store', 'Type', 'In', 'Out',
                      'Balance', 'Reference', 'Destination', 'Status', 'By'])
        for d in rep['detail']:
            ws2.append([
                d['date'].strftime('%Y-%m-%d %H:%M'), d['material'], d['code'],
                d['warehouse'], d['type'], d['qty_in'], d['qty_out'],
                d['balance_after'], d['reference'], d['destination'],
                d['status'], d['by']])

        resp = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = (
            f'attachment; filename="materials_movement_{d_from}_{d_to}.xlsx"')
        wb.save(resp)
        return resp


class MaterialsMovementReportPDFView(LoginRequiredMixin, _AccessMixin, View):
    """Professional PDF in the Ministry house style (masthead, title block,
    executive summary, banded tables, sign-off)."""
    def get(self, request):
        _, d_from, d_to, label, wh = _params(request)
        store_name = ''
        if wh:
            store_name = getattr(Warehouse.objects.filter(pk=wh).first(), 'name', '')
        ctx = preparer_context(request.user)
        ctx.update({
            'report': build_report(d_from, d_to, wh),
            'period_label': label,
            'store_name': store_name,
        })
        return render_pdf('Inventory/materials_movement_report_pdf.html', ctx,
                          f'materials_movement_report_{d_from}_{d_to}.pdf')
