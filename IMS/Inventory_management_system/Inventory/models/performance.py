"""
Performance / KPI configuration and snapshot models.

This is the persistence layer for the rebuilt, single-source-of-truth KPI
system. Targets live in the database (tunable in admin), and monthly grades are
snapshotted for history and trends. The scoring logic lives in
``Inventory/services/performance.py``.
"""
from django.db import models
from django.contrib.auth.models import User


# Canonical roles that receive an individual grade. Transporters are graded only
# when their Transporter record is linked to a login user.
ROLE_SCHEDULE = "Schedule Officers"
ROLE_STORE = "Store Officers"
ROLE_CONSULTANT = "Consultants"
ROLE_MANAGEMENT = "Management"
ROLE_TRANSPORTER = "Transporters"

GRADABLE_ROLES = [
    ROLE_SCHEDULE,
    ROLE_STORE,
    ROLE_CONSULTANT,
    ROLE_MANAGEMENT,
    ROLE_TRANSPORTER,
]

# Letter-grade bands keyed off the 0-100 overall score (descending).
GRADE_BANDS = [
    (90, "A+", "success"),
    (85, "A", "success"),
    (80, "B+", "info"),
    (75, "B", "info"),
    (70, "C+", "warning"),
    (65, "C", "warning"),
    (60, "D", "danger"),
    (0, "F", "danger"),
]


class RolePerformanceTarget(models.Model):
    """Per-role appraisal targets. One row per gradable role; admin-tunable."""

    role = models.CharField(
        max_length=50, unique=True,
        help_text="Group name this target applies to (e.g. 'Store Officers').",
    )
    sla_days = models.PositiveIntegerField(
        default=3,
        help_text="Max days for this role's stage to count as on-time.",
    )
    throughput_target = models.PositiveIntegerField(
        default=20,
        help_text="Completed items per 30 days that equals 'meeting expectation' (100%).",
    )
    quality_target_pct = models.PositiveIntegerField(
        default=95,
        help_text="Quality rate (%) that equals full marks (e.g. % deliveries with no damage).",
    )
    stage_label = models.CharField(
        max_length=120, blank=True,
        help_text="Human description of the stage measured (for dashboards).",
    )
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Role performance target"
        verbose_name_plural = "Role performance targets"
        ordering = ["role"]

    def __str__(self):
        return f"{self.role}: SLA {self.sla_days}d, target {self.throughput_target}/mo"


class PerformanceConfig(models.Model):
    """Global appraisal weights and rules. Singleton (use load())."""

    weight_timeliness = models.PositiveIntegerField(default=30)
    weight_quality = models.PositiveIntegerField(default=30)
    weight_throughput = models.PositiveIntegerField(default=20)
    weight_responsiveness = models.PositiveIntegerField(default=20)
    min_items_for_grade = models.PositiveIntegerField(
        default=5,
        help_text="Below this many completed items in the period, show "
                  "'Insufficient data' instead of a grade.",
    )

    class Meta:
        verbose_name = "Performance configuration"
        verbose_name_plural = "Performance configuration"

    def __str__(self):
        return "Performance configuration"

    @classmethod
    def load(cls):
        """Return the single config row, creating defaults if absent."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def weights(self):
        return {
            "timeliness": self.weight_timeliness,
            "quality": self.weight_quality,
            "throughput": self.weight_throughput,
            "responsiveness": self.weight_responsiveness,
        }


class PerformanceSnapshot(models.Model):
    """A user's computed grade for one calendar month (appraisal history)."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="performance_snapshots"
    )
    role = models.CharField(max_length=50)
    period_year = models.PositiveIntegerField()
    period_month = models.PositiveIntegerField()

    timeliness_score = models.FloatField(null=True, blank=True)
    quality_score = models.FloatField(null=True, blank=True)
    throughput_score = models.FloatField(null=True, blank=True)
    responsiveness_score = models.FloatField(null=True, blank=True)
    overall_score = models.FloatField(null=True, blank=True)
    grade = models.CharField(max_length=4, blank=True)

    completed_count = models.PositiveIntegerField(default=0)
    on_time_count = models.PositiveIntegerField(default=0)
    insufficient_data = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Performance snapshot"
        verbose_name_plural = "Performance snapshots"
        unique_together = ("user", "period_year", "period_month")
        ordering = ["-period_year", "-period_month", "-overall_score"]
        indexes = [
            models.Index(fields=["period_year", "period_month"]),
        ]

    def __str__(self):
        return f"{self.user.username} {self.period_year}-{self.period_month:02d}: {self.grade or 'N/A'}"
