"""
Model tests for the Inventory app.
Tests core model creation, string representations, constraints, and relationships.
"""
from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.db import IntegrityError
from Inventory.models import (
    Category, Unit, Warehouse, InventoryItem, Supplier,
    MaterialOrder, Profile,
)


class CategoryModelTest(TestCase):
    """Tests for the Category model."""

    def test_create_category(self):
        cat = Category.objects.create(name="Electrical")
        self.assertEqual(str(cat), "Electrical")

    def test_category_verbose_name_plural(self):
        self.assertEqual(Category._meta.verbose_name_plural, "categories")


class UnitModelTest(TestCase):
    """Tests for the Unit model."""

    def test_create_unit(self):
        unit = Unit.objects.create(name="kg")
        self.assertEqual(str(unit), "kg")

    def test_unit_verbose_name_plural(self):
        self.assertEqual(Unit._meta.verbose_name_plural, "units")


class WarehouseModelTest(TestCase):
    """Tests for the Warehouse model."""

    def setUp(self):
        self.warehouse = Warehouse.objects.create(
            name="Main Store",
            code="MS001",
            location="Accra",
        )

    def test_str_representation(self):
        self.assertEqual(str(self.warehouse), "Main Store (MS001)")

    def test_unique_code_constraint(self):
        with self.assertRaises(IntegrityError):
            Warehouse.objects.create(
                name="Duplicate",
                code="MS001",
                location="Kumasi",
            )

    def test_is_active_default(self):
        self.assertTrue(self.warehouse.is_active)

    def test_optional_contact_fields(self):
        w = Warehouse.objects.create(name="Empty", code="EM01", location="N/A")
        self.assertIsNone(w.contact_person)
        self.assertIsNone(w.contact_phone)
        self.assertIsNone(w.contact_email)


class InventoryItemModelTest(TestCase):
    """Tests for the InventoryItem model."""

    def setUp(self):
        self.category = Category.objects.create(name="Cables")
        self.unit = Unit.objects.create(name="m")
        self.warehouse = Warehouse.objects.create(
            name="WH1", code="WH001", location="Tema"
        )
        self.item = InventoryItem.objects.create(
            name="16mm Cable",
            quantity=500,
            category=self.category,
            code="CCA001",
            unit=self.unit,
            warehouse=self.warehouse,
        )

    def test_str_representation(self):
        self.assertEqual(str(self.item), "16mm Cable")

    def test_unique_together_code_warehouse(self):
        """Same code + warehouse combination should fail."""
        with self.assertRaises(IntegrityError):
            InventoryItem.objects.create(
                name="Duplicate",
                quantity=1,
                code="CCA001",
                unit=self.unit,
                warehouse=self.warehouse,
            )

    def test_same_code_different_warehouse_allowed(self):
        """Same code but different warehouse should succeed."""
        other_wh = Warehouse.objects.create(
            name="WH2", code="WH002", location="Accra"
        )
        item2 = InventoryItem.objects.create(
            name="16mm Cable (WH2)",
            quantity=100,
            code="CCA001",
            unit=self.unit,
            warehouse=other_wh,
        )
        self.assertEqual(item2.code, "CCA001")

    def test_category_nullable(self):
        item = InventoryItem.objects.create(
            name="Uncategorised",
            quantity=10,
            code="UNC01",
            unit=self.unit,
        )
        self.assertIsNone(item.category)

    def test_default_ordering(self):
        InventoryItem.objects.create(
            name="AAA First",
            quantity=1,
            code="AAA01",
            unit=self.unit,
        )
        items = InventoryItem.objects.all()
        # Ordering is alphabetical by name; '1' < 'A' lexicographically
        self.assertEqual(items.first().name, "16mm Cable")


class ProfileModelTest(TestCase):
    """Tests for the Profile model (auto-created via signal)."""

    def test_profile_auto_created(self):
        """Profile should be auto-created when a user is created."""
        user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.assertTrue(hasattr(user, 'profile'))
        self.assertIsInstance(user.profile, Profile)

    def test_profile_str(self):
        user = User.objects.create_user(
            username="testuser", password="testpass123"
        )
        self.assertIn("testuser", str(user.profile))
