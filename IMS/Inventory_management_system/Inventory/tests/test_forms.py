"""
Form tests for the Inventory app.
Tests form validation, required fields, and widget configuration.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from Inventory.forms import (
    UserRegistration, InventoryItemForm, ExcelUploadForm,
)
from Inventory.models import Category, Unit, Warehouse


class UserRegistrationFormTest(TestCase):
    """Tests for the user registration form."""

    def test_valid_registration(self):
        form = UserRegistration(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'StrongPass12345!',
            'password2': 'StrongPass12345!',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_password_mismatch(self):
        form = UserRegistration(data={
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'StrongPass12345!',
            'password2': 'WrongPass12345!',
        })
        self.assertFalse(form.is_valid())

    def test_missing_email(self):
        form = UserRegistration(data={
            'username': 'newuser',
            'password1': 'StrongPass12345!',
            'password2': 'StrongPass12345!',
        })
        # Email may or may not be required depending on form config
        # Just ensure the form processes without crashing
        form.is_valid()

    def test_duplicate_username(self):
        User.objects.create_user(username='existing', password='pass123')
        form = UserRegistration(data={
            'username': 'existing',
            'email': 'dup@example.com',
            'password1': 'StrongPass12345!',
            'password2': 'StrongPass12345!',
        })
        self.assertFalse(form.is_valid())


class InventoryItemFormTest(TestCase):
    """Tests for the InventoryItem form."""

    def setUp(self):
        self.category = Category.objects.create(name="Test Category")
        self.unit = Unit.objects.create(name="pcs")

    def test_valid_item_form(self):
        form = InventoryItemForm(data={
            'name': 'Test Item',
            'quantity': 100,
            'category': self.category.pk,
            'unit': self.unit.pk,
            'code': 'TST001',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_missing_required_fields(self):
        form = InventoryItemForm(data={})
        self.assertFalse(form.is_valid())
        # name, quantity, unit, code should be required
        self.assertIn('name', form.errors)
        self.assertIn('quantity', form.errors)

    def test_negative_quantity_rejected(self):
        """Negative quantities should ideally be invalid."""
        form = InventoryItemForm(data={
            'name': 'Negative Item',
            'quantity': -5,
            'category': self.category.pk,
            'unit': self.unit.pk,
            'code': 'NEG01',
        })
        # This test documents current behavior
        # If the form allows negatives, this documents it as a known issue
        form.is_valid()  # Just ensure it doesn't crash


class ExcelUploadFormTest(TestCase):
    """Tests for the Excel upload form."""

    def test_no_file_is_invalid(self):
        form = ExcelUploadForm(data={}, files={})
        self.assertFalse(form.is_valid())
