"""
Performance / appraisal views (rebuilt KPI system).

- MyPerformanceView        : a user's own appraisal (self-service).
- staff_performance_detail : management (or the user) viewing one person.
- TeamPerformanceView      : management roll-up of everyone's grades.

Visibility policy: a user can see their own; management/superusers can see anyone.
"""
import logging

from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.views.generic import TemplateView

from Inventory.models import PerformanceSnapshot
from Inventory.services.performance import compute_user_performance, compute_roster

logger = logging.getLogger(__name__)


def _is_management(user):
    return user.is_superuser or user.groups.filter(name="Management").exists()


def _history(user, limit=6):
    return list(
        PerformanceSnapshot.objects.filter(user=user)
        .order_by("period_year", "period_month")
        .values("period_year", "period_month", "overall_score", "grade")[:limit]
    )


class MyPerformanceView(LoginRequiredMixin, TemplateView):
    template_name = "Inventory/performance/my_performance.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["perf"] = compute_user_performance(self.request.user)
        ctx["history"] = _history(self.request.user)
        ctx["is_self"] = True
        return ctx


@login_required
def staff_performance_detail(request, username):
    """Management views any user's appraisal; a user may view their own."""
    staff = get_object_or_404(User, username=username)
    if staff != request.user and not _is_management(request.user):
        raise PermissionDenied
    ctx = {
        "perf": compute_user_performance(staff),
        "history": _history(staff),
        "is_self": staff == request.user,
        "staff_member": staff,
    }
    return render(request, "Inventory/performance/my_performance.html", ctx)


class TeamPerformanceView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "Inventory/performance/team_performance.html"

    def test_func(self):
        return _is_management(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        roster = compute_roster()
        graded = [r for r in roster if not r["insufficient_data"] and r["overall_score"] is not None]
        ctx["roster"] = roster
        ctx["graded_count"] = len(graded)
        ctx["total_count"] = len(roster)
        ctx["avg_score"] = round(sum(r["overall_score"] for r in graded) / len(graded), 1) if graded else None
        ctx["top"] = graded[0] if graded else None
        return ctx
