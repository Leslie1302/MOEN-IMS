import secrets

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
import auto_prefetch

DOCUMENT_KIND_CHOICES = [
    ('memo', 'Approval memo'),
    ('letter', 'Release letter'),
]


def _make_token():
    """A short, human-transcribable verification token: XXXX-XXXX-XXXX.

    Printed in the signature stamp and typed into the public verify page, so the
    alphabet excludes characters that are misread off paper (0/O, 1/I/L, 5/S,
    8/B). ~34 bits of entropy — ample, since the token identifies rather than
    authorises, and the verify endpoint is rate-limited.
    """
    alphabet = 'ACDEFGHJKMNPQRTUVWXY2346789'
    return '-'.join(''.join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


class SigningStep(auto_prefetch.Model):
    """
    One position in a document's approval chain.

    The chain lives in data, not code, because the mapping between an *office*
    and the *person* filling it changes without warning — an acting appointment
    may last a fortnight and must not require a deploy. Three separable pieces:

      * `SigningStep`  — which office signs this document, in what order
                         (changes rarely; a policy decision)
      * `Signatory`    — the name and title that print on the page
                         (changes when the postholder changes)
      * `SigningStep.user` — whose login may actually sign
                         (changes with each acting appointment)

    An acting appointment is therefore two field edits in admin.

    In practice: memo → Ag. Director, Power (order 1); letter → Chief Director
    (order 1). More signatories can be inserted without touching code.
    """

    document_kind = models.CharField(max_length=10, choices=DOCUMENT_KIND_CHOICES, db_index=True)
    order = models.PositiveSmallIntegerField(
        default=1, help_text="Signing position, lowest first. Steps are enforced in order.")
    signatory = auto_prefetch.ForeignKey(
        'Inventory.Signatory', on_delete=models.CASCADE, related_name='signing_steps',
        help_text="Whose name and title print on the signature line.")
    user = auto_prefetch.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='signing_steps',
        help_text="The login allowed to sign this step. Change this when someone acts "
                  "in the office. Leave blank for a print-only signatory who never "
                  "signs in the system.")
    required = models.BooleanField(
        default=True, help_text="A required step must be signed before the chain completes.")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['document_kind', 'order']
        verbose_name = 'signing step'
        verbose_name_plural = 'signing steps'
        constraints = [
            models.UniqueConstraint(
                fields=['document_kind', 'order'],
                condition=models.Q(active=True),
                name='unique_active_step_order_per_document'),
        ]

    def __str__(self):
        return f"{self.get_document_kind_display()} #{self.order}: {self.signatory}"

    @classmethod
    def chain_for(cls, document_kind):
        return list(cls.objects.filter(document_kind=document_kind, active=True)
                    .select_related('signatory', 'user').order_by('order'))


class DocumentSignature(auto_prefetch.Model):
    """
    A signature applied to a release document — the audit record of one signing.

    Name and title are **denormalised deliberately**. Titles change, acting
    appointments end, and Signatory rows get edited; the record has to say what
    was printed on the document at the moment it was signed, not what the
    config says today.

    `signature_image` is a PNG of a signature drawn live in the browser. It is
    never a stored, reusable asset: there is no signature file on a profile to
    lift, and a copied image is inert because it carries no valid token. It must
    only ever be served inside the signed document — never in a list view, an
    email body, or the public verify page.
    """

    release_letter = auto_prefetch.ForeignKey(
        'Inventory.ReleaseLetter', on_delete=models.CASCADE, related_name='signatures')
    document_kind = models.CharField(max_length=10, choices=DOCUMENT_KIND_CHOICES, db_index=True)
    step = auto_prefetch.ForeignKey(
        SigningStep, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='signatures')

    signed_by = auto_prefetch.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='document_signatures')

    # What was printed, captured at signing time.
    signatory_name = models.CharField(max_length=200)
    signatory_title = models.CharField(
        max_length=200, blank=True,
        help_text="The office signed in, e.g. 'Ag. Chief Director'.")
    signatory_designation = models.CharField(
        max_length=200, blank=True,
        help_text="Substantive post, e.g. 'Director, Finance'. Differs from the office "
                  "when someone is acting — the record must show both.")
    signs_for = models.CharField(max_length=200, blank=True)

    signature_image = models.ImageField(
        upload_to='signatures/%Y/%m/', blank=True, null=True,
        help_text="PNG of the signature drawn at signing time. Access-controlled.")

    document_version = models.PositiveIntegerField(
        default=1, help_text="Document version signed, so a signature ties to exact content.")
    verification_token = models.CharField(max_length=20, unique=True, db_index=True, blank=True)

    signed_at = models.DateTimeField(default=timezone.now, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)

    superseded = models.BooleanField(
        default=False, db_index=True,
        help_text="Set when the document is reissued. The signature stays on record but "
                  "no longer applies to the current document.")

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['document_kind', 'signed_at']
        verbose_name = 'document signature'
        verbose_name_plural = 'document signatures'

    def __str__(self):
        return f"{self.signatory_name} — {self.get_document_kind_display()} ({self.verification_token})"

    def save(self, *args, **kwargs):
        if not self.verification_token:
            # Collisions are vanishingly unlikely but the field is unique, so
            # retry rather than surface an IntegrityError to a signing officer.
            for _ in range(5):
                token = _make_token()
                if not DocumentSignature.objects.filter(verification_token=token).exists():
                    self.verification_token = token
                    break
        super().save(*args, **kwargs)

    @property
    def stamp_lines(self):
        """The authority stamp, as printed beneath the drawn signature.

        This is what carries evidential weight — who signed, in what office, on
        what substantive authority, over which document version, when, and a
        token any third party can check. The drawing is the human mark; this is
        the evidence.
        """
        lines = [self.signatory_name.upper()]
        if self.signatory_title:
            lines.append(self.signatory_title)
        if self.signatory_designation and self.signatory_designation != self.signatory_title:
            lines.append(f"(substantive: {self.signatory_designation})")
        if self.signs_for:
            lines.append(f"FOR: {self.signs_for.upper()}")
        lines.append(f"Signed {self.signed_at.strftime('%d %b %Y, %H:%M')} GMT")
        code = self.release_letter.code or self.release_letter.request_code
        lines.append(f"MOEN-IMS · {code} · v{self.document_version}")
        lines.append(f"Verify: {self.verification_token}")
        return lines
