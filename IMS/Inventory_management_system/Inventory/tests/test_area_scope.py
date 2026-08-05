"""Area-based region scoping."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from Inventory.models import Area, AreaRegion, Community, Profile
from Inventory.utils import accessible_region_names, scope_qs_by_area

User = get_user_model()


class AreaScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.area = Area.objects.create(name='Test Area')
        AreaRegion.objects.create(area=cls.area, region='Ashanti')

        Community.objects.create(region='Ashanti', district='Kumasi', community='A')
        Community.objects.create(region='Volta', district='Ho', community='B')

        cons = Group.objects.create(name='Consultants')
        mgmt = Group.objects.create(name='Management')

        cls.consultant = User.objects.create_user('cons', password='x')
        cls.consultant.groups.add(cons)
        Profile.objects.create(user=cls.consultant, area=cls.area)

        cls.consultant_no_area = User.objects.create_user('cons2', password='x')
        cls.consultant_no_area.groups.add(cons)
        Profile.objects.create(user=cls.consultant_no_area)

        cls.manager = User.objects.create_user('mgr', password='x')
        cls.manager.groups.add(mgmt)

    def test_consultant_scoped_to_their_area(self):
        self.assertEqual(accessible_region_names(self.consultant), ['Ashanti'])
        qs = scope_qs_by_area(Community.objects.all(), self.consultant)
        self.assertEqual(set(qs.values_list('region', flat=True)), {'Ashanti'})

    def test_management_sees_everything(self):
        self.assertIsNone(accessible_region_names(self.manager))
        qs = scope_qs_by_area(Community.objects.all(), self.manager)
        self.assertEqual(qs.count(), 2)

    def test_unassigned_scoped_user_sees_nothing(self):
        # Fail closed: a consultant with no area must not see the whole country.
        self.assertEqual(accessible_region_names(self.consultant_no_area), [])
        self.assertEqual(
            scope_qs_by_area(Community.objects.all(), self.consultant_no_area).count(), 0)
