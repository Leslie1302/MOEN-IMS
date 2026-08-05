"""Consignee resolution binds via the consultant's Area."""

from django.test import TestCase

from Inventory.models import Area, AreaRegion, Community, ProjectConsultant, ProjectType
from Inventory.services.consignee_resolver import resolve_consignee


class ConsigneeAreaResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # A consultant-routed project type (SHEP is seeded by migration 0033).
        cls.ptype = (ProjectType.objects.filter(consignee_role='consultant').first())
        assert cls.ptype is not None, 'no consultant-routed ProjectType seeded'

        cls.area = Area.objects.create(name='Northern Belt')
        AreaRegion.objects.create(area=cls.area, region='Northern')
        AreaRegion.objects.create(area=cls.area, region='Savannah')

        cls.consultant = ProjectConsultant.objects.create(
            name='Belt Consult', firm='Belt Engineering Ltd', area=cls.area, active=True)

    def test_resolves_by_area_for_any_region_in_it(self):
        for region in ('Northern', 'Savannah'):
            community = Community.objects.create(
                region=region, district='D', community=f'C-{region}')
            resolved = resolve_consignee(self.ptype, community=community)
            self.assertEqual(resolved.kind, 'consultant')
            self.assertEqual(resolved.name, 'Belt Consult')

    def test_region_outside_area_does_not_resolve_to_this_consultant(self):
        community = Community.objects.create(
            region='Volta', district='D', community='C-Volta')
        resolved = resolve_consignee(self.ptype, community=community)
        # No area covers Volta and no legacy region/district set → unresolved.
        self.assertNotEqual(resolved.name, 'Belt Consult')
