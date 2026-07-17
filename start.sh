#!/bin/bash
cd IMS/Inventory_management_system
# Apply migrations on every start — idempotent, no-op when up to date.
# (Azure ignores the Procfile 'release:' phase; this is the real hook.)
python manage.py migrate --noinput
gunicorn Inventory_management_system.wsgi
