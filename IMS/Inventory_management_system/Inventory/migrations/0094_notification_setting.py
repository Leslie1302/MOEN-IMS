# Global on/off switch for outgoing notification emails (singleton), toggled
# from the admin portal.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0093_remove_area_project_scoping'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationSetting',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('emails_enabled', models.BooleanField(
                    default=True,
                    help_text='When OFF, the system sends NO automatic notification emails. '
                              'In-app notifications still work.')),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'notification setting',
                'verbose_name_plural': 'notification settings',
            },
        ),
    ]
