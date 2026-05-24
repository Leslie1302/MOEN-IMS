from django.db import models
import auto_prefetch


class Signatory(auto_prefetch.Model):
    """
    Configurable signing officer used on generated memos and release letters.

    Each Signatory has a role (e.g. "Ag. Director, Power"), a name
    (e.g. "Ing. Sulemana Abubakari"), and flags indicating which document
    types they sign by default. When leadership changes, the data row is
    updated -- no code deploy required.

    The PDF generator queries Signatory at render time, so updates take
    effect immediately on the next document generation.
    """

    ROLE_RELEASE_MEMO = 'release_memo'
    ROLE_RELEASE_LETTER = 'release_letter'
    ROLE_PAYMENT_MEMO = 'payment_memo'

    name = models.CharField(
        max_length=200,
        help_text="Full name as it should appear on the signature line (e.g. 'Ing. Sulemana Abubakari').",
    )
    title = models.CharField(
        max_length=200,
        help_text="Official title as it should appear under the signature line (e.g. 'Ag. Director, Power').",
    )

    # Which document types this signatory is the default for. Multiple
    # signatories can share a role; the most recently updated active one
    # wins at render time.
    is_default_for_release_memo = models.BooleanField(
        default=False,
        help_text="Signs the Director-Power approval memo (Phase F).",
    )
    is_default_for_release_letter = models.BooleanField(
        default=False,
        help_text="Signs the release letter to MMU (Phase F). Typically Chief Director 'FOR: HON. MINISTER'.",
    )
    is_default_for_payment_memo = models.BooleanField(
        default=False,
        help_text="Signs the payment-approval memo (Phase I).",
    )

    # For release-letter "FOR: HON. MINISTER" line.
    signs_for = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional. Appears under the title as 'FOR: <value>'. Used on the release letter where the Chief Director signs on behalf of the Hon. Minister.",
    )

    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-updated_at']
        verbose_name = 'signatory'
        verbose_name_plural = 'signatories'

    def __str__(self):
        return f"{self.name} — {self.title}"

    @classmethod
    def for_release_memo(cls):
        """Return the active signatory for release-side approval memos."""
        return cls.objects.filter(
            active=True, is_default_for_release_memo=True,
        ).order_by('-updated_at').first()

    @classmethod
    def for_release_letter(cls):
        """Return the active signatory for release letters to MMU."""
        return cls.objects.filter(
            active=True, is_default_for_release_letter=True,
        ).order_by('-updated_at').first()

    @classmethod
    def for_payment_memo(cls):
        """Return the active signatory for payment-approval memos (Phase I)."""
        return cls.objects.filter(
            active=True, is_default_for_payment_memo=True,
        ).order_by('-updated_at').first()
