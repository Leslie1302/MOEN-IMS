"""
Object-level authorization tests for the item Edit/Delete views.

`is_staff` alone is not authorisation. These tests pin the guard added to
`item_views.EditItem`/`DeleteItem`: a staff user scoped to one group must
not be able to edit or delete another group's stock via the URL pk (IDOR),
while remaining able to manage their own group's items. Superusers and
Management retain full access.
"""
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group

from Inventory.models import Category, Unit, Warehouse, InventoryItem


class ItemEditDeleteAuthorizationTests(TestCase):
    def setUp(self):
        self.group_a = Group.objects.create(name="GroupA")
        self.group_b = Group.objects.create(name="GroupB")

        # Staff user belonging only to GroupA.
        self.user_a = User.objects.create_user(
            username="staff_a", password="pass12345", is_staff=True
        )
        self.user_a.groups.add(self.group_a)

        self.category = Category.objects.create(name="Cat")
        self.unit = Unit.objects.create(name="pcs")
        self.warehouse = Warehouse.objects.create(
            name="WH", code="WH01", location="x"
        )

        # One item owned by each group.
        self.item_a = InventoryItem.objects.create(
            name="Item A", quantity=100, category=self.category,
            unit=self.unit, code="A01", warehouse=self.warehouse,
            group=self.group_a,
        )
        self.item_b = InventoryItem.objects.create(
            name="Item B", quantity=100, category=self.category,
            unit=self.unit, code="B01", warehouse=self.warehouse,
            group=self.group_b,
        )

        self.client.login(username="staff_a", password="pass12345")

    # --- cross-group access is denied (404, not 403: don't leak existence) ---

    def test_edit_other_group_item_returns_404(self):
        resp = self.client.get(reverse("edit-item", args=[self.item_b.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_delete_other_group_item_get_returns_404(self):
        resp = self.client.get(reverse("delete-item", args=[self.item_b.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_delete_other_group_item_post_does_not_delete(self):
        self.client.post(reverse("delete-item", args=[self.item_b.pk]))
        self.assertTrue(InventoryItem.objects.filter(pk=self.item_b.pk).exists())

    # --- own-group access still works ---

    def test_edit_own_group_item_allowed(self):
        resp = self.client.get(reverse("edit-item", args=[self.item_a.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_delete_own_group_item_allowed(self):
        resp = self.client.post(reverse("delete-item", args=[self.item_a.pk]))
        self.assertEqual(resp.status_code, 302)  # redirect to success_url
        self.assertFalse(InventoryItem.objects.filter(pk=self.item_a.pk).exists())

    # --- superuser bypasses scoping ---

    def test_superuser_can_edit_any_group_item(self):
        User.objects.create_superuser(
            username="root", password="pass12345", email="r@e.com"
        )
        self.client.login(username="root", password="pass12345")
        resp = self.client.get(reverse("edit-item", args=[self.item_b.pk]))
        self.assertEqual(resp.status_code, 200)

    # --- Management group bypasses scoping ---

    def test_management_can_edit_any_group_item(self):
        # "Management" is seeded by migration 0031_create_canonical_groups,
        # so get_or_create avoids a UNIQUE-constraint clash.
        mgmt, _ = Group.objects.get_or_create(name="Management")
        manager = User.objects.create_user(
            username="manager", password="pass12345", is_staff=True
        )
        manager.groups.add(mgmt)
        self.client.login(username="manager", password="pass12345")
        resp = self.client.get(reverse("edit-item", args=[self.item_b.pk]))
        self.assertEqual(resp.status_code, 200)
