"""Shared plumbing for professional (Ministry house-style) report PDFs.

``preparer_context`` auto-fills the "Prepared by" / sign-off block from the
signed-in user's profile; ``render_pdf`` turns a template into a PDF response,
degrading gracefully where WeasyPrint is unavailable.
"""
import logging

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


def preparer_context(user):
    """Name / designation / office for the report's preparer + today's date."""
    prof = getattr(user, 'profile', None)
    name = ''
    if getattr(user, 'is_authenticated', False):
        name = user.get_full_name() or user.username
    return {
        'prepared_by_name': name,
        'prepared_by_title': getattr(prof, 'designation', '') or '',
        'prepared_by_office': getattr(prof, 'office', '') or '',
        'generated_on': timezone.localdate(),
    }


def render_pdf(template, context, filename):
    """Render ``template`` with ``context`` to an inline PDF HttpResponse."""
    html = render_to_string(template, context)
    try:
        from weasyprint import HTML
    except Exception:  # noqa: BLE001 — renderer libs may be absent on a host
        logger.exception("WeasyPrint unavailable for %s", filename)
        return HttpResponse(
            "PDF renderer is not available on this server. "
            "Use the Excel export or view on screen instead.", status=503)
    pdf = HTML(string=html).write_pdf()
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = f'inline; filename="{filename}"'
    return resp
