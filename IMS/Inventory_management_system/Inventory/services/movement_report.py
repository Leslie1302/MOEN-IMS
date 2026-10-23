"""Materials movement report — what moved in a period, where it went, status.

Built on the append-only StockMovement ledger (the tally cards). Produces two
views over a date range:

* ``summary``  — one row per material: received, issued, transfers, adjustments,
                 write-offs, reversals, net change, and closing balance.
* ``detail``   — one row per movement, enriched with its destination and the
                 order status where the movement came from a release/receipt.

Destination/status enrichment: issue/receipt rows carry the request code in
their note ("Release order REQ-…"); we pull it out, look up the MaterialOrder,
and read the site from its linked Bill of Quantity.
"""
import re
from collections import OrderedDict
from datetime import date, datetime, timedelta

from django.utils import timezone

from Inventory.models import MaterialOrder, StockMovement

# A request/receipt code: REQ- or RCPT- followed by one or more hyphen-joined
# alphanumeric groups (handles REQ-20261009-285606 and REQ-DEMO-0001 alike).
_REQ_RE = re.compile(r'((?:REQ|RCPT)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)', re.IGNORECASE)


def resolve_period(period, raw_from='', raw_to=''):
    """Return (date_from, date_to, label) for a named period or custom range.

    ``period`` is one of week/month/year/custom. Dates are inclusive. 'week'
    is the Monday–Sunday week containing today; 'month' and 'year' are the
    calendar month/year to date's containing period.
    """
    today = timezone.localdate()

    def _parse(s):
        try:
            return datetime.strptime(s, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None

    if period == 'custom':
        d_from = _parse(raw_from) or today
        d_to = _parse(raw_to) or today
        if d_to < d_from:
            d_from, d_to = d_to, d_from
        return d_from, d_to, f"{d_from:%d %b %Y} – {d_to:%d %b %Y}"

    if period == 'month':
        d_from = today.replace(day=1)
        return d_from, today, f"{d_from:%B %Y} (to {today:%d %b})"

    if period == 'year':
        d_from = date(today.year, 1, 1)
        return d_from, today, f"{today.year} (to {today:%d %b})"

    # default: week (Monday..Sunday containing today)
    d_from = today - timedelta(days=today.weekday())
    d_to = d_from + timedelta(days=6)
    return d_from, d_to, f"Week of {d_from:%d %b} – {d_to:%d %b %Y}"


def _destination_and_status(refs):
    """Map each request-code reference to (destination, status).

    One query for all the codes seen in the period. Destination comes from the
    order's linked BoQ (community / district / region); status is the order's.
    """
    refs = {r for r in refs if r}
    if not refs:
        return {}
    orders = (MaterialOrder.objects
              .filter(request_code__in=refs)
              .select_related('linked_boq_item'))
    out = {}
    for o in orders:
        boq = o.linked_boq_item
        if boq:
            parts = [boq.community, boq.district, boq.region]
            dest = ', '.join(p for p in parts if p) or '—'
        else:
            dest = '—'
        # A request code can map to several sub-orders; first non-empty wins.
        out.setdefault(o.request_code, (dest, o.status))
    return out


def _ref_from_note(note):
    m = _REQ_RE.search(note or '')
    return m.group(1) if m else ''


def build_report(date_from, date_to, warehouse_id=None):
    """Assemble the movement report for the inclusive date range."""
    qs = (StockMovement.objects
          .filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
          .select_related('item', 'item__warehouse', 'item__unit', 'performed_by')
          .order_by('created_at', 'id'))
    if warehouse_id:
        qs = qs.filter(item__warehouse_id=warehouse_id)
    movements = list(qs)

    enrich = _destination_and_status(
        {_ref_from_note(m.note) for m in movements})

    detail = []
    # summary keyed by (item_code, item_name, warehouse)
    summary = OrderedDict()
    for m in movements:
        ref_code = _ref_from_note(m.note)
        dest, status = enrich.get(ref_code, ('—', ''))
        qty_in = float(m.qty_in or 0)
        qty_out = float(m.qty_out or 0)
        detail.append({
            'date': m.created_at,
            'material': m.item.name,
            'code': m.item.code or '',
            'warehouse': getattr(m.item.warehouse, 'name', '') or '—',
            'type': m.get_movement_type_display(),
            'type_raw': m.movement_type,
            'qty_in': qty_in,
            'qty_out': qty_out,
            'balance_after': float(m.balance_after or 0),
            'reference': m.reference or '',
            'destination': dest,
            'status': status or '—',
            'by': (m.performed_by.get_full_name() or m.performed_by.username)
                  if m.performed_by else 'system',
        })

        key = (m.item.code or '', m.item.name, getattr(m.item.warehouse, 'name', '') or '—')
        row = summary.setdefault(key, {
            'code': m.item.code or '', 'material': m.item.name,
            'warehouse': getattr(m.item.warehouse, 'name', '') or '—',
            'unit': getattr(m.item.unit, 'name', '') or '',
            'received': 0.0, 'issued': 0.0, 'transfer_in': 0.0, 'transfer_out': 0.0,
            'adjustment': 0.0, 'write_off': 0.0, 'reversal': 0.0,
            'net': 0.0, 'closing_balance': 0.0,
        })
        bucket = {
            'receipt': 'received', 'issue': 'issued',
            'transfer_in': 'transfer_in', 'transfer_out': 'transfer_out',
            'adjustment': 'adjustment', 'write_off': 'write_off',
            'reversal': 'reversal', 'opening': 'received',
        }.get(m.movement_type)
        if bucket:
            row[bucket] += qty_in if qty_in else qty_out
        row['net'] += qty_in - qty_out
        row['closing_balance'] = float(m.balance_after or 0)  # last seen wins

    totals = {
        'received': sum(r['received'] for r in summary.values()),
        'issued': sum(r['issued'] for r in summary.values()),
        'movements': len(detail),
        'materials': len(summary),
    }
    return {
        'date_from': date_from, 'date_to': date_to,
        'summary': list(summary.values()),
        'detail': detail,
        'totals': totals,
    }
