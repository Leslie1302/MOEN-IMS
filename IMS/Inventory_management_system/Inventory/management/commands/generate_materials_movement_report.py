"""Weekly materials movement report — scheduled run.

Summarises the previous calendar week's stock movements and notifies
stakeholders in-app + by email (create_notification does both), with a link to
the full report page. Run from a weekly scheduler (e.g. Monday 06:00):

    python manage.py generate_materials_movement_report

Flags:
    --weeks-back N   report the week N weeks before this one (default 1)
    --dry-run        build and print the summary, send nothing
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from Inventory.services.movement_report import build_report


class Command(BaseCommand):
    help = "Generate and send the weekly materials movement report."

    def add_arguments(self, parser):
        parser.add_argument('--weeks-back', type=int, default=1)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        today = timezone.localdate()
        # Monday of the target week, then its Sunday.
        this_monday = today - timedelta(days=today.weekday())
        d_from = this_monday - timedelta(weeks=opts['weeks_back'])
        d_to = d_from + timedelta(days=6)

        rep = build_report(d_from, d_to)
        t = rep['totals']
        label = f"{d_from:%d %b} – {d_to:%d %b %Y}"
        link = f"/reports/movement/?period=custom&from={d_from}&to={d_to}"
        groups = ('Management', 'Stores Management')

        text_summary = (
            f"Week {label}: {t['materials']} material(s) moved across "
            f"{t['movements']} movement(s). Received {t['received']:.0f}, "
            f"issued {t['issued']:.0f}.")
        self.stdout.write(text_summary)
        if opts['dry_run']:
            self.stdout.write(self.style.WARNING("Dry run — nothing sent."))
            return

        self._email(rep, label, link, groups)        # rich HTML email
        self._notify(text_summary, label, link, groups)  # in-app, no extra email
        self.stdout.write(self.style.SUCCESS("Weekly movement report dispatched."))

    # -- rich HTML email (summary table embedded), sent via M365 --
    def _email(self, rep, label, link, groups):
        from django.conf import settings
        from django.contrib.auth.models import User
        from django.template.loader import render_to_string

        from Inventory.models import NotificationSetting
        if not NotificationSetting.emails_are_enabled():
            self.stdout.write("Email notifications globally disabled — email skipped.")
            return

        recipients = list(
            User.objects.filter(groups__name__in=groups, is_active=True)
            .exclude(email='').values_list('email', flat=True).distinct())
        if not recipients:
            self.stdout.write("No recipients with email — email skipped.")
            return

        sender = User.objects.filter(
            is_superuser=True, microsoft_credentials__isnull=False).first()
        if not sender:
            self.stdout.write("No M365 sender available — email skipped.")
            return

        CAP = 60
        body = render_to_string('Inventory/emails/materials_movement_report.html', {
            'period_label': label,
            'totals': rep['totals'],
            'summary': rep['summary'][:CAP],
            'more_count': max(0, len(rep['summary']) - CAP),
            'link': link,
            'base_url': getattr(settings, 'BASE_URL', ''),
        })
        from accounts.notifications import send_email_notification
        try:
            send_email_notification(
                user=sender, to=recipients,
                subject=f"[MOEN-IMS] Weekly Materials Movement — {label}",
                body=body, body_type="HTML")
            self.stdout.write(f"Rich email sent to {len(recipients)} recipient(s).")
        except Exception as e:
            self.stderr.write(f"Email failed: {e}")

    # -- in-app notifications only (created directly so they don't re-send a
    #    second, plain email on top of the rich one above) --
    def _notify(self, text_summary, label, link, groups):
        from Inventory.models import Notification
        for group in groups:
            Notification.objects.create(
                notification_type='staff_prompt',
                title=f"Weekly Materials Movement Report — {label}",
                message=f"{text_summary} View: {link}",
                recipient_group=group)
