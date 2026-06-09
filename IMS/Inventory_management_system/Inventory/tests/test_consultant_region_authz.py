"""
Confidentiality scoping for the consultant dashboard.

`consultant_dash` rendered MaterialOrder.objects.all() — so an external
consultant saw every order nationwide. It now restricts external consultants
to orders in the region(s) their ProjectConsultant binding covers; internal
staff / Management / superusers are unrestricted; an unbound consultant sees
nothing (fail closed).
"""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group

from Inventory.models import Unit, MaterialOrder, ProjectConsultant


class ConsultantDashRegionScopingTests(TestCase):
    def setUp(self):
        self.unit = Unit.objects.create(name="each")
        self.order_accra = MaterialOrder.objects.create(
            name="Pole-A", quantity=Decimal("1"), unit=self.unit, region="Greater Accra"
        )
        self.order_ashanti = MaterialOrder.objects.create(
            name="Pole-B", quantity=Decimal("1"), unit=self.unit, region="Ashanti"
        )
        self.consultants = Group.objects.get_or_create(name="Consultants")[0]

    def _order_ids(self, resp):
        return {o.id for o in resp.context["orders"]}

    def test_bound_consultant_sees_only_their_region(self):
        cons = User.objects.create_user("cons_accra", password="pw")
        cons.groups.add(self.consultants)
        ProjectConsultant.objects.create(
            name="Accra Consult", user=cons, region="Greater Accra", active=True
        )
        self.client.login(username="cons_accra", password="pw")
        resp = self.client.get(reverse("consultant_dash"))
        ids = self._order_ids(resp)
        self.assertIn(self.order_accra.id, ids)
        self.assertNotIn(self.order_ashanti.id, ids)

    def test_unbound_consultant_sees_nothing(self):
        cons = User.objects.create_user("cons_none", password="pw")
        cons.groups.add(self.consultants)  # in group, but no ProjectConsultant binding
        self.client.login(username="cons_none", password="pw")
        resp = self.client.get(reverse("consultant_dash"))
        self.assertEqual(self._order_ids(resp), set())

    def test_management_user_sees_all_regions(self):
        mgr = User.objects.create_user("mgr", password="pw")
        mgr.groups.add(Group.objects.get_or_create(name="Management")[0])
        self.client.login(username="mgr", password="pw")
        resp = self.client.get(reverse("consultant_dash"))
        ids = self._order_ids(resp)
        self.assertIn(self.order_accra.id, ids)
        self.assertIn(self.order_ashanti.id, ids)

    def test_superuser_sees_all_regions(self):
        User.objects.create_superuser("root", "r@e.com", "pw")
        self.client.login(username="root", password="pw")
        resp = self.client.get(reverse("consultant_dash"))
        ids = self._order_ids(resp)
        self.assertIn(self.order_accra.id, ids)
        self.assertIn(self.order_ashanti.id, ids)
