from django.contrib.auth.models import User
from django.db import models
import auto_prefetch


class DocumentDispatch(auto_prefetch.Model):
    """
    A record of release documents being emailed to someone.

    Release paperwork leaving the system is an auditable event: the memo and
    letter authorise materials worth real money, and "who did you send it to?"
    has to be answerable months later. Every attempt is recorded — including
    failures, so a release that looks un-actioned can be distinguished from one
    where Graph rejected the send.

    Recipients are stored as resolved email addresses alongside the user rows
    they came from, because a user's address can change afterwards and the
    audit needs to say where the document actually went at the time.
    """

    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    release_letter = auto_prefetch.ForeignKey(
        'Inventory.ReleaseLetter', on_delete=models.CASCADE,
        related_name='dispatches')

    sent_by = auto_prefetch.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='document_dispatches',
        help_text="The officer who sent it. Graph sends on their behalf, so the "
                  "message comes from their own mailbox.")
    recipients = models.TextField(
        help_text="Comma-separated addresses the message was actually sent to.")
    recipient_users = models.ManyToManyField(
        User, blank=True, related_name='received_document_dispatches',
        help_text="System users among the recipients, where the address came from a user record.")

    include_memo = models.BooleanField(default=True)
    include_letter = models.BooleanField(default=True)
    # The versions actually sent. Without these the history implies the document
    # on file today is what the recipient received — false as soon as anything
    # is regenerated, and the QR would not catch it because it encodes the
    # release code, not the version.
    memo_version = models.PositiveIntegerField(default=0)
    letter_version = models.PositiveIntegerField(default=0)
    subject = models.CharField(max_length=300, blank=True)
    message = models.TextField(blank=True, help_text="Optional covering note added by the officer.")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sent')
    error = models.TextField(blank=True, help_text="Graph's error when status is 'failed'.")
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta(auto_prefetch.Model.Meta):
        ordering = ['-sent_at']
        verbose_name = 'document dispatch'
        verbose_name_plural = 'document dispatches'

    def __str__(self):
        return f"{self.release_letter_id} -> {self.recipients} ({self.status})"

    @property
    def recipient_list(self):
        return [a.strip() for a in (self.recipients or '').split(',') if a.strip()]

    @property
    def documents_label(self):
        parts = []
        if self.include_memo:
            parts.append('memo')
        if self.include_letter:
            parts.append('letter')
        return ' + '.join(parts) or 'no attachments'
