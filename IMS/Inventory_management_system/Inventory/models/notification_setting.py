from django.db import models
from django.contrib.auth.models import User


class NotificationSetting(models.Model):
    """Global on/off switch for outgoing notification emails, toggled from admin.

    A singleton (always pk=1). When ``emails_enabled`` is False the automatic
    notification emails (new request, BoQ update, receipts, bulk-request
    summaries, …) are suppressed at ``signals._trigger_email_notification``.
    In-app notifications are unaffected, and deliberate one-off sends (emailing a
    release document, a BoQ-assistance request) still go out — those are explicit
    user actions, not notifications.
    """

    emails_enabled = models.BooleanField(
        default=True,
        help_text="When OFF, the system sends NO automatic notification emails. "
                  "In-app notifications still work.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = 'notification setting'
        verbose_name_plural = 'notification settings'

    def __str__(self):
        return f"Email notifications: {'ON' if self.emails_enabled else 'OFF'}"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def emails_are_enabled(cls) -> bool:
        """Cheap read used on every send. Fails OPEN: a config/DB hiccup (or the
        table not existing yet during a deploy) must not silently drop all email."""
        try:
            return cls.load().emails_enabled
        except Exception:
            return True
