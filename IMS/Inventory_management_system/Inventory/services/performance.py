"""
Performance / KPI scoring service — the single source of truth.

Every user is scored on the same four dimensions (each 0-100), measured against
role-appropriate targets stored in the database (RolePerformanceTarget):

    Timeliness     - % of completed work that met the stage SLA
    Quality        - role-specific quality rate (e.g. % deliveries undamaged)
    Throughput     - completed items vs the role's monthly target
    Responsiveness - % of the open queue that is not overdue

Dimensions a role cannot be measured on return None and are dropped from the
weighting (weights renormalise over the available dimensions). Below the
minimum-data threshold a user shows "Insufficient data" rather than a grade.

All field references are validated against the live models. Only timestamps that
actually exist are used: MaterialOrder.date_requested / processed_at / updated_at,
MaterialTransport.date_dispatched / date_delivered, SiteReceipt.received_date.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from django.db.models import F, ExpressionWrapper, DurationField, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

from Inventory.models import (
    MaterialOrder, MaterialTransport, SiteReceipt, Transporter,
    RolePerformanceTarget, PerformanceConfig, GRADE_BANDS,
)
from Inventory.models.performance import (
    ROLE_SCHEDULE, ROLE_STORE, ROLE_CONSULTANT, ROLE_MANAGEMENT, ROLE_TRANSPORTER,
    GRADABLE_ROLES,
)

# Order statuses considered "still open" (in someone's queue).
_OPEN_STATUSES = ["Draft", "Pending", "Seen", "Approved", "In Progress",
                  "Partially Fulfilled", "Ready for Pickup"]
_TERMINAL_BAD = ["Rejected", "Cancelled"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clamp(value):
    return max(0.0, min(100.0, float(value)))


def _rate(numerator, denominator):
    """Return percentage or None if there's nothing to measure."""
    if not denominator:
        return None
    return _clamp(numerator / denominator * 100.0)


def grade_from_score(score):
    """Map a 0-100 score to (letter, bootstrap colour)."""
    if score is None:
        return ("N/A", "secondary")
    for threshold, letter, colour in GRADE_BANDS:
        if score >= threshold:
            return (letter, colour)
    return ("F", "danger")


def get_targets():
    """role -> RolePerformanceTarget (DB-backed, admin-tunable)."""
    return {t.role: t for t in RolePerformanceTarget.objects.filter(active=True)}


def primary_role(user):
    """The single gradable role used for this user, in priority order."""
    user_groups = set(user.groups.values_list("name", flat=True))
    for role in GRADABLE_ROLES:
        if role == ROLE_TRANSPORTER:
            if Transporter.objects.filter(user=user).exists():
                return role
        elif role in user_groups:
            return role
    return None


def _on_time_count(qs, start_field, end_field, sla_days):
    """Count rows in qs whose (end - start) <= sla_days. None-safe."""
    annotated = qs.filter(**{f"{start_field}__isnull": False,
                             f"{end_field}__isnull": False}).annotate(
        _delay=ExpressionWrapper(F(end_field) - F(start_field), output_field=DurationField())
    )
    measurable = annotated.count()
    on_time = annotated.filter(_delay__lte=timedelta(days=sla_days)).count()
    return on_time, measurable


# ---------------------------------------------------------------------------
# Per-role computation. Each returns a dict of raw dimension stats.
# ---------------------------------------------------------------------------
def _schedule_officer(user, since, until, target):
    base = MaterialOrder.objects.filter(user=user)
    completed = base.filter(processed_at__gte=since, processed_at__lt=until)
    completed_count = completed.count()
    on_time, measurable = _on_time_count(completed, "date_requested", "processed_at", target.sla_days)

    created = base.filter(date_requested__gte=since, date_requested__lt=until)
    total_created = created.count()
    bad = created.filter(status__in=_TERMINAL_BAD).count()

    open_qs = base.filter(status__in=_OPEN_STATUSES)
    overdue = open_qs.filter(date_requested__lt=until - timedelta(days=target.sla_days)).count()
    open_count = open_qs.count()

    return _assemble(completed_count, on_time, measurable, total_created, bad,
                     open_count, overdue, target)


def _store_officer(user, since, until, target):
    base = MaterialOrder.objects.filter(processed_by=user)
    completed = base.filter(processed_at__gte=since, processed_at__lt=until)
    completed_count = completed.count()
    on_time, measurable = _on_time_count(completed, "date_requested", "processed_at", target.sla_days)

    total_processed = completed_count
    bad = completed.filter(status__in=_TERMINAL_BAD).count()

    open_qs = MaterialOrder.objects.filter(
        Q(assigned_to=user) | Q(processed_by=user), status__in=_OPEN_STATUSES
    )
    overdue = open_qs.filter(date_requested__lt=until - timedelta(days=target.sla_days)).count()
    open_count = open_qs.count()

    return _assemble(completed_count, on_time, measurable, total_processed, bad,
                     open_count, overdue, target)


def _consultant(user, since, until, target):
    base = SiteReceipt.objects.filter(received_by=user)
    completed = base.filter(received_date__gte=since, received_date__lt=until)
    completed_count = completed.count()
    on_time, measurable = _on_time_count(
        completed, "material_transport__date_delivered", "received_date", target.sla_days
    )
    good = completed.filter(condition="Good").count()
    quality = _rate(good, completed_count)
    # Responsiveness has no clean per-consultant queue -> excluded.
    return _build_result(completed_count, _rate(on_time, measurable), quality,
                         completed_count, target, responsiveness=None,
                         on_time=on_time, measurable=measurable)


def _management(user, since, until, target):
    base = MaterialOrder.objects.filter(last_updated_by=user)
    completed = base.filter(status__in=["Approved", "Completed"],
                            updated_at__gte=since, updated_at__lt=until)
    completed_count = completed.count()
    on_time, measurable = _on_time_count(completed, "date_requested", "updated_at", target.sla_days)
    bad = base.filter(status="Rejected").count()
    quality = _rate(completed_count, completed_count + bad)

    # Org-level approval backlog (management collectively owns approvals).
    pending = MaterialOrder.objects.filter(status="Pending")
    overdue = pending.filter(date_requested__lt=until - timedelta(days=target.sla_days)).count()
    pending_count = pending.count()
    responsiveness = _rate(pending_count - overdue, pending_count)

    return _build_result(completed_count, _rate(on_time, measurable), quality,
                         completed_count, target, responsiveness=responsiveness,
                         on_time=on_time, measurable=measurable)


def _transporter(user, since, until, target):
    transports = MaterialTransport.objects.filter(transporter__user=user)
    completed = transports.filter(status="Delivered",
                                  date_delivered__gte=since, date_delivered__lt=until)
    completed_count = completed.count()
    on_time, measurable = _on_time_count(completed, "date_dispatched", "date_delivered", target.sla_days)

    receipted = completed.filter(site_receipt__isnull=False)
    receipted_count = receipted.count()
    undamaged = receipted.exclude(site_receipt__condition="Damaged").count()
    quality = _rate(undamaged, receipted_count)

    open_qs = transports.filter(status__in=["Loaded", "In Transit"])
    overdue = open_qs.filter(date_dispatched__lt=until - timedelta(days=target.sla_days)).count()
    open_count = open_qs.count()
    responsiveness = _rate(open_count - overdue, open_count)

    return _build_result(completed_count, _rate(on_time, measurable), quality,
                         completed_count, target, responsiveness=responsiveness,
                         on_time=on_time, measurable=measurable)


def _assemble(completed_count, on_time, measurable, total_created, bad,
              open_count, overdue, target):
    """Common assembly for order-based roles (schedule/store)."""
    timeliness = _rate(on_time, measurable)
    quality = _rate(total_created - bad, total_created)
    responsiveness = _rate(open_count - overdue, open_count)
    return _build_result(completed_count, timeliness, quality, completed_count,
                         target, responsiveness=responsiveness,
                         on_time=on_time, measurable=measurable, open_count=open_count,
                         overdue=overdue)


def _build_result(completed_count, timeliness, quality, throughput_completed,
                  target, responsiveness=None, on_time=0, measurable=0,
                  open_count=0, overdue=0):
    throughput = None
    if target.throughput_target:
        throughput = _clamp(throughput_completed / target.throughput_target * 100.0)
    # Scale quality so that hitting the quality target == full marks.
    quality_scaled = quality
    if quality is not None and target.quality_target_pct:
        quality_scaled = _clamp(quality / target.quality_target_pct * 100.0)
    return {
        "dimensions": {
            "timeliness": timeliness,
            "quality": quality_scaled,
            "throughput": throughput,
            "responsiveness": responsiveness,
        },
        "completed_count": completed_count,
        "on_time_count": on_time,
        "measurable_count": measurable,
        "open_count": open_count,
        "overdue_count": overdue,
        "quality_rate": quality,  # unscaled, for display
    }


_ROLE_FUNCS = {
    ROLE_SCHEDULE: _schedule_officer,
    ROLE_STORE: _store_officer,
    ROLE_CONSULTANT: _consultant,
    ROLE_MANAGEMENT: _management,
    ROLE_TRANSPORTER: _transporter,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_user_performance(user, since=None, until=None, config=None, targets=None):
    """
    Compute one user's appraisal for the window [since, until).
    Defaults to the last 30 days. Returns a structured, display-ready dict.
    """
    until = until or timezone.now()
    since = since or (until - timedelta(days=30))
    config = config or PerformanceConfig.load()
    targets = targets if targets is not None else get_targets()

    role = primary_role(user)
    result = {
        "user_id": user.id,
        "username": user.username,
        "full_name": (f"{user.first_name} {user.last_name}".strip() or user.username),
        "role": role,
        "since": since,
        "until": until,
        "gradable": role is not None,
        "insufficient_data": False,
        "dimensions": {},
        "weights_used": {},
        "overall_score": None,
        "grade": "N/A",
        "grade_color": "secondary",
        "completed_count": 0,
        "issues": [],
    }
    if role is None:
        result["grade"] = "N/A"
        return result

    target = targets.get(role)
    if target is None:
        # No target configured for this role yet.
        result["issues"].append(f"No performance target configured for role '{role}'.")
        return result

    stats = _ROLE_FUNCS[role](user, since, until, target)
    result.update({
        "dimensions": stats["dimensions"],
        "completed_count": stats["completed_count"],
        "on_time_count": stats["on_time_count"],
        "overdue_count": stats.get("overdue_count", 0),
        "quality_rate": stats.get("quality_rate"),
        "target": {
            "sla_days": target.sla_days,
            "throughput_target": target.throughput_target,
            "quality_target_pct": target.quality_target_pct,
            "stage_label": target.stage_label,
        },
    })

    # Minimum-data guard.
    if stats["completed_count"] < config.min_items_for_grade:
        result["insufficient_data"] = True
        result["grade"] = "N/A"
        return result

    # Weighted overall over the AVAILABLE dimensions only.
    weights = config.weights
    num, denom, used = 0.0, 0.0, {}
    for dim, score in stats["dimensions"].items():
        if score is None:
            continue
        w = weights.get(dim, 0)
        num += score * w
        denom += w
        used[dim] = w
    overall = round(num / denom, 1) if denom else None
    result["overall_score"] = overall
    result["weights_used"] = used
    result["grade"], result["grade_color"] = grade_from_score(overall)
    result["issues"] = _build_issues(stats, target)
    return result


def _build_issues(stats, target):
    """Plain-language list of what's costing the user points."""
    issues = []
    dims = stats["dimensions"]
    measurable = stats.get("measurable_count", 0)
    late = measurable - stats.get("on_time_count", 0)
    if dims.get("timeliness") is not None and late > 0:
        issues.append(f"{late} of {measurable} completed item(s) missed the {target.sla_days}-day SLA.")
    if dims.get("quality") is not None and (stats.get("quality_rate") or 100) < target.quality_target_pct:
        issues.append(f"Quality rate {stats['quality_rate']:.0f}% is below the {target.quality_target_pct}% target.")
    if dims.get("throughput") is not None and stats["completed_count"] < target.throughput_target:
        issues.append(f"Completed {stats['completed_count']} of the {target.throughput_target}/month throughput target.")
    if stats.get("overdue_count", 0) > 0:
        issues.append(f"{stats['overdue_count']} open item(s) are past their SLA and need action.")
    return issues


def compute_roster(since=None, until=None):
    """All gradable users with their grades, for the management roll-up."""
    from django.contrib.auth.models import User
    config = PerformanceConfig.load()
    targets = get_targets()
    rows = []
    users = User.objects.filter(is_active=True).prefetch_related("groups")
    for user in users:
        # One user with bad data must not zero out the whole roster — that
        # turned the management page into "0 users" regardless of reality.
        try:
            res = compute_user_performance(
                user, since, until, config=config, targets=targets)
        except Exception:
            logger.exception("Performance computation failed for user %s; skipping.",
                             getattr(user, 'username', user.pk))
            continue
        if res["gradable"]:
            rows.append(res)
    # Sort: graded users by score desc, insufficient-data last.
    rows.sort(key=lambda r: (r["overall_score"] is None, -(r["overall_score"] or 0)))
    return rows
