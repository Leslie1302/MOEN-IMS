#!/bin/bash
# Azure App Service Startup Command: bash start.sh
# The GitHub workflow deploys only IMS/Inventory_management_system/, so THIS is
# the start script Azure runs (the repo-root start.sh never reaches Azure).
set -e

# WeasyPrint's native deps for HTML->PDF (release memo/letter). apt is available
# as root on the Oryx runtime image; this is a no-op once the layer is cached.
# ponytail: apt-at-boot, cheapest path. Move to a custom container if boots slow.
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libcairo2 libffi-dev \
    2>/dev/null || echo "WARN: apt install of WeasyPrint libs failed; PDF gen may error."
fi

# Apply migrations on every start — idempotent, no-op when up to date.
python manage.py migrate --noinput

exec gunicorn Inventory_management_system.wsgi --bind=0.0.0.0:${PORT:-8000} --log-file -
