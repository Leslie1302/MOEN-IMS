from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
import auto_prefetch

def _fernet():
    return Fernet(settings.TOKEN_ENCRYPTION_KEY.encode())

class MicrosoftCredentials(auto_prefetch.Model):
    user = auto_prefetch.OneToOneField(User, on_delete=models.CASCADE, related_name='microsoft_credentials')
    ms_id = models.CharField(max_length=128, blank=True, null=True, unique=True)
    ms_email = models.EmailField(blank=True, null=True)
    _access_token = models.TextField(db_column="access_token", blank=True, null=True)
    _refresh_token = models.TextField(db_column="refresh_token", blank=True, null=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)

    class Meta(auto_prefetch.Model.Meta):
        verbose_name_plural = "Microsoft Credentials"

    @property
    def access_token(self):
        if not self._access_token:
            return None
        return _fernet().decrypt(self._access_token.encode()).decode()

    @access_token.setter
    def access_token(self, value):
        self._access_token = _fernet().encrypt(value.encode()).decode() if value else None

    @property
    def refresh_token(self):
        if not self._refresh_token:
            return None
        return _fernet().decrypt(self._refresh_token.encode()).decode()

    @refresh_token.setter
    def refresh_token(self, value):
        self._refresh_token = _fernet().encrypt(value.encode()).decode() if value else None

    def is_token_expired(self):
        from django.utils import timezone
        if not self.token_expires_at:
            return True
        return timezone.now() >= self.token_expires_at

    def __str__(self):
        return f"M365 Credentials for {self.user.username}"
