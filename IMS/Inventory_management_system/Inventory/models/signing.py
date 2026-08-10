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

    document_kind = models.CharField(
        max_length=10, choices=DOCUMENT_KIND_CHOICES, db_index=True,
        help_text="Which document this step signs.")
    order = models.PositiveSmallIntegerField(
        default=1,
        help_text="Position in the release's signing sequence — ACROSS both documents, "
                  "not within one. Typically 1 = Ag. Director Power signs the memo, "
                  "2 = Chief Director signs the letter.")
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
        ordering = ['order', 'document_kind']
        verbose_name = 'signing step'
        verbose_name_plural = 'signing steps'
        constraints = [
            # One sequence for the whole release, so two steps cannot share a
            # position. Previously scoped to (document_kind, order), which
            # allowed a memo step 1 and a letter step 1 — two independent
            # chains with no defined order between them.
            models.UniqueConstraint(
                fields=['order'],
                condition=models.Q(active=True),
                name='unique_active_step_order'),
        ]

    def __str__(self):
        return f"#{self.order} {self.get_document_kind_display()}: {self.signatory}"

    @classmethod
    def chain(cls):
        """The whole release signing sequence, in order, across both documents.

        The Ag. Director signs the memo, then the Chief Director signs the
        letter — and the signed memo is the authority for the letter, so the
        order between documents is meaningful rather than incidental.
        """
        return list(cls.objects.filter(active=True)
                    .select_related('signatory', 'user').order_by('order'))

    @classmethod
    def chain_for(cls, document_kind):
        """Steps that sign one document, still in release order."""
        return [s for s in cls.chain() if s.document_kind == document_kind]


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


class DiscussionRequest(auto_prefetch.Model):
    """
    A signatory asking the preparing officer to talk about a release.

    Deliberately **not** a rejection. A signature chain with a reject state
    invites officers to use it for "change the third line", and the release then
    carries a permanent black mark for a typo. What a signatory actually wants at
    that point is a conversation, so that is what this records: a note, an email
    from the signatory's own mailbox, an in-app notification, and a row on file.

    The workflow does not move. If the conversation concludes that the document
    must change, the officer voids and reissues — which is the honest path,
    because it discards the signatures rather than editing underneath them.
    """

    release_letter = auto_prefetch.ForeignKey(
        'Inventory.ReleaseLetter', on_delete=models.CASCADE, related_name='discussion_requests')
    document_kind = models.CharField(
        max_length=10, choices=DOCUMENT_KIND_CHOICES, blank=True,
        help_text="The document prompting the call, if the signatory named one.")

    raised_by = auto_prefetch.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='discussion_requests_raised')
    officer = auto_prefetch.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='discussion_requests_received',
        help_text="The officer who prepared the release, and who is being called.")

    # Two tiers, because there are two different things a signatory means.
    #
    # 'routine' is the original: a conversation, no state change, no black mark.
    # 'correction' is for an actual error found in a document already signed.
    # Before it existed the only route was void-and-reissue, so corrections
    # happened by phone and the record showed a clean release that had quietly
    # been rebuilt. An off-record correction is worse than a recorded one.
    KIND_CHOICES = [
        ('routine', 'Routine discussion — nothing changes'),
        ('correction', 'Correction required — returns to the officer'),
    ]
    kind = models.CharField(
        max_length=12, choices=KIND_CHOICES, default='routine', db_index=True,
        help_text="A routine call moves nothing. A correction supersedes the "
                  "signatures on the named document and every later step, and "
                  "returns the release to the preparing officer.")
    superseded_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="How many signatures this correction superseded. Recorded so the "
                  "release history shows what a correction actually cost.")

    note = models.TextField(help_text="What the signatory wants to discuss.")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Recorded rather than raised: the note and the in-app notification are the
    # record, and a Graph failure must not lose them. The officer sees on the
    # release that a call was raised and whether the email actually left.
    email_sent = models.BooleanField(default=False)
    email_error = models.CharField(max_length=400, blank=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-created_at']
        verbose_name = 'discussion request'
        verbose_name_plural = 'discussion requests'

    def __str__(self):
        who = self.raised_by.get_full_name() if self.raised_by else 'A signatory'
        return f"{who} called about {self.release_letter}"
