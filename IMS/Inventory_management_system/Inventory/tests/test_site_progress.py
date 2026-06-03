"""
Tests for the consultant-facing Site Progress flow.

Covers:
  * the list page renders with the new aggregates
  * the edit form updates works_status / progress_percent / notes
  * progress_updated_at / progress_updated_by are stamped automatically
  * the cross-field guard blocks an Energised -> In Progress regression
    that doesn't include a note
  * the JSON API exposes the regional totals
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from Inventory.forms.site_progress import SiteProgressForm
from Inventory.models import Project, ProjectSite


User = get_user_model()


class SiteProgressTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(
            'consultant', 'c@test.local', 'pw',
        )
        cls.project = Project.objects.create(
            name='SHEP rollout', code='SHEP-001', description='',
            project_type='SHEP', status='Active', consultant='—',
            start_date=timezone.localdate(), planned_end_date=timezone.localdate(),
        )
        cls.site = ProjectSite.objects.create(
            project=cls.project, name='Osu A', code='OSU-A',
            region='Greater Accra', district='Accra Metro', community='Osu',
        )

    def _login(self):
        self.client = Client()
        self.client.force_login(self.user)

    # ---- list page --------------------------------------------------------

    def test_list_renders_with_aggregates(self):
        self._login()
        response = self.client.get(reverse('site_progress_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Site progress')
        self.assertContains(response, self.site.community)

    # ---- edit form --------------------------------------------------------

    def test_edit_updates_fields_and_stamps_audit(self):
        self._login()
        before = timezone.now()
        response = self.client.post(
            reverse('site_progress_edit', args=[self.site.pk]),
            data={
                'works_status': 'Energised',
                'progress_percent': '85',
                'progress_notes': 'Conductors strung, transformer energised last week.',
            },
        )
        # Redirect to the list page on success.
        self.assertEqual(response.status_code, 302)

        self.site.refresh_from_db()
        self.assertEqual(self.site.works_status, 'Energised')
        self.assertEqual(self.site.progress_percent, 85)
        self.assertIsNotNone(self.site.progress_updated_at)
        self.assertGreaterEqual(self.site.progress_updated_at, before)
        self.assertEqual(self.site.progress_updated_by, self.user)
        # Energised sites get actual_completion_date stamped for the
        # existing map drill-downs that read it.
        self.assertEqual(self.site.actual_completion_date, timezone.localdate())

    def test_edit_rejects_regression_without_note(self):
        self.site.works_status = 'Energised'
        self.site.save(update_fields=['works_status'])

        form = SiteProgressForm(
            data={
                'works_status': 'In Progress',
                'progress_percent': '50',
                'progress_notes': '',
            },
            instance=self.site,
        )
        self.assertFalse(form.is_valid())
        self.assertIn('progress_notes', form.errors)

    def test_edit_accepts_regression_with_note(self):
        self.site.works_status = 'Energised'
        self.site.save(update_fields=['works_status'])

        form = SiteProgressForm(
            data={
                'works_status': 'In Progress',
                'progress_percent': '50',
                'progress_notes': 'Reported transformer fault, re-investigating.',
            },
            instance=self.site,
        )
        self.assertTrue(form.is_valid(), form.errors)

    # ---- JSON API ---------------------------------------------------------

    def test_api_returns_regional_totals(self):
        ProjectSite.objects.create(
            project=self.project, name='Osu B', code='OSU-B',
            region='Greater Accra', district='Accra Metro', community='Osu',
            works_status='Energised', progress_percent=100,
        )
        self._login()
        payload = self.client.get(reverse('site_progress_api')).json()
        self.assertIn('Greater Accra', payload['regions'])
        gar = payload['regions']['Greater Accra']
        self.assertEqual(gar['total_sites'], 2)
        self.assertEqual(gar['energised_sites'], 1)
        self.assertEqual(gar['energised_pct'], 50.0)
