"""
Tests for the works_status decouple (Phase B6).

Verifies that:
  * adding an unverified MeterInstallation does NOT change works_status
  * verifying a MeterInstallation flips matching ProjectSites to 'Energised'
  * 'Commissioned' is never downgraded by a later install
  * the explicit project_site link overrides the community-wide sweep
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from Inventory.models import (
    Community, MeterInstallation, Project, ProjectSite, ProjectType,
)


User = get_user_model()


class WorksStatusSignalTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.project_type = ProjectType.objects.get(code='streetlights')
        cls.reporter = User.objects.create_user('rep', password='x')
        cls.verifier = User.objects.create_user('mgr', password='x')

        cls.community = Community.objects.create(
            region='Greater Accra', district='Accra Metro',
            community='Osu', project_type=cls.project_type,
        )
        cls.project = Project.objects.create(
            name='Osu poles rollout', code='POL-OSU-01',
            description='test', project_type='STREET', status='Active',
            consultant='—', start_date=timezone.localdate(),
            planned_end_date=timezone.localdate(),
        )
        cls.site = ProjectSite.objects.create(
            project=cls.project, name='Osu A', code='OSU-A',
            region='Greater Accra', district='Accra Metro', community='Osu',
        )

    def _install(self, **kwargs):
        defaults = dict(
            community=self.community,
            phase_type='1ph', quantity=1,
            installation_date=timezone.localdate(),
            reported_by=self.reporter,
        )
        defaults.update(kwargs)
        return MeterInstallation.objects.create(**defaults)

    def test_default_works_status_is_planned(self):
        self.assertEqual(self.site.works_status, 'Planned')

    def test_unverified_install_does_not_change_works_status(self):
        self._install()
        self.site.refresh_from_db()
        self.assertEqual(self.site.works_status, 'Planned')

    def test_verified_install_flips_to_energised(self):
        install = self._install()
        install.mark_verified(self.verifier)
        install.save(update_fields=['verified_by', 'verified_at'])

        self.site.refresh_from_db()
        self.assertEqual(self.site.works_status, 'Energised')

    def test_commissioned_is_never_downgraded(self):
        self.site.works_status = 'Commissioned'
        self.site.save(update_fields=['works_status'])

        install = self._install()
        install.mark_verified(self.verifier)
        install.save(update_fields=['verified_by', 'verified_at'])

        self.site.refresh_from_db()
        self.assertEqual(self.site.works_status, 'Commissioned')

    def test_explicit_project_site_link_targets_only_that_site(self):
        other_site = ProjectSite.objects.create(
            project=self.project, name='Osu B', code='OSU-B',
            region='Greater Accra', district='Accra Metro', community='Osu',
        )
        install = self._install(project_site=self.site)
        install.mark_verified(self.verifier)
        install.save(update_fields=['verified_by', 'verified_at'])

        self.site.refresh_from_db()
        other_site.refresh_from_db()
        self.assertEqual(self.site.works_status, 'Energised')
        # other_site shares the same community but was not the explicit
        # target; sweep is skipped when project_site_id is set.
        self.assertEqual(other_site.works_status, 'Planned')

    def test_already_energised_is_idempotent(self):
        install = self._install()
        install.mark_verified(self.verifier)
        install.save(update_fields=['verified_by', 'verified_at'])

        # Second verified install at the same site -- signal must be a no-op,
        # not flip back to Planned or trigger an extra save.
        install2 = self._install(phase_type='3ph', quantity=2)
        install2.mark_verified(self.verifier)
        install2.save(update_fields=['verified_by', 'verified_at'])

        self.site.refresh_from_db()
        self.assertEqual(self.site.works_status, 'Energised')
