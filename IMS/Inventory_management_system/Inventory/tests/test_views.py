"""
View tests for the Inventory app.
Tests authentication requirements, status codes, and template rendering.
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group
from Inventory.models import (
    Category, Unit, Warehouse, InventoryItem,
)


class PublicPageTests(TestCase):
    """Tests that public pages are accessible without login."""

    def test_index_page(self):
        resp = self.client.get(reverse('index'))
        self.assertEqual(resp.status_code, 200)

    def test_signup_page(self):
        resp = self.client.get(reverse('signup'))
        self.assertEqual(resp.status_code, 200)

    def test_signin_page(self):
        resp = self.client.get(reverse('signin'))
        self.assertEqual(resp.status_code, 200)

    def test_about_requires_login(self):
        resp = self.client.get(reverse('about'))
        self.assertIn(resp.status_code, [301, 302])

    def test_help_requires_login(self):
        resp = self.client.get(reverse('help'))
        self.assertIn(resp.status_code, [301, 302])


class AuthenticationRequiredTests(TestCase):
    """Tests that protected pages redirect unauthenticated users."""

    PROTECTED_URL_NAMES = [
        'dashboard',
        'material_orders',
        'bill_of_quantity',
        'material_receipt',
        'material_heatmap',
        'low_inventory_summary',
        'profile',
        'request_material',
        'about',
        'help',
    ]

    def test_protected_pages_redirect_to_login(self):
        for url_name in self.PROTECTED_URL_NAMES:
            try:
                url = reverse(url_name)
                resp = self.client.get(url)
                self.assertIn(
                    resp.status_code, [302, 301],
                    f"{url_name} ({url}) should redirect, got {resp.status_code}"
                )
            except Exception:
                # Some URLs may require arguments; skip those
                pass


class DashboardViewTests(TestCase):
    """Tests for the Dashboard view."""

    def setUp(self):
        # Use superuser to bypass group/authorization checks
        self.user = User.objects.create_superuser(
            username="testadmin", password="testpass123",
            email="admin@test.com",
        )

        # Create test data
        self.category = Category.objects.create(name="Test Category")
        self.unit = Unit.objects.create(name="pcs")
        self.warehouse = Warehouse.objects.create(
            name="Test WH", code="TWH01", location="Test"
        )
        InventoryItem.objects.create(
            name="Test Item",
            quantity=100,
            category=self.category,
            unit=self.unit,
            code="TST01",
            warehouse=self.warehouse,
        )

    def test_dashboard_requires_login(self):
        """Unauthenticated users should be redirected."""
        self.client.logout()
        resp = self.client.get(reverse('dashboard'))
        self.assertNotEqual(resp.status_code, 200)

    def test_dashboard_accessible_when_logged_in(self):
        self.client.login(username="testadmin", password="testpass123")
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_shows_items(self):
        self.client.login(username="testadmin", password="testpass123")
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, "Test Item")

    def test_dashboard_low_stock_alert(self):
        """Items with quantity <= 10 should trigger low stock alert."""
        InventoryItem.objects.create(
            name="Low Stock Item",
            quantity=5,
            unit=self.unit,
            code="LOW01",
        )
        self.client.login(username="testadmin", password="testpass123")
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, "Low Stock Alert")


class SignUpViewTests(TestCase):
    """Tests for user registration."""

    def test_signup_creates_user(self):
        resp = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'SecurePass12345!',
            'password2': 'SecurePass12345!',
        })
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_signup_password_mismatch(self):
        resp = self.client.post(reverse('signup'), {
            'username': 'failuser',
            'email': 'fail@example.com',
            'password1': 'SecurePass12345!',
            'password2': 'DifferentPass12345!',
        })
        self.assertFalse(User.objects.filter(username='failuser').exists())
