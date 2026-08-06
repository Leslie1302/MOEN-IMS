#!/bin/bash
# Azure App Service Startup Command: bash start.sh
# The GitHub workflow deploys only IMS/Inventory_management_system/, so THIS is
# the start script Azure runs (the repo-root start.sh never reaches Azure).
#
# NOTE: if the Startup Command in the Azure Portal is not set to `bash start.sh`,
# none of this runs — App Service falls back to its own gunicorn guess, and you
# get an app with no migrations applied and no PDF rendering.
set -e

# ── WeasyPrint native libraries ──────────────────────────────────────────────
# App Service's filesystem is rebuilt on every restart, so these must be
# installed at boot rather than baked in. WeasyPrint >= 53 needs Pango, its
# FreeType bridge and harfbuzz; it no longer uses cairo. libglib2.0-0 supplies
# libgobject-2.0, which is the one that surfaces in the error message when the
# set is incomplete.
#
# ponytail: apt-at-boot is the cheapest reversible path. If cold starts get
# painful, move to a custom container image with these baked into a layer.
WEASY_LIBS="libglib2.0-0 libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libgdk-pixbuf-2.0-0 libffi8"

if command -v apt-get >/dev/null 2>&1; then
  echo "[start.sh] Installing WeasyPrint native libraries..."
  # Deliberately NOT swallowing stderr: a silent failure here produces an app
  # that looks healthy but cannot mint a single document.
  if apt-get update -qq && apt-get install -y -qq --no-install-recommends $WEASY_LIBS; then
    echo "[start.sh] Native libraries installed."
  else
    echo "[start.sh] WARNING: apt install failed. PDF generation will be unavailable."
    echo "[start.sh] Packages attempted: $WEASY_LIBS"
  fi
else
  echo "[start.sh] WARNING: apt-get unavailable; skipping native library install."
fi

# Fail loudly in the log if WeasyPrint still cannot load. The app is still
# usable for everything else, so this warns rather than aborts the boot.
python - <<'PY' || true
try:
    import weasyprint
    print(f"[start.sh] WeasyPrint {weasyprint.__version__} ready.")
except Exception as exc:
    print(f"[start.sh] WARNING: WeasyPrint unusable -> {exc}")
    print("[start.sh] Release memos/letters will NOT be generated until this is fixed.")
PY

# ── Database ─────────────────────────────────────────────────────────────────
# Apply migrations on every start — idempotent, no-op when up to date.
python manage.py migrate --noinput

exec gunicorn Inventory_management_system.wsgi --bind=0.0.0.0:${PORT:-8000} --log-file -
