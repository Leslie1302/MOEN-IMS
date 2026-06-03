"""
Access rate models.

Two tables drive the formula-based national electricity-access rate that
the Ghana map shows:

  * ``MeterInstallation``   -- one row per batch of meters installed at a
    community on a given date, split by phase (1-phase vs 3-phase). Only
    rows that have been verified by a manager contribute to the rate.

  * ``AccessRateConfig``    -- admin-editable constants (persons per
    connection, baseline population already electrified, total national
    population). Updates land as new rows with a future ``effective_from``
    date, so historical reports remain reproducible against the config
    that was active at the time.

The formula computed downstream by ``Inventory.services.access_rate``:

    access_rate = (
        persons_per_connection * (meters_1ph_installed + meters_3ph_installed)
        + baseline_population_access
    ) / total_population
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

import auto_prefetch


class MeterInstallation(auto_prefetch.Model):
    """A batch of meters installed at a community on a single date.

    Multiple rows per community are expected over time; aggregation
    happens in :func:`Inventory.services.access_rate.compute_access_rate`.
    """

    PHASE_CHOICES = [
        ('1ph', '1-phase'),
        ('3ph', '3-phase'),
    ]

    community = auto_prefetch.ForeignKey(
        'Inventory.Community',
        on_delete=models.PROTECT,
        related_name='meter_installations',
        help_text='Community where the meters were installed. Drives the '
                  'region / district roll-ups on the access-rate map.',
    )
    project_site = auto_prefetch.ForeignKey(
        'Inventory.ProjectSite',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='meter_installations',
        help_text='Optional. Link the installation to a specific ProjectSite '
                  'when the community has more than one active site.',
    )
    phase_type = models.CharField(
        max_length=3, choices=PHASE_CHOICES, db_index=True,
        help_text="'1ph' for single-phase, '3ph' for three-phase meters. "
                  'Both feed the access rate at the same weight (each '
                  'meter ≈ one household).',
    )
    quantity = models.PositiveIntegerField(
        help_text='Number of meters of this phase type installed on this '
                  'report. Use one row per phase_type per day; do not mix.',
    )
    installation_date = models.DateField(
        db_index=True,
        help_text='Date the meters were energised at site. Used for '
                  'as-of access-rate queries.',
    )

    reported_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='meter_reports',
        help_text='Field officer / site supervisor who logged the install.',
    )
    verified_by = auto_prefetch.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='meter_verifications',
        help_text='Manager who confirmed the install. Only verified rows '
                  'contribute to the published access rate.',
    )
    verified_at = models.DateTimeField(
        null=True, blank=True,
        help_text='Set automatically when verified_by is filled in by the '
                  'verification view.',
    )

    evidence_photo = models.ImageField(
        upload_to='meter_evidence/',
        null=True, blank=True,
        help_text='Optional photo of the installed meter(s). Helps the '
                  'verifier sign off without a site visit.',
    )
    notes = models.TextField(
        blank=True,
        help_text='Optional context (which feeder, which transformer, '
                  'cluster name, anything the verifier should know).',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-installation_date', '-created_at']
        indexes = [
            models.Index(fields=['phase_type', 'installation_date']),
            models.Index(fields=['community', 'phase_type']),
            models.Index(fields=['verified_at']),
        ]
        verbose_name = 'meter installation'
        verbose_name_plural = 'meter installations'

    def __str__(self):
        return (
            f"{self.quantity} × {self.get_phase_type_display()} "
            f"@ {self.community} on {self.installation_date}"
        )

    @property
    def is_verified(self) -> bool:
        """Convenience flag the calculator service and templates read.

        Returns ``True`` only when *both* ``verified_by`` and ``verified_at``
        are set, so a half-completed verification doesn't accidentally
        leak into the published numerator.
        """
        return self.verified_by_id is not None and self.verified_at is not None

    def mark_verified(self, by_user, when=None) -> None:
        """Stamp ``verified_by`` and ``verified_at`` together.

        Centralised here so the API view, admin action, and any future
        scheduled-verification job all set the same fields. Callers must
        still save the instance.
        """
        self.verified_by = by_user
        self.verified_at = when or timezone.now()


class AccessRateConfig(auto_prefetch.Model):
    """The three constants the access-rate formula multiplies / divides by.

    Versioned by ``effective_from`` -- new rows replace older ones for
    today's calculations, while historical-date queries pick up the row
    that was in effect on the as-of date. Never mutate an existing row in
    place; insert a new one so the audit trail stays intact.
    """

    persons_per_connection = models.PositiveIntegerField(
        default=7,
        help_text='People served per newly-installed meter. Default 7 = '
                  'household-size proxy used when actual per-meter data '
                  'is unavailable. Refresh when survey numbers improve.',
    )
    baseline_population_access = models.PositiveBigIntegerField(
        default=27_980_911,
        help_text='Population already electrified before the programme. '
                  'Becomes the additive constant in the access-rate '
                  "numerator. Source: cite in 'notes' when changing.",
    )
    total_population = models.PositiveBigIntegerField(
        default=31_493_526,
        help_text='Total national population (denominator). Refresh from '
                  'the latest census when published.',
    )

    effective_from = models.DateField(
        db_index=True,
        help_text='First date this config applies. The current config is '
                  "the row with the latest effective_from <= today's date.",
    )
    notes = models.TextField(
        blank=True,
        help_text='Why these values? Cite the source (e.g. "GSS 2021 '
                  'census, Ministry briefing of 12 May 2026"). Shown on '
                  'the map info panel so reviewers can audit the numbers.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = auto_prefetch.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='access_rate_configs',
    )

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-effective_from']
        verbose_name = 'access rate config'
        verbose_name_plural = 'access rate configs'

    def __str__(self):
        return (
            f"AccessRateConfig(persons={self.persons_per_connection}, "
            f"baseline={self.baseline_population_access:,}, "
            f"total={self.total_population:,}, "
            f"from={self.effective_from})"
        )

    @classmethod
    def current(cls, as_of=None):
        """Return the row in effect on ``as_of`` (default: today).

        Returns ``None`` only if the table is empty -- callers should
        treat that as a configuration error rather than fall back to
        hardcoded defaults silently.
        """
        when = as_of or timezone.localdate()
        return (
            cls.objects.filter(effective_from__lte=when)
            .order_by('-effective_from')
            .first()
        )
