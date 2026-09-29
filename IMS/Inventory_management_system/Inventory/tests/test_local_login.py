"""Password login exists on localhost with DEBUG only — never in production."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings


class LocalDevLoginTests(TestCase):
    def setUp(self):
        User.objects.create_user('tester', password='pw-12345')

    @override_settings(DEBUG=True)
    def test_localhost_with_debug_logs_in_with_a_password(self):
        resp = self.client.post('/auth/login/', {'username': 'tester', 'password': 'pw-12345'},
                                HTTP_HOST='localhost:8000')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)

    @override_settings(DEBUG=False, ALLOWED_HOSTS=['localhost', 'moen-ims.org'])
    def test_no_debug_still_goes_to_microsoft(self):
        with patch('accounts.views._msal_app') as app:
            app.return_value.get_authorization_request_url.return_value = 'https://login.microsoftonline.com/x'
            resp = self.client.get('/auth/login/', HTTP_HOST='localhost')
        self.assertTrue(resp['Location'].startswith('https://login.microsoftonline.com'))

    @override_settings(DEBUG=True, ALLOWED_HOSTS=['moen-ims.org'])
    def test_real_host_still_goes_to_microsoft(self):
        with patch('accounts.views._msal_app') as app:
            app.return_value.get_authorization_request_url.return_value = 'https://login.microsoftonline.com/x'
            resp = self.client.get('/auth/login/', HTTP_HOST='moen-ims.org')
        self.assertTrue(resp['Location'].startswith('https://login.microsoftonline.com'))

    @override_settings(DEBUG=True)
    def test_localhost_shows_the_form(self):
        resp = self.client.get('/auth/login/', HTTP_HOST='localhost:8000')
        self.assertContains(resp, 'name="password"')
