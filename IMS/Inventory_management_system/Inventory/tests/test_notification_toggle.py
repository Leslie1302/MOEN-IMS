"""Global email on/off switch, toggled from the admin portal.

The toggle suppresses AUTOMATIC notification emails at
signals._trigger_email_notification; in-app notifications still get created.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from Inventory.models import NotificationSetting, Notification

User = get_user_model()


class NotificationSettingModelTests(TestCase):
    def test_singleton_and_default_on(self):
        a = NotificationSetting.load()
        b = NotificationSetting.load()
        self.assertEqual(a.pk, 1)
        self.assertEqual(b.pk, 1)
        self.assertTrue(NotificationSetting.emails_are_enabled())

    def test_toggle_off_persists(self):
        s = NotificationSetting.load()
        s.emails_enabled = False
        s.save()
        self.assertFalse(NotificationSetting.emails_are_enabled())
        self.assertEqual(NotificationSetting.objects.count(), 1)  # still one row


class EmailGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from accounts.models import MicrosoftCredentials
        mgmt, _ = Group.objects.get_or_create(name='Management')
        cls.recipient = User.objects.create_user('mgr', email='m@x.test', password='x')
        cls.recipient.groups.add(mgmt)
        # A sender with M365 creds must exist or the email path bails before send.
        cls.sender = User.objects.create_superuser('root', 'r@x.test', 'x')
        MicrosoftCredentials.objects.create(user=cls.sender)  # existence is enough

    def _notif(self):
        # A stand-in Notification so no post_save side effects fire during the test.
        from unittest.mock import MagicMock
        n = MagicMock()
        n.id = 1
        n.recipient_user = None
        n.recipient_group = 'Management'
        n.sender = None
        n.title = 'T'
        n.message = 'M'
        return n

    def _set(self, enabled):
        s = NotificationSetting.load()
        s.emails_enabled = enabled
        s.save()

    # NOTE: signals.py does `from accounts.notifications import send_email_notification`
    # at module scope, so the patch target is Inventory.signals, not accounts.notifications.
    @patch('Inventory.signals.send_email_notification')
    def test_disabled_suppresses_email(self, mock_send):
        from Inventory.signals import _trigger_email_notification
        self._set(False)
        _trigger_email_notification(self._notif())
        mock_send.assert_not_called()   # gate short-circuits before the send

    @patch('Inventory.signals.send_email_notification')
    def test_enabled_sends(self, mock_send):
        from Inventory.signals import _trigger_email_notification
        self._set(True)
        _trigger_email_notification(self._notif())
        self.assertTrue(mock_send.called)


class AdminToggleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser('root', 'r@x.test', 'x')

    def test_toggle_button_flips_state(self):
        self.client.force_login(self.admin)
        self.assertTrue(NotificationSetting.emails_are_enabled())
        url = reverse('admin:Inventory_notificationsetting_toggle')
        self.client.post(url)
        self.assertFalse(NotificationSetting.emails_are_enabled())
        self.client.post(url)
        self.assertTrue(NotificationSetting.emails_are_enabled())

    def test_changelist_shows_status(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('admin:Inventory_notificationsetting_changelist'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Email Notifications')
