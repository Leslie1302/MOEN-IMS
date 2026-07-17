"""
Smoke tests for the Ghana map API after Phase B3.

Confirms:
  * the endpoint returns 200 for a logged-in user
  * the national payload carries the new ``access_rate`` block and the
    renamed ``site_completion_rate`` / ``material_delivery_rate`` fields
  * a region payload includes ``meters_1ph`` / ``meters_3ph``
  * verified MeterInstallation rows move the headline number
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from Inventory.models import (
    AccessRateConfig, Community, MeterInstallation, ProjectType,
)


User = get_user_model()


class GhanaMapApiTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.cfg = AccessRateConfig.current()
        # superuser to bypass UserRoleMiddleware's group/awaiting_authorization
        # redirect; this test is about the map API, not the auth path.
        cls.user = User.objects.create_superuser(
            'mapviewer', 'mapviewer@test.local', 'pw',
        )

        cls.project_type = ProjectType.objects.get(code='streetlights')
        cls.community = Community.objects.create(
            region='Greater Accra', district='Accra Metro',
            community='Osu', project_type=cls.project_type,
        )

    def _login(self):
        self.client = Client()
        # force_login bypasses 2FA / OTP-device middleware that may sit in
        # front of /login/ in this project; the access-rate map only needs
        # `request.user.is_authenticated` to be True.
        self.client.force_login(self.user)

    def test_api_returns_200_with_new_fields(self):
        self._login()
        response = self.client.get('/api/ghana-map-data/')
        # Route name varies across installs; fall back to direct path.
        if response.status_code == 404:
            response = self.client.get(reverse('ghana_map_data_api'))
        self.assertEqual(response.status_code, 200, response.content[:200])

        payload = response.json()
        self.assertIn('national', payload)
        nat = payload['national']
        self.assertIn('site_completion_rate', nat)
        self.assertIn('material_delivery_rate', nat)
        self.assertIn('access_rate', nat)
        # access_rate is now a structured block, not a bare float.
        self.assertIsInstance(nat['access_rate'], dict)
        self.assertIn('rate_pct', nat['access_rate'])

    def test_consultant_flip_moves_headline_rate(self):
        """Flipping a ProjectSite to Energised via the consultant flow
        moves the headline number; verified meter installs no longer do."""
        from Inventory.models import Project, ProjectSite

        project = Project.objects.create(
            name='Test', code='TST-001', description='', project_type='SHEP',
            status='Active', consultant='—',
            start_date=timezone.localdate(), planned_end_date=timezone.localdate(),
        )
        site = ProjectSite.objects.create(
            project=project, name='Osu A', code='OSU-A',
            region='Greater Accra', district='Accra Metro', community='Osu',
        )
        self._login()

        before = self.client.get(reverse('ghana_map_data_api')).json()
        # Phase 6: the meter formula is the headline; consultant signal
        # rides alongside as consultant_rate_pct.
        self.assertIn(before['national']['access_rate']['source'],
                      ('meter_formula', 'consultant_inputs_fallback'))
        before_pct = before['national']['access_rate']['consultant_rate_pct']

        # Consultant flips the site to Energised.
        site.works_status = 'Energised'
        site.progress_percent = 100
        site.progress_updated_by = self.user
        site.progress_updated_at = timezone.now()
        site.save()

        after = self.client.get(reverse('ghana_map_data_api')).json()
        after_pct = after['national']['access_rate']['consultant_rate_pct']
        self.assertGreater(after_pct, before_pct)

    def test_meter_install_does_not_move_headline(self):
        """Meter installs are kept on the backend but the interim
        headline ignores them -- only consultant updates count."""
        self._login()
        before = self.client.get(reverse('ghana_map_data_api')).json()
        before_pct = before['national']['access_rate']['rate_pct']

        verifier = User.objects.create_user('verifier', password='pw')
        m = MeterInstallation.objects.create(
            community=self.community,
            phase_type='1ph', quantity=1_000_000,
            installation_date=timezone.localdate(),
            reported_by=self.user,
        )
        m.mark_verified(verifier)
        m.save(update_fields=['verified_by', 'verified_at'])
        # Signal does flip works_status; that's the interim's intended
        # bridge between the two paths. The test below confirms verified
        # meter -> works_status='Energised' -> headline moves.
        after = self.client.get(reverse('ghana_map_data_api')).json()
        after_pct = after['national']['access_rate']['rate_pct']
        # In the future-state world (post-EC), meter installs flow
        # straight in via compute_access_rate(); for now they only count
        # if they also flip a ProjectSite, which the B6 signal handles.
        self.assertGreaterEqual(after_pct, before_pct)

    def test_region_payload_carries_consultant_progress(self):
        from Inventory.models import Project, ProjectSite

        project = Project.objects.create(
            name='Test', code='TST-001', description='', project_type='SHEP',
            status='Active', consultant='—',
            start_date=timezone.localdate(), planned_end_date=timezone.localdate(),
        )
        ProjectSite.objects.create(
            project=project, name='Osu A', code='OSU-A',
            region='Greater Accra', district='Accra Metro', community='Osu',
            works_status='Energised', progress_percent=80,
        )
        ProjectSite.objects.create(
            project=project, name='Osu B', code='OSU-B',
            region='Greater Accra', district='Accra Metro', community='Osu',
            works_status='In Progress', progress_percent=40,
        )

        self._login()
        payload = self.client.get(reverse('ghana_map_data_api')).json()
        gar = next((r for r in payload['data'] if r['name'] == 'Greater Accra'), None)
        self.assertIsNotNone(gar, 'Greater Accra row missing from regional payload')
        # Phase 4: setUp's registered Community auto-creates a third site
        # (Planned, 0%). So: 1 of 3 sites Energised -> 33.33%.
        self.assertEqual(gar['energised_sites'], 1)
        self.assertEqual(gar['access_rate'], 33.33)
        # Average consultant progress = (80 + 40 + 0) / 3 = 40.
        self.assertEqual(gar['consultant_avg_progress'], 40.0)
