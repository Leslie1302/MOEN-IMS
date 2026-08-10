"""
Public document verification — no login required.

Someone holding a physical release letter or memo (MMU, Internal Audit, a
contractor, a district officer) needs to answer one question: *is this document
real, and is it still current?* Until now they could only ask the Ministry.
Scanning the QR now lands here.

**Two tiers, because release codes are enumerable.** Codes run RE-2026-0001,
0002, 0003, so anyone can walk the sequence without ever seeing a document. A
code lookup therefore proves only that a reference exists — and presenting that
as verification would be actively harmful: a forger could enumerate to find a
real approved code, print it on a fake release letter, and have this page answer
"issued by MOEN-IMS".

  * **Code only** → existence and status. No signatories. The page says in terms
    that it has not verified the document.
  * **Valid token** (from the QR, or a signature's verification token) → full
    verification, including who signed and in what office. The token is
    unguessable, so supplying it proves the reader held the actual document.

**Disclosure principle: this page reveals nothing that is not already printed on
the paper in the reader's hand.** Never the materials, quantities, communities,
values, or the signature images — those are on the document itself if the holder
is entitled to them, and this page is readable by anyone with a camera.

The page also answers the negative case, which is the one that matters for
fraud: an unknown code says so plainly rather than 404-ing into ambiguity.
"""

import hmac
import logging

from django.http import Http404
from django.shortcuts import render
from django.views import View
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

logger = logging.getLogger(__name__)


@method_decorator(
    # Public and unauthenticated, so it is rate-limited per IP. Generous enough
    # for an office checking a stack of documents, tight enough that the
    # endpoint cannot be walked to enumerate every release code.
    ratelimit(key='ip', rate='30/m', method='GET', block=True), name='dispatch')
class VerifyDocumentView(View):
    """Resolve a release code (from the QR) or a signature verification token."""

    template_name = 'Inventory/verify_document.html'

    def get(self, request, reference):
        from Inventory.models import DocumentSignature, ReleaseLetter

        reference = (reference or '').strip()
        if not reference or len(reference) > 64:
            raise Http404("No such reference.")

        release_letter = None
        matched_signature = None
        proved_possession = False

        # A signature token is unguessable, so resolving one is itself proof the
        # reader had the document — same standing as the document token.
        if '-' in reference and len(reference.replace('-', '')) == 12:
            matched_signature = (DocumentSignature.objects
                                 .filter(verification_token__iexact=reference)
                                 .select_related('release_letter').first())
            if matched_signature:
                release_letter = matched_signature.release_letter
                proved_possession = True

        if release_letter is None:
            release_letter = (ReleaseLetter.objects
                              .filter(code__iexact=reference).first())

        if release_letter is None:
            # A pre-IMS paper reference should not read as "no such document" —
            # the document is real, it simply predates the system. Presented as
            # an archived record and explicitly NOT as something IMS issued.
            from Inventory.models import ArchivedRequisition
            archived = ArchivedRequisition.objects.filter(reference__iexact=reference).first()
            if archived:
                return render(request, self.template_name, {
                    'reference': reference, 'found': True, 'archived': archived,
                    'verified': False,
                })

            logger.info("Verify miss for reference %r from %s",
                        reference[:40], request.META.get('REMOTE_ADDR'))
            return render(request, self.template_name,
                          {'reference': reference, 'found': False}, status=404)

        # ── The two tiers ────────────────────────────────────────────────
        # Release codes are sequential and enumerable, so a code lookup proves
        # only that a reference exists. It must NOT be presented as verifying
        # the paper: a forger who enumerates a real approved code could print it
        # on a fake letter. Possession of the unguessable token is what raises
        # the answer from "this reference exists" to "this document is genuine".
        if not proved_possession:
            supplied = (request.GET.get('t') or '').strip()
            expected = release_letter.verify_token or ''
            if supplied and expected:
                proved_possession = hmac.compare_digest(supplied, expected)
            if supplied and not proved_possession:
                logger.warning("Verify token mismatch for %s from %s",
                               release_letter.code, request.META.get('REMOTE_ADDR'))

        context = {
            'reference': reference,
            'found': True,
            'release_letter': release_letter,
            'verified': proved_possession,
            'status_label': self._status_label(release_letter),
        }

        if proved_possession:
            context.update({
                'matched_signature': matched_signature,
                'signatures': list(release_letter.signatures.filter(superseded=False)
                                   .order_by('document_kind', 'signed_at')),
                'has_superseded': release_letter.signatures.filter(superseded=True).exists(),
                # The fast-track shows here rather than on the PDF. Urgency is
                # declared *after* the chain completes, and by then the document
                # is locked — stamping it would mean altering a signed document,
                # which is the one thing the lock exists to prevent. So the
                # document's public face carries it instead, where it is visible
                # to exactly the people who would want to know: whoever is
                # holding the paper and checking whether it is good.
                'is_urgent': release_letter.is_urgent,
                'urgent_reason': release_letter.urgent_reason,
                'scan_outstanding': release_letter.urgent_scan_outstanding,
            })
        return render(request, self.template_name, context)

    @staticmethod
    def _status_label(release_letter):
        """Plain words, not internal state names — the reader is not a user."""
        return {
            'draft': 'Draft — not yet issued',
            'memo_generated': 'Issued, awaiting signature',
            'awaiting_signature': 'Awaiting signature',
            'awaiting_scan_upload': 'Signed, awaiting the registered copy',
            'approved': 'Approved',
            'released': 'Released',
            'voided': 'VOIDED — this document is no longer valid',
            'reissued': 'Superseded by a reissued document',
        }.get(release_letter.workflow_status, release_letter.workflow_status or 'Unknown')
