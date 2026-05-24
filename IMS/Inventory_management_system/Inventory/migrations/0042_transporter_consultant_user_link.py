"""
Phase C.3 + transporter parity:
  - Add `user` FK from Transporter to auth.User
  - Add `user` FK from ProjectConsultant to auth.User

Both are nullable + SET_NULL on delete so existing rows survive and a
transporter / consultant created before a domain account is provisioned
remains valid. Once the FK is set, the user's dashboard scopes to the
company and they receive in-system alerts via the existing notification
infrastructure.
"""

import auto_prefetch
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0041_alter_signatory_managers'),
        # AUTH_USER_MODEL pulls in the right user model migration
        # regardless of project setup.
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='transporter',
            name='user',
            field=auto_prefetch.ForeignKey(
                blank=True,
                help_text='Domain account that operates this transport company. '
                          'Receives in-system alerts when transports are assigned.',
                null=True,
                on_delete=models.SET_NULL,
                related_name='transporter_company',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='projectconsultant',
            name='user',
            field=auto_prefetch.ForeignKey(
                blank=True,
                help_text='Domain account for this consultant. Receives in-system '
                          'alerts when SHEP releases are bound to this consultancy.',
                null=True,
                on_delete=models.SET_NULL,
                related_name='project_consultancy',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
