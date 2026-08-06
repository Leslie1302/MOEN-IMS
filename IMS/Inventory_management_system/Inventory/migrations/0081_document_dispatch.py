# Audit trail for release documents emailed out of the system via Microsoft
# Graph. Release paperwork authorises materials worth real money, so "who was
# this sent to, and when?" has to be answerable later — including for attempts
# that failed, so an un-actioned release is distinguishable from a rejected send.

import auto_prefetch
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0080_letterhead_continuation_top'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentDispatch',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recipients', models.TextField(help_text='Comma-separated addresses the message was actually sent to.')),
                ('include_memo', models.BooleanField(default=True)),
                ('include_letter', models.BooleanField(default=True)),
                ('subject', models.CharField(blank=True, max_length=300)),
                ('message', models.TextField(blank=True, help_text='Optional covering note added by the officer.')),
                ('status', models.CharField(choices=[('sent', 'Sent'), ('failed', 'Failed')], default='sent', max_length=10)),
                ('error', models.TextField(blank=True, help_text="Graph's error when status is 'failed'.")),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('release_letter', auto_prefetch.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='dispatches', to='Inventory.releaseletter')),
                ('sent_by', auto_prefetch.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='document_dispatches', to=settings.AUTH_USER_MODEL,
                    help_text='The officer who sent it. Graph sends on their behalf, so the '
                              'message comes from their own mailbox.')),
                ('recipient_users', models.ManyToManyField(
                    blank=True, related_name='received_document_dispatches',
                    to=settings.AUTH_USER_MODEL,
                    help_text='System users among the recipients, where the address came from a user record.')),
            ],
            options={
                'verbose_name': 'document dispatch',
                'verbose_name_plural': 'document dispatches',
                'ordering': ['-sent_at'],
                'abstract': False,
                'base_manager_name': 'prefetch_manager',
            },
            bases=(auto_prefetch.Model,),
        ),
    ]
