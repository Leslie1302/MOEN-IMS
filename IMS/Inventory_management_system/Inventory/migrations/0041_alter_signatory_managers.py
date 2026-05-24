# Originally meant to capture the auto_prefetch `prefetch_manager` on
# Signatory, but Django's migration serializer cannot deconstruct managers
# generated via `models.Manager.from_queryset()` (which is what
# auto_prefetch.Manager is). The error path is documented in Django's
# manager.py: `Could not find manager ManagerFromQuerySet in
# django.db.models.manager.`
#
# This migration is now a no-op so the chain stays linear. The cosmetic
# "Change managers on signatory" autodetector warning will reappear on
# every `makemigrations --check`, but the runtime is unaffected: the
# Signatory model still inherits prefetch_manager from auto_prefetch.Model
# via class inheritance, and queries route through it correctly.
#
# If we ever want to silence the warning permanently, the fix is to
# subclass auto_prefetch.Manager in the Signatory model file:
#     class SignatoryManager(auto_prefetch.Manager):
#         pass
# and then list that subclass in the migration's managers=[] tuple.
# Not worth the noise for a cosmetic check warning.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('Inventory', '0040_transport_awaiting_choice'),
    ]

    operations = []
