"""
Tests for the rebuilt KPI / appraisal engine (Inventory/services/performance.py).

Targets are seeded by migration 0066, so these run against the real configured
SLAs (Schedule Officer SLA 3 days, throughput 20/mo, etc.).
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.utils import timezone

from Inventory.models import Unit, MaterialOrder, SiteReceipt, MaterialTransport
from Inventory.services.performance import (
    compute_user_performance, grade_from_score, primary_role,
)


def _set(order, **fields):
    """Bypass auto_now_add/save() to control timestamps and status."""
    MaterialOrder.objects.filter(pk=order.pk).update(**fields)


class GradeBandingTest(TestCase):
    def test_bands(self):
        self.assertEqual(grade_from_score(92)[0], "A+")
        self.assertEqual(grade_from_score(86)[0], "A")
        self.assertEqual(grade_from_score(72)[0], "C+")
        self.assertEqual(grade_from_score(50)[0], "F")
        self.assertEqual(grade_from_score(None)[0], "N/A")


class PrimaryRoleTest(TestCase):
    def test_role_from_group(self):
        g = Group.objects.get_or_create(name="Store Officers")[0]
        u = User.objects.create(username="so1")
        u.groups.add(g)
        self.assertEqual(primary_role(u), "Store Officers")

    def test_no_role(self):
        u = User.objects.create(username="nobody")
        self.assertIsNone(primary_role(u))


class ScheduleOfficerScoringTest(TestCase):
    def setUp(self):
        self.unit = Unit.objects.create(name="each")
        self.now = timezone.now()
        self.since = self.now - timedelta(days=30)
        self.officer = User.objects.create(username="sched1")
        self.officer.groups.add(Group.objects.get_or_create(name="Schedule Officers")[0])

    def _order(self, days_ago_requested, processing_days, status="Completed"):
        req = self.now - timedelta(days=days_ago_requested)
        proc = req + timedelta(days=processing_days)
        o = MaterialOrder.objects.create(
            name="Pole", quantity=Decimal("1"), unit=self.unit, user=self.officer
        )
        _set(o, date_requested=req, processed_at=proc, status=status)
        return o

    def test_all_on_time_grades_well(self):
        for _ in range(6):
            self._order(days_ago_requested=10, processing_days=2)  # 2d <= 3d SLA
        res = compute_user_performance(self.officer, self.since, self.now)
        self.assertEqual(res["role"], "Schedule Officers")
        self.assertEqual(res["completed_count"], 6)
        self.assertEqual(res["dimensions"]["timeliness"], 100.0)
        self.assertFalse(res["insufficient_data"])
        # timeliness100*30 + quality100*30 + throughput(6/20=30)*20, /80 = 82.5
        self.assertAlmostEqual(res["overall_score"], 82.5, places=1)
        self.assertEqual(res["grade"], "B+")

    def test_late_work_lowers_timeliness(self):
        for _ in range(3):
            self._order(days_ago_requested=10, processing_days=2)   # on time
        for _ in range(3):
            self._order(days_ago_requested=10, processing_days=6)   # late (>3d)
        res = compute_user_performance(self.officer, self.since, self.now)
        self.assertEqual(res["completed_count"], 6)
        self.assertEqual(res["dimensions"]["timeliness"], 50.0)

    def test_insufficient_data_below_threshold(self):
        for _ in range(4):  # below min_items_for_grade (5)
            self._order(days_ago_requested=10, processing_days=2)
        res = compute_user_performance(self.officer, self.since, self.now)
        self.assertTrue(res["insufficient_data"])
        self.assertEqual(res["grade"], "N/A")
        self.assertIsNone(res["overall_score"])

    def test_rejected_orders_hurt_quality(self):
        for _ in range(5):
            self._order(days_ago_requested=10, processing_days=2)
        # One rejected order created in-window drags quality down.
        self._order(days_ago_requested=10, processing_days=2, status="Rejected")
        res = compute_user_performance(self.officer, self.since, self.now)
        self.assertIsNotNone(res["quality_rate"])
        self.assertLess(res["quality_rate"], 100)


class ConsultantQualityTest(TestCase):
    def setUp(self):
        self.unit = Unit.objects.create(name="each")
        self.now = timezone.now()
        self.since = self.now - timedelta(days=30)
        self.consultant = User.objects.create(username="cons1")
        self.consultant.groups.add(Group.objects.get_or_create(name="Consultants")[0])
        self.order = MaterialOrder.objects.create(
            name="Cable", quantity=Decimal("1"), unit=self.unit
        )

    def _receipt(self, condition):
        transport = MaterialTransport.objects.create(
            material_order=self.order, quantity=Decimal("1"),
            status="Delivered", date_delivered=self.now - timedelta(days=2),
        )
        return SiteReceipt.objects.create(
            material_transport=transport,
            received_quantity=Decimal("1"),
            received_by=self.consultant,
            condition=condition,
        )

    def test_quality_rate_reflects_conditions(self):
        for _ in range(4):
            self._receipt("Good")
        self._receipt("Damaged")  # 4/5 good = 80%
        # received_date is auto_now_add, so use the default (live) 30-day window.
        res = compute_user_performance(self.consultant)
        self.assertEqual(res["role"], "Consultants")
        self.assertEqual(res["completed_count"], 5)
        self.assertAlmostEqual(res["quality_rate"], 80.0, places=1)


class PerformanceViewRenderTest(TestCase):
    """Smoke test: the new appraisal pages render for the right users."""

    def setUp(self):
        self.mgr = User.objects.create_superuser("mgr", "m@x.com", "pw")
        self.staff = User.objects.create_user("staff1", password="pw")
        self.staff.groups.add(Group.objects.get_or_create(name="Store Officers")[0])

    def test_team_page_renders_for_management(self):
        self.client.force_login(self.mgr)
        resp = self.client.get("/performance/team/")
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "Inventory/performance/team_performance.html")

    def test_my_page_renders(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/performance/me/")
        self.assertEqual(resp.status_code, 200)

    def test_staff_detail_blocked_for_non_management_other_user(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/performance/user/mgr/")
        self.assertEqual(resp.status_code, 403)


class StaffProfilePageTest(TestCase):
    """Regression: management 'view user details' must render, not redirect."""

    def setUp(self):
        self.mgr = User.objects.create_superuser("mgr2", "m2@x.com", "pw")
        self.staff = User.objects.create_user("staff2", password="pw")

    def test_staff_profile_renders_for_management(self):
        self.client.force_login(self.mgr)
        resp = self.client.get(f"/staff-profile/{self.staff.username}/")
        self.assertEqual(resp.status_code, 200)  # was 302 redirect before the fix
        self.assertTemplateUsed(resp, "Inventory/staff_profile.html")


class ManagementDashboardLinkTest(TestCase):
    """Regression: management dashboard must link to user details by USERNAME,
    not by full name (which 404s and bounced to the dashboard)."""

    def setUp(self):
        self.mgr = User.objects.create_superuser("boss", "b@x.com", "pw")
        self.staff = User.objects.create_user(
            "sadjei", password="pw", first_name="Selorm", last_name="Adjei"
        )
        self.staff.groups.add(Group.objects.get_or_create(name="Schedule Officers")[0])

    def test_dashboard_links_by_username(self):
        self.client.force_login(self.mgr)
        resp = self.client.get("/management_dashboard/")
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("/staff-profile/sadjei/", html)          # links by username
        self.assertNotIn("/staff-profile/Selorm", html)        # not by full name
        self.assertIn("Selorm Adjei", html)                    # full name still shown
