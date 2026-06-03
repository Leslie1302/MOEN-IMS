"""
Tests for the access-rate calculator service.

Covers the contract documented in IMPLEMENTATION_PLAN_POLES_AND_ACCESS_RATE.md:

  * zero meters -> baseline-only rate (88.85% for the seed config)
  * +1 verified 1ph meter -> numerator goes up by persons_per_connection
  * +1 verified 3ph meter -> same weighting as 1ph
  * unverified rows do not contribute
  * region filter narrows the meter count but keeps the national
    baseline/denominator
  * a newer AccessRateConfig row takes over once its effective_from
    has been reached
  * as_of dates roll the rate back to the historical config
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from Inventory.models import (
    AccessRateConfig, Community, MeterInstallation, ProjectType,
)
from Inventory.services.access_rate import compute_access_rate, regional_meter_breakdown


User = get_user_model()


class AccessRateCalculatorTests(TestCase):
    """Verify compute_access_rate against the formula."""

    @classmethod
    def setUpTestData(cls):
        # The 0058 migration seeds the canonical config; rely on that so the
        # test asserts the same numbers a fresh install would publish.
        cls.cfg = AccessRateConfig.current()
        assert cls.cfg is not None, 'seed migration 0058 did not run'

        cls.project_type = ProjectType.objects.get(code='streetlights')

        cls.community_a = Community.objects.create(
            region='Greater Accra', district='Accra Metro',
            community='Osu', project_type=cls.project_type,
        )
        cls.community_b = Community.objects.create(
            region='Ashanti', district='Kumasi Metro',
            community='Adum', project_type=cls.project_type,
        )

        cls.reporter = User.objects.create_user('reporter', password='x')
        cls.verifier = User.objects.create_user('verifier', password='x')

    # ---- baseline ----------------------------------------------------------

    def test_baseline_only_with_zero_meters(self):
        """No meters installed -> rate is baseline / total."""
        result = compute_access_rate()
        expected_pct = round(
            (self.cfg.baseline_population_access / self.cfg.total_population) * 100,
            2,
        )
        self.assertEqual(result.meters_1ph, 0)
        self.assertEqual(result.meters_3ph, 0)
        self.assertEqual(result.pop_newly_served, 0)
        self.assertEqual(result.rate_pct, expected_pct)
        # Sanity-check the documented number from the plan.
        self.assertAlmostEqual(expected_pct, 88.85, places=1)

    # ---- meter contributions ----------------------------------------------

    def _verify_install(self, install):
        install.mark_verified(self.verifier)
        install.save(update_fields=['verified_by', 'verified_at'])
        return install

    def test_one_verified_1ph_meter_adds_persons_per_connection(self):
        install = MeterInstallation.objects.create(
            community=self.community_a,
            phase_type='1ph', quantity=1,
            installation_date=timezone.localdate(),
            reported_by=self.reporter,
        )
        self._verify_install(install)

        result = compute_access_rate()
        self.assertEqual(result.meters_1ph, 1)
        self.assertEqual(result.pop_newly_served, self.cfg.persons_per_connection)

    def test_one_verified_3ph_meter_weighted_same_as_1ph(self):
        install = MeterInstallation.objects.create(
            community=self.community_a,
            phase_type='3ph', quantity=1,
            installation_date=timezone.localdate(),
            reported_by=self.reporter,
        )
        self._verify_install(install)

        result = compute_access_rate()
        self.assertEqual(result.meters_3ph, 1)
        self.assertEqual(result.pop_newly_served, self.cfg.persons_per_connection)

    def test_unverified_meters_do_not_contribute(self):
        MeterInstallation.objects.create(
            community=self.community_a,
            phase_type='1ph', quantity=500,
            installation_date=timezone.localdate(),
            reported_by=self.reporter,
        )
        # Same row count, no verification stamp.
        result = compute_access_rate()
        self.assertEqual(result.meters_1ph, 0)
        self.assertEqual(result.pop_newly_served, 0)

    def test_include_unverified_flag_overrides(self):
        MeterInstallation.objects.create(
            community=self.community_a,
            phase_type='1ph', quantity=500,
            installation_date=timezone.localdate(),
            reported_by=self.reporter,
        )
        result = compute_access_rate(include_unverified=True)
        self.assertEqual(result.meters_1ph, 500)

    def test_thousand_1ph_meters_match_formula(self):
        """1000 verified 1ph meters -> numerator += 7000."""
        install = MeterInstallation.objects.create(
            community=self.community_a,
            phase_type='1ph', quantity=1000,
            installation_date=timezone.localdate(),
            reported_by=self.reporter,
        )
        self._verify_install(install)

        result = compute_access_rate()
        expected_numerator = (
            self.cfg.persons_per_connection * 1000
            + self.cfg.baseline_population_access
        )
        expected_pct = round(expected_numerator / self.cfg.total_population * 100, 2)
        self.assertEqual(result.rate_pct, expected_pct)

    # ---- geographic filters -----------------------------------------------

    def test_region_filter_narrows_meters_but_not_denominator(self):
        for community in (self.community_a, self.community_b):
            self._verify_install(MeterInstallation.objects.create(
                community=community,
                phase_type='1ph', quantity=1,
                installation_date=timezone.localdate(),
                reported_by=self.reporter,
            ))

        national = compute_access_rate()
        region   = compute_access_rate(region='Greater Accra')

        self.assertEqual(national.meters_1ph, 2)
        self.assertEqual(region.meters_1ph, 1)
        # Denominator unchanged across scopes.
        self.assertEqual(region.total_population, national.total_population)
        self.assertEqual(region.baseline_population, national.baseline_population)
        # And the result is flagged.
        self.assertEqual(region.scope, 'region')
        self.assertEqual(national.scope, 'national')

    def test_district_filter_works(self):
        for community, qty in (
            (self.community_a, 3),  # Accra Metro
            (self.community_b, 5),  # Kumasi Metro
        ):
            self._verify_install(MeterInstallation.objects.create(
                community=community,
                phase_type='1ph', quantity=qty,
                installation_date=timezone.localdate(),
                reported_by=self.reporter,
            ))
        result = compute_access_rate(district='Accra Metro')
        self.assertEqual(result.meters_1ph, 3)
        self.assertEqual(result.scope, 'district')

    # ---- config versioning -------------------------------------------------

    def test_newer_config_takes_over_after_effective_from(self):
        future = timezone.localdate() + datetime.timedelta(days=1)
        AccessRateConfig.objects.create(
            persons_per_connection=10,        # changed
            baseline_population_access=self.cfg.baseline_population_access,
            total_population=self.cfg.total_population,
            effective_from=timezone.localdate(),  # today, supersedes the 2026-01-01 seed
            notes='Test override',
        )
        install = MeterInstallation.objects.create(
            community=self.community_a,
            phase_type='1ph', quantity=1,
            installation_date=timezone.localdate(),
            reported_by=self.reporter,
        )
        self._verify_install(install)

        result = compute_access_rate()
        self.assertEqual(result.persons_per_connection, 10)
        self.assertEqual(result.pop_newly_served, 10)

    def test_as_of_picks_historical_config(self):
        # Add a meter that's only counted if installation_date <= today.
        install = MeterInstallation.objects.create(
            community=self.community_a,
            phase_type='1ph', quantity=1,
            installation_date=timezone.localdate(),
            reported_by=self.reporter,
        )
        self._verify_install(install)

        before_install = timezone.localdate() - datetime.timedelta(days=30)
        historical = compute_access_rate(as_of=before_install)
        self.assertEqual(historical.meters_1ph, 0)

        current = compute_access_rate()
        self.assertEqual(current.meters_1ph, 1)

    # ---- regional breakdown helper ----------------------------------------

    def test_regional_breakdown_counts_each_region(self):
        self._verify_install(MeterInstallation.objects.create(
            community=self.community_a, phase_type='1ph', quantity=5,
            installation_date=timezone.localdate(), reported_by=self.reporter,
        ))
        self._verify_install(MeterInstallation.objects.create(
            community=self.community_a, phase_type='3ph', quantity=2,
            installation_date=timezone.localdate(), reported_by=self.reporter,
        ))
        self._verify_install(MeterInstallation.objects.create(
            community=self.community_b, phase_type='1ph', quantity=3,
            installation_date=timezone.localdate(), reported_by=self.reporter,
        ))
        breakdown = regional_meter_breakdown()
        self.assertEqual(breakdown['Greater Accra']['meters_1ph'], 5)
        self.assertEqual(breakdown['Greater Accra']['meters_3ph'], 2)
        self.assertEqual(breakdown['Ashanti']['meters_1ph'], 3)
        self.assertEqual(
            breakdown['Greater Accra']['pop_newly_served'],
            self.cfg.persons_per_connection * 7,
        )


class AccessRateConfigTests(TestCase):
    """Direct unit tests on AccessRateConfig.current()."""

    def test_current_picks_latest_effective_from(self):
        AccessRateConfig.objects.all().delete()
        older = AccessRateConfig.objects.create(
            persons_per_connection=5,
            baseline_population_access=1_000_000,
            total_population=2_000_000,
            effective_from=datetime.date(2025, 1, 1),
        )
        newer = AccessRateConfig.objects.create(
            persons_per_connection=7,
            baseline_population_access=1_000_000,
            total_population=2_000_000,
            effective_from=datetime.date(2026, 1, 1),
        )
        self.assertEqual(AccessRateConfig.current(), newer)

    def test_current_respects_as_of(self):
        AccessRateConfig.objects.all().delete()
        older = AccessRateConfig.objects.create(
            persons_per_connection=5,
            baseline_population_access=1_000_000,
            total_population=2_000_000,
            effective_from=datetime.date(2025, 1, 1),
        )
        AccessRateConfig.objects.create(
            persons_per_connection=7,
            baseline_population_access=1_000_000,
            total_population=2_000_000,
            effective_from=datetime.date(2026, 1, 1),
        )
        # Mid-2025 -> picks the older row.
        self.assertEqual(
            AccessRateConfig.current(as_of=datetime.date(2025, 6, 15)),
            older,
        )
