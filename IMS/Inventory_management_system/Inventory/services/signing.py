"""
Applying signatures to release documents.

A signature is captured as a drawing made live in the browser and stored with a
generated **authority stamp** — name, office signed in, substantive designation,
timestamp, document version, and a token any third party can verify. The drawing
is the human mark; the stamp is the evidence. Nothing here depends on the
drawing being legally sufficient on its own, because the digital route never
grants physical release by itself (see the plan, §4b).

Two invariants this module exists to protect:

  * **Order.** A step cannot be signed while an earlier required step is
    outstanding. The Ag. Director signs the memo before it reaches the Chief
    Director, and the system should enforce that rather than trust it.
  * **Immutability.** Once a document carries a signature it is locked. A
    regenerated signed document would reproduce a signature over content the
    signatory never saw, which is forgery-adjacent. Changing a signed document
    means void and reissue.
"""

import base64
import binascii
import logging
import re

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_SIGNATURE_BYTES = 2 * 1024 * 1024
_DATA_URI = re.compile(r'^data:image/png;base64,(?P<data>[A-Za-z0-9+/=\s]+)$')


class SigningError(RuntimeError):
    """Anything that stops a signature being applied, phrased for the signer."""


def decode_signature_png(data_uri):
    """Validate and decode the canvas data-URI into PNG bytes.

    Only `data:image/png;base64,...` is accepted — the drawing comes from our
    own canvas, so anything else is either a bug or someone posting a hand-built
    payload, and neither should reach storage.
    """
    if not data_uri:
        raise SigningError("No signature was drawn.")

    match = _DATA_URI.match(data_uri.strip())
    if not match:
        raise SigningError("The signature was not in the expected format. Draw it again.")

    try:
        raw = base64.b64decode(match.group('data'), validate=False)
    except (binascii.Error, ValueError):
        raise SigningError("The signature image could not be read. Draw it again.")

    if len(raw) > MAX_SIGNATURE_BYTES:
        raise SigningError("The signature image is too large.")
    if not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        raise SigningError("The signature was not a valid PNG.")
    # A blank canvas still produces a valid PNG; a few hundred bytes means the
    # signer submitted without drawing anything.
    if len(raw) < 200:
        raise SigningError("The signature looks blank. Draw your signature, then confirm.")
    return raw


def steps_awaiting(user, document_kind=None):
    """Active signing steps this user is allowed to sign."""
    from Inventory.models import SigningStep

    qs = SigningStep.objects.filter(active=True, user=user).select_related('signatory')
    if document_kind:
        qs = qs.filter(document_kind=document_kind)
    return list(qs.order_by('document_kind', 'order'))


def can_sign(user, release_letter, document_kind):
    """→ (allowed, step_or_None, reason).

    Reasons are written for the person being refused, since every one of them
    is a plausible thing to hit: wrong person, out of turn, already signed,
    document not generated, or already locked.
    """
    if not user or not user.is_authenticated:
        return False, None, "You must be signed in."

    # Refuse before anything is recorded. Signing depends on re-rendering the
    # document, so with no renderer the signature could never reach the page —
    # and discovering that after the fact leaves a locked, unsigned document.
    from .document_render import weasyprint_status
    renderer_ok, renderer_detail = weasyprint_status()
    if not renderer_ok:
        return False, None, (
            "Signing is unavailable because this server cannot produce PDFs, so the "
            f"signature could not be placed on the document. {renderer_detail}")

    pdf = getattr(release_letter, f'{document_kind}_pdf', None)
    if not pdf:
        return False, None, (
            f"The {document_kind} has not been generated yet, so there is nothing to sign.")

    if getattr(release_letter, f'{document_kind}_locked', False):
        return False, None, (
            f"This {document_kind} is complete and locked. To change it, void and reissue "
            "the release.")

    if release_letter.signing_complete(document_kind):
        return False, None, f"The {document_kind} has already been fully signed."

    next_step = release_letter.next_signing_step(document_kind)
    if next_step is None:
        # The release's next step belongs to the OTHER document. This is the
        # order that matters: the signed memo is the authority for the letter,
        # so the letter cannot be signed first.
        pending = release_letter.next_signing_step()
        if pending is None:
            return False, None, f"The {document_kind} has already been fully signed."
        holder = pending.signatory.title if pending.signatory else 'another officer'
        return False, None, (
            f"The {pending.get_document_kind_display().lower()} must be signed first — "
            f"it is with {holder}.")

    if next_step.user_id != user.pk:
        holder = (next_step.signatory.title if next_step.signatory else 'another officer')
        return False, next_step, (
            f"This {document_kind} is awaiting {holder}. It will reach you once they have signed.")

    return True, next_step, ""


@transaction.atomic
def apply_signature(release_letter, user, document_kind, signature_data_uri,
                    ip_address=None, user_agent=''):
    """Record a signature, re-mint the PDF, and lock the document when complete.

    Returns the `DocumentSignature`. Raises `SigningError` if the signer is not
    the one due, the document is locked, or the drawing is unusable.
    """
    from Inventory.models import DocumentSignature, Profile

    allowed, step, reason = can_sign(user, release_letter, document_kind)
    if not allowed:
        raise SigningError(reason)

    png = decode_signature_png(signature_data_uri)

    signatory = step.signatory
    # Read the profile from the database rather than through `user.profile`.
    #
    # Django caches the reverse one-to-one on the User instance the moment
    # anything assigns `profile.user = <that instance>` — which the profile
    # creation signal does at sign-up, before any designation has been set. Any
    # later edit to the designation updates a different Python object, so the
    # cached one stays blank and the signature is recorded with no substantive
    # post at all.
    #
    # The designation is part of a permanent audit record and is the field that
    # tells an acting appointment apart from a substantive one. It has to be
    # what the database says at the moment of signing, not whatever happened to
    # be attached to the request's user object.
    profile = Profile.objects.filter(user=user).first()

    signature = DocumentSignature(
        release_letter=release_letter,
        document_kind=document_kind,
        step=step,
        signed_by=user,
        # Denormalised on purpose: titles change and acting appointments end,
        # but the record must say what was printed at the time.
        signatory_name=signatory.name if signatory else (user.get_full_name() or user.username),
        signatory_title=signatory.title if signatory else '',
        signatory_designation=(getattr(profile, 'designation', '') or ''),
        signs_for=(signatory.signs_for if signatory else ''),
        document_version=getattr(release_letter, f'{document_kind}_version', 1) or 1,
        signed_at=timezone.now(),
        ip_address=ip_address,
        user_agent=(user_agent or '')[:400],
    )
    signature.signature_image.save(
        f"sig_{release_letter.pk}_{document_kind}_{signature.signed_at:%Y%m%d%H%M%S}.png",
        ContentFile(png), save=False)
    signature.save()

    logger.info("ReleaseLetter %s: %s signed by %s (token %s)",
                release_letter.pk, document_kind, user, signature.verification_token)

    # Re-mint the PDF so the stored document carries the signature.
    #
    # This must NOT be best-effort. If it fails and we carry on, the chain
    # completes, the document locks, and the officer is left holding a locked
    # release whose PDF shows no signature — and the lock blocks the only button
    # that could fix it. Raising rolls the whole signing back (this function is
    # atomic), so the officer can retry once the renderer is available.
    try:
        rebuild_signed_pdf(release_letter, document_kind)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Rolling back signature on ReleaseLetter %s (%s): "
                         "the PDF could not be re-minted: %s",
                         release_letter.pk, document_kind, exc)
        raise SigningError(
            "Your signature was not applied, because the signed PDF could not be "
            f"produced: {exc} Nothing has been changed — try again once this is "
            "resolved.") from exc

    if release_letter.signing_complete(document_kind):
        setattr(release_letter, f'{document_kind}_locked', True)
        release_letter.save(update_fields=[f'{document_kind}_locked'])
        logger.info("ReleaseLetter %s: %s chain complete, document locked.",
                    release_letter.pk, document_kind)

    # The whole release is signed: MMU may now start preparing. This is the
    # default route on every release and grants nothing beyond picking and
    # staging — materials still leave only on the verified wet-signed scan,
    # unless management separately declares the release urgent.
    if release_letter.signing_complete():
        from .urgency import mark_advance_notice
        mark_advance_notice(release_letter)

    return signature


def rebuild_signed_pdf(release_letter, document_kind):
    """Re-render the stored PDF so it carries the signatures applied so far.

    Safe to run on a locked document. The lock exists to stop the *content*
    changing under a signature; re-rendering reproduces the same content and
    adds the signature block that should already have been there. This is the
    repair path for a document signed while the renderer was unavailable.

    Raises on failure — the caller decides whether that aborts a signing
    (it should) or is merely reported (a manual rebuild).
    """
    from .document_render import render_document_pdf

    content = render_document_pdf(release_letter, document_kind)
    field = getattr(release_letter, f'{document_kind}_pdf')
    field.save(content.name, content, save=False)
    release_letter.save(update_fields=[f'{document_kind}_pdf'])
    logger.info("ReleaseLetter %s: %s PDF rebuilt with %s signature(s).",
                release_letter.pk, document_kind,
                release_letter.signatures_for(document_kind).count())
    return True


def signed_pdf_is_stale(release_letter, document_kind):
    """True when a document has signatures but its PDF predates the last one.

    Catches the state this repair path exists for: signed while the renderer was
    down, so the stored PDF shows no signature even though the record says it is
    signed and locked.
    """
    signatures = release_letter.signatures_for(document_kind)
    if not signatures.exists():
        return False
    field = getattr(release_letter, f'{document_kind}_pdf', None)
    if not field:
        return True
    try:
        from django.core.files.storage import default_storage
        minted = default_storage.get_modified_time(field.name)
    except Exception:  # noqa: BLE001 — storage backends vary; don't guess
        return False
    return minted < signatures.last().signed_at


def supersede_signatures(release_letter, document_kind=None):
    """Mark signatures superseded and unlock, for void-and-reissue.

    Signatures are never deleted — the record that someone signed version 2
    survives the issue of version 3.
    """
    qs = release_letter.signatures.filter(superseded=False)
    if document_kind:
        qs = qs.filter(document_kind=document_kind)
    count = qs.update(superseded=True)

    kinds = [document_kind] if document_kind else ['memo', 'letter']
    for kind in kinds:
        setattr(release_letter, f'{kind}_locked', False)
    release_letter.save(update_fields=[f'{k}_locked' for k in kinds])

    logger.info("ReleaseLetter %s: %s signature(s) superseded, documents unlocked.",
                release_letter.pk, count)
    return count
