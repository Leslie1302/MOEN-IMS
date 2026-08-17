"""The 'Stores Management' group must reach every page under both the Stores
Operations and Stores Management navbar sections.

Historically several gates checked only 'Store Officers'/'Management', so Stores
Management users hit 403 (UserPassesTestMixin) or 404 (transporter views'
SuperuserOnlyMixin hides the page). These tests assert the access logic directly.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase

from Inventory.utils import can_access_stores
from Inventory.stores_management_views import (
    StoresManagementMixin, StoresStaffMixin,
    StoreOfficerPerformanceDashboard,
)
from Inventory.transporter_views import TransporterListView, TransportationStatusView
from Inventory.views.consultant_views import SiteReceiptListView

User = get_user_model()


class StoresManagementAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sm = cls._user('sm', 'Stores Management')
        cls.officer = cls._user('so', 'Store Officers')
        cls.outsider = User.objects.create_user('out', password='x')
        cls.rf = RequestFactory()

    @staticmethod
    def _user(name, group):
        u = User.objects.create_user(name, password='x')
        u.groups.add(Group.objects.get_or_create(name=group)[0])
        return u

    def _passes(self, view_cls, user):
        v = view_cls()
        req = self.rf.get('/')
        req.user = user
        v.request = req
        return v.test_func()

    def test_helper(self):
        self.assertTrue(can_access_stores(self.sm))
        self.assertTrue(can_access_stores(self.officer))
        self.assertFalse(can_access_stores(self.outsider))

    def test_stores_management_group_passes_every_gate(self):
        for view_cls in (StoresManagementMixin, StoresStaffMixin,
                         StoreOfficerPerformanceDashboard,
                         TransporterListView, TransportationStatusView, SiteReceiptListView):
            self.assertTrue(self._passes(view_cls, self.sm),
                            f"Stores Management denied by {view_cls.__name__}")

    def test_outsiders_still_denied(self):
        for view_cls in (StoresManagementMixin, StoresStaffMixin,
                         TransporterListView):
            self.assertFalse(self._passes(view_cls, self.outsider),
                             f"{view_cls.__name__} let a non-stores user in")
