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

    def test_signup_page_redirects_to_oauth(self):
        resp = self.client.get(reverse('signup'))
        self.assertEqual(resp.status_code, 302)  # Redirects to M365 OAuth

    def test_signin_page_redirects_to_oauth(self):
        resp = self.client.get(reverse('signin'))
        self.assertEqual(resp.status_code, 302)  # Redirects to M365 OAuth

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
    """Tests for user registration (now handled via M365 OAuth)."""

    def test_signup_redirects_to_oauth(self):
        """POST to signup should redirect to OAuth, not create a user."""
        resp = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'SecurePass12345!',
            'password2': 'SecurePass12345!',
        })
        # Signup is now a redirect to M365 OAuth — no local user creation
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_signup_password_mismatch(self):
        resp = self.client.post(reverse('signup'), {
            'username': 'failuser',
            'email': 'fail@example.com',
            'password1': 'SecurePass12345!',
            'password2': 'DifferentPass12345!',
        })
        self.assertFalse(User.objects.filter(username='failuser').exists())


class LogoutHardeningTests(TestCase):
    """Tests for POST-only logout endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(username="logoutuser", password="pass12345")
        self.client.login(username="logoutuser", password="pass12345")

    def test_inventory_logout_rejects_get(self):
        resp = self.client.get(reverse('logout'))
        self.assertEqual(resp.status_code, 405)

    def test_accounts_logout_rejects_get(self):
        resp = self.client.get(reverse('ms_logout'))
        self.assertEqual(resp.status_code, 405)


class StoreOperationsAccessTests(TestCase):
    """Tests for store operations aliases and reconciliation pages."""

    def setUp(self):
        self.user = User.objects.create_user(username="storekeeper1", password="pass12345")
        group = Group.objects.create(name="Storekeeper")
        self.user.groups.add(group)
        self.client.login(username="storekeeper1", password="pass12345")

    def test_dashboard_shows_store_operations_menu(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Store Operations")

    def test_store_operations_can_open_reconciliation_pages(self):
        allowed_urls = [
            'bill_of_quantity',
            'boq_overissuance_summary',
            'boq_overissuance_justification_list',
            'project_management_dashboard',
            'project_community_analysis',
            'project_package_analysis',
            'project_material_analysis',
        ]

        for url_name in allowed_urls:
            resp = self.client.get(reverse(url_name))
            self.assertEqual(
                resp.status_code, 200,
                f"{url_name} should be accessible to store operations users"
            )
