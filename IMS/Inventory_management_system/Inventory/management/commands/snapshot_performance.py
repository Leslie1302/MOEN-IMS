"""
Persist monthly performance snapshots for all gradable users.

Run on a schedule (e.g. first of each month) to build appraisal history and
trends:  python manage.py snapshot_performance            # previous month
         python manage.py snapshot_performance --year 2026 --month 5
"""
import calendar
from datetime import datetime

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from Inventory.models import PerformanceSnapshot
from Inventory.services.performance import compute_user_performance, primary_role


class Command(BaseCommand):
    help = "Snapshot each gradable user's performance grade for a calendar month."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=None)
        parser.add_argument("--month", type=int, default=None)

    def handle(self, *args, **options):
        year, month = options["year"], options["month"]
        if not (year and month):
            # Default to the previous calendar month.
            today = timezone.now()
            first_this_month = today.replace(day=1)
            prev = first_this_month - timezone.timedelta(days=1)
            year, month = prev.year, prev.month

        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime(year, month, 1), tz)
        last_day = calendar.monthrange(year, month)[1]
        end = timezone.make_aware(datetime(year, month, last_day, 23, 59, 59), tz)

        written = 0
        for user in User.objects.filter(is_active=True).prefetch_related("groups"):
            if primary_role(user) is None:
                continue
            res = compute_user_performance(user, since=start, until=end)
            dims = res.get("dimensions", {})
            PerformanceSnapshot.objects.update_or_create(
                user=user, period_year=year, period_month=month,
                defaults={
                    "role": res.get("role") or "",
                    "timeliness_score": dims.get("timeliness"),
                    "quality_score": dims.get("quality"),
                    "throughput_score": dims.get("throughput"),
                    "responsiveness_score": dims.get("responsiveness"),
                    "overall_score": res.get("overall_score"),
                    "grade": "" if res.get("insufficient_data") else res.get("grade", ""),
                    "completed_count": res.get("completed_count", 0),
                    "on_time_count": res.get("on_time_count", 0),
                    "insufficient_data": res.get("insufficient_data", False),
                },
            )
            written += 1

        self.stdout.write(self.style.SUCCESS(
            f"Wrote {written} performance snapshot(s) for {year}-{month:02d}."
        ))
