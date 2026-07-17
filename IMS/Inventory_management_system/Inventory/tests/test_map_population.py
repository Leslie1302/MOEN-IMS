"""
Phase 4 regression tests: the Ghana map populates from the community
registry, not from hand-created sites.

  * Registering a Community auto-creates its ProjectSite (map row)
  * Sync is idempotent and reuses pre-existing sites
  * The community progress page flags BoQ communities missing from
    the registry (the silent string-match failures)
"""
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from Inventory.models import BillOfQuantity, Community, ProjectSite


class CommunityMapSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user('mgr', password='x')
        group, _ = Group.objects.get_or_create(name='Management')
        cls.manager.groups.add(group)

    def test_community_creation_creates_map_site(self):
        Community.objects.create(
            region='Volta', district='Central Tongu', community='Mafi Kumase',
        )
        site = ProjectSite.objects.get(community__iexact='Mafi Kumase')
        self.assertEqual(site.region, 'Volta')
        self.assertEqual(site.status, 'Planned')
        self.assertEqual(site.project.code, 'PRG-SHEP')  # umbrella programme

        # Map API sees it immediately
        self.client.force_login(self.manager)
        payload = self.client.get(reverse('ghana_map_data_api')).json()
        volta = next(r for r in payload['data'] if r['name'] == 'Volta')
        self.assertEqual(volta['total_sites'], 1)
        self.assertEqual(volta['planned_sites'], 1)

    def test_sync_is_idempotent(self):
        c = Community.objects.create(
            region='Volta', district='Central Tongu', community='Adidome',
        )
        c.package_number = 'PKG-1'
        c.save()  # second save must not duplicate the site
        self.assertEqual(
            ProjectSite.objects.filter(community__iexact='Adidome').count(), 1)

    def test_existing_site_is_reused_not_duplicated(self):
        from Inventory.models import Project
        project = Project.objects.create(
            name='Legacy', code='LEG-1', description='x',
            consultant='c', contractor='c',
        )
        ProjectSite.objects.create(
            project=project, name='Osu Site', code='OSU-1',
            region='Greater Accra', district='Accra Metro', community='Osu',
        )
        Community.objects.create(
            region='Greater Accra', district='Accra Metro', community='osu',
        )  # case-insensitive match on the existing site
        self.assertEqual(
            ProjectSite.objects.filter(community__iexact='Osu').count(), 1)

    def test_progress_page_flags_unregistered_boq_communities(self):
        BillOfQuantity.objects.create(
            region='Volta', district='Ho West', community='Dzolokpuita',
            consultant='c', contractor='c', package_number='PKG-9',
            material_description='Pole', item_code='P-1',
            contract_quantity=10,
        )
        self.client.force_login(self.manager)
        resp = self.client.get(reverse('community_progress_list'))
        self.assertEqual(resp.status_code, 200)
        missing = resp.context['unregistered_boq_communities']
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['community'], 'Dzolokpuita')

        # Registering the community clears the flag AND creates the site
        Community.objects.create(
            region='Volta', district='Ho West', community='Dzolokpuita',
        )
        resp = self.client.get(reverse('community_progress_list'))
        self.assertEqual(len(resp.context['unregistered_boq_communities']), 0)
        self.assertTrue(ProjectSite.objects.filter(
            community__iexact='Dzolokpuita').exists())
