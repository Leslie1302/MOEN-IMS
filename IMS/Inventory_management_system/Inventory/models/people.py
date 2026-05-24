from django.db import models
import auto_prefetch


class MemberOfParliament(auto_prefetch.Model):
    """
    Member of Parliament -- the consignee for Cost Sharing and Streetlights
    releases. Lookup is by constituency (and falls back to region/district
    when the community-to-constituency mapping is incomplete).

    Replaces the previously-free-text `consultant`/`contractor` CharFields
    that allowed any value to be typed in.
    """

    title = models.CharField(
        max_length=20,
        default='Hon.',
        help_text="Title prefix, e.g. 'Hon.'",
    )
    name = models.CharField(max_length=200, db_index=True)
    constituency = models.CharField(max_length=200, db_index=True)
    region = models.CharField(max_length=100, db_index=True)
    district = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional. Some constituencies span districts.",
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    term_start = models.DateField(null=True, blank=True)
    term_end = models.DateField(
        null=True,
        blank=True,
        help_text="Set when this MP's term ends. Inactive MPs are not auto-resolved.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['region', 'constituency', 'name']
        verbose_name = 'Member of Parliament'
        verbose_name_plural = 'Members of Parliament'

    def __str__(self):
        return f"{self.title} {self.name} — {self.constituency}"

    @property
    def display_name(self):
        return f"{self.title} {self.name}"


class ProjectConsultant(auto_prefetch.Model):
    """
    A consultant firm or individual assigned to a region (and optionally
    one or more districts within it). For SHEP releases the consignee is
    the consultant whose region matches the community being served.

    Resolution priority on a release:
      1. Community.project_consultant FK (explicit override)
      2. ProjectConsultant where region == community.region
      3. ProjectConsultant where district == community.district
      4. Unresolved (with clear reason)

    Mirrors the MemberOfParliament pattern so SHEP and Cost Sharing /
    Streetlights resolution paths feel symmetrical.
    """

    name = models.CharField(max_length=200, db_index=True)
    firm = models.CharField(
        max_length=200,
        blank=True,
        help_text="Engineering firm or consultancy, if applicable.",
    )
    region = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Region this consultant covers. Used by the consignee resolver "
                  "to auto-bind SHEP communities in this region to the consultant.",
    )
    district = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Optional. Narrows binding to specific districts within the region.",
    )
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    # Optional FK to the Django user that represents the consultant's
    # day-to-day operator. Once linked, the user's dashboard scopes to this
    # consultancy and they receive in-system alerts for SHEP releases bound
    # to it. Nullable so existing consultant rows without a linked account
    # keep working as paper-only consignees.
    user = auto_prefetch.ForeignKey(
        'auth.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='project_consultancy',
        help_text="Domain account for this consultant. Receives in-system "
                  "alerts when SHEP releases are bound to this consultancy.",
    )

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['region', 'name']
        verbose_name = 'project consultant'
        verbose_name_plural = 'project consultants'

    def __str__(self):
        bits = [self.name]
        if self.firm and self.firm != self.name:
            bits.append(f"({self.firm})")
        if self.region:
            bits.append(f"— {self.region}")
        return ' '.join(bits)

    @property
    def display_name(self):
        return self.firm or self.name
