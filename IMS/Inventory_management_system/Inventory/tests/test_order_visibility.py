"""Who can see which material orders.

The list drives stock movements, so it fails CLOSED: a user with no
material-order role sees nothing rather than everything. Before this, the view
had no filtering at all — any logged-in account saw the entire national order
book.
"""

from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse

from Inventory.models import MaterialOrder, Unit


class OrderVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unit = Unit.objects.create(name='set')

        def order(code, assignee=None):
            return MaterialOrder.objects.create(
                name='Stay Wire', quantity=Decimal('10'), unit=cls.unit,
                request_type='Release', status='Pending',
                request_code=code, assigned_to=assignee)

        cls.officer_a = cls._user('officer_a', 'Store Officers')
        cls.officer_b = cls._user('officer_b', 'Store Officers')
        cls.stores_mgmt = cls._user('stores_mgmt', 'Stores Management')
        cls.management = cls._user('mgmt', 'Management')
        cls.consultant = cls._user('consultant', 'Consultants')
        cls.admin = User.objects.create_superuser('root', password='pw')

        cls.mine = order('REQ-A', cls.officer_a)
        cls.theirs = order('REQ-B', cls.officer_b)
        cls.unassigned = order('REQ-C', None)

    @staticmethod
    def _user(username, group):
        user = User.objects.create_user(username, password='pw')
        user.groups.add(Group.objects.get_or_create(name=group)[0])
        return user

    def _codes_visible_to(self, user):
        self.client.force_login(user)
        resp = self.client.get(reverse('material_orders'))
        if resp.status_code != 200:
            return None
        return {o.request_code for o in resp.context['orders']}

    # -- full visibility ---------------------------------------------------
    def test_superuser_sees_everything(self):
        self.assertEqual(self._codes_visible_to(self.admin),
                         {'REQ-A', 'REQ-B', 'REQ-C'})

    def test_stores_management_sees_everything(self):
        self.assertEqual(self._codes_visible_to(self.stores_mgmt),
                         {'REQ-A', 'REQ-B', 'REQ-C'})

    def test_management_sees_everything(self):
        self.assertEqual(self._codes_visible_to(self.management),
                         {'REQ-A', 'REQ-B', 'REQ-C'})

    # -- scoped ------------------------------------------------------------
    def test_a_store_officer_sees_only_their_assignments(self):
        self.assertEqual(self._codes_visible_to(self.officer_a), {'REQ-A'})

    def test_a_store_officer_cannot_see_another_officers_order(self):
        self.assertNotIn('REQ-B', self._codes_visible_to(self.officer_a))

    def test_unassigned_orders_are_not_shown_to_officers(self):
        """Unassigned work belongs to whoever allocates it, not to everyone."""
        self.assertNotIn('REQ-C', self._codes_visible_to(self.officer_a))

    # -- fail closed -------------------------------------------------------
    def test_a_user_with_no_order_role_sees_nothing(self):
        self.assertEqual(self._codes_visible_to(self.consultant), set())

    # -- counts must match the list ---------------------------------------
    def test_the_headline_counts_are_scoped_too(self):
        """A count of 3 above a table of 1 reads as a bug, and leaks the size
        of the national order book."""
        self.client.force_login(self.officer_a)
        resp = self.client.get(reverse('material_orders'))
        self.assertEqual(resp.context['total_orders'], 1)

    def test_management_counts_are_unscoped(self):
        self.client.force_login(self.stores_mgmt)
        resp = self.client.get(reverse('material_orders'))
        self.assertEqual(resp.context['total_orders'], 3)
