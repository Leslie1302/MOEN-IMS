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
# installed at boot rather than baked in.
#
# **glib must be named explicitly.** An earlier version of this list left it out,
# reasoning that glib/gobject/libffi arrive as Pango dependencies. They do — but
# that is not the same thing as being loadable, and WeasyPrint does not go
# through Pango to reach gobject. `weasyprint/text/ffi.py` calls
#
#     dlopen(ffi, 'gobject-2.0-0', 'gobject-2.0', 'libgobject-2.0-0', ...)
#
# directly, by soname. Installed-as-a-dependency was not enough, and the boot
# ended in:
#
#     OSError: cannot load library 'libgobject-2.0-0': cannot open shared
#     object file: No such file or directory
#
# with an app that came up healthy and could not mint a single document.
#
# The rename matters here too. Ubuntu 24.04 (noble) moved glib in the 64-bit
# time_t transition, so the package is `libglib2.0-0t64` and `libglib2.0-0` does
# not exist. Both names are listed: exactly one will resolve on any given image,
# and the per-package retry below tolerates the other failing. That is why the
# retry loop exists — the batch install aborts wholesale on one bad name.
#
# ponytail: apt-at-boot is the cheapest reversible path, and it re-runs on every
# cold start because App Service rebuilds the filesystem. If this gets painful,
# or if a transient apt failure taking out document generation stops being
# acceptable, move to a custom container image with these baked into a layer.
WEASY_LIBS="libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libgdk-pixbuf-2.0-0"
# Tried in order; the first that installs wins. Listing both spellings is
# deliberate — see the note on the noble rename above.
GLIB_LIBS="libglib2.0-0t64 libglib2.0-0"

if command -v apt-get >/dev/null 2>&1; then
  echo "[start.sh] Installing WeasyPrint native libraries..."

  apt-get update -qq || echo "[start.sh] WARNING: apt-get update failed."

  # glib first, and on its own. It is the one WeasyPrint dlopens by name, so a
  # boot without it is a boot with no renderer — whereas a missing harfbuzz
  # merely degrades text shaping. Installing it separately also keeps the noble
  # rename from taking the whole batch down with it.
  glib_ok=""
  for pkg in $GLIB_LIBS; do
    if apt-get install -y -qq --no-install-recommends "$pkg" 2>/dev/null; then
      echo "[start.sh]   ok: $pkg"
      glib_ok="$pkg"
      break
    fi
  done
  if [ -z "$glib_ok" ]; then
    echo "[start.sh]   FAILED: no glib package installed ($GLIB_LIBS)."
    echo "[start.sh]   WeasyPrint will not load. Check the package name for this image."
  fi

  # Deliberately NOT swallowing stderr: a silent failure here produces an app
  # that looks healthy but cannot mint a single document.
  if apt-get install -y -qq --no-install-recommends $WEASY_LIBS; then
    echo "[start.sh] Native libraries installed."
  else
    # One bad package name aborts the whole batch, so retry individually —
    # three of four libraries is still a working renderer on most images.
    echo "[start.sh] Batch install failed; retrying package by package..."
    for pkg in $WEASY_LIBS; do
      apt-get install -y -qq --no-install-recommends "$pkg" \
        && echo "[start.sh]   ok: $pkg" \
        || echo "[start.sh]   FAILED: $pkg"
    done
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

# ── Static files ─────────────────────────────────────────────────────────────
# WhiteNoise serves from STATIC_ROOT (staticfiles/), which is gitignored and NOT
# in the deploy artifact — so it must be built here. Without this, prod serves a
# stale (or missing) bundle: e.g. the table-export button was in the source but
# never reached users because collectstatic never ran. Guarded so a static build
# hiccup can't take the whole app down (set -e is on).
echo "[start.sh] Collecting static files..."
python manage.py collectstatic --noinput \
  && echo "[start.sh] Static files collected." \
  || echo "[start.sh] WARNING: collectstatic failed; static assets may be stale."

# ── Database ─────────────────────────────────────────────────────────────────
# Apply migrations on every start — idempotent, no-op when up to date.
python manage.py migrate --noinput

exec gunicorn Inventory_management_system.wsgi --bind=0.0.0.0:${PORT:-8000} --log-file -
