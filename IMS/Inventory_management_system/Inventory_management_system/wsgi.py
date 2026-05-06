"""
WSGI config for Inventory_management_system project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/howto/deployment/wsgi/
"""

import logging
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inventory_management_system.settings')

application = get_wsgi_application()


# ---------------------------------------------------------------------------
# Emergency: auto-run migrations on container start.
#
# On Azure App Service we currently can't reach the portal to set a custom
# startup command (which is the proper place to run `manage.py migrate`).
# As a workaround we run migrations here, exactly once per worker process,
# right after the WSGI app is initialised.
#
# This is intentionally guarded behind RUN_MIGRATIONS_ON_STARTUP so it can be
# turned off the moment a real startup command / release task is wired up.
# Default is ON only when running on Azure App Service (WEBSITE_SITE_NAME set).
# ---------------------------------------------------------------------------
def _maybe_run_migrations():
    on_azure = bool(os.environ.get('WEBSITE_SITE_NAME'))
    flag = os.environ.get('RUN_MIGRATIONS_ON_STARTUP')
    if flag is not None:
        should_run = flag.lower() in ('1', 'true', 'yes')
    else:
        should_run = on_azure  # default: only on Azure
    if not should_run:
        return
    try:
        from django.core.management import call_command
        call_command('migrate', '--noinput')
        logging.getLogger(__name__).info("Startup migrations completed.")
    except Exception:  # noqa: BLE001
        # Never let migration failures stop the app from booting -- we'd rather
        # serve a 500 from a specific endpoint than have the whole site down.
        logging.getLogger(__name__).exception("Startup migrations failed.")


_maybe_run_migrations()
