import os
import uuid
import logging
import msal
from django.conf import settings
from django.contrib.auth import login, logout
from django.shortcuts import redirect
from django.http import HttpResponseBadRequest
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User
from django.urls import reverse
from django.views.decorators.http import require_POST
from .models import MicrosoftCredentials

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trusted admin bootstrap.
#
# Emails listed here (or in TRUSTED_ADMIN_EMAILS env var, comma-separated) are
# automatically promoted to is_superuser/is_staff on Microsoft OAuth login.
# This is the only way to recover from a fresh database when no superuser
# exists yet -- without it, every signed-in user gets bounced to the
# "awaiting authorization" page by UserRoleMiddleware.
#
# When portal/Kudu access is restored, prefer the env var and remove the
# hardcoded list.
# ---------------------------------------------------------------------------
_HARDCODED_TRUSTED_ADMIN_EMAILS = {
    "leslie.adjetey@energymin.gov.gh",
}
_ENV_TRUSTED_ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("TRUSTED_ADMIN_EMAILS", "").split(",")
    if e.strip()
}
TRUSTED_ADMIN_EMAILS = {
    e.lower() for e in _HARDCODED_TRUSTED_ADMIN_EMAILS
} | _ENV_TRUSTED_ADMIN_EMAILS

def _callback_redirect_uri(request):
    """
    Keep localhost dynamic so the session cookie and callback host match,
    but use the configured production redirect URI outside local development.
    """
    configured = settings.MICROSOFT.get("REDIRECT_URI", "").strip()
    host = request.get_host().split(":")[0].lower()
    if host in {"localhost", "127.0.0.1"}:
        return request.build_absolute_uri(reverse("ms_callback"))
    return configured or request.build_absolute_uri(reverse("ms_callback"))

def _msal_app():
    ms = settings.MICROSOFT
    return msal.ConfidentialClientApplication(
        client_id=ms["CLIENT_ID"],
        client_credential=ms["CLIENT_SECRET"],
        authority=ms["AUTHORITY"],
    )

def ms_login(request):
    """
    Redirects to Microsoft's OAuth login page.
    Route: GET /auth/login/
    """
    ms = settings.MICROSOFT
    state = str(uuid.uuid4())
    request.session["oauth_state"] = state
    request.session.save() #Save the session to ensure state is stored before redirecting
    callback_uri = _callback_redirect_uri(request)
    auth_url = _msal_app().get_authorization_request_url(
        scopes=ms["SCOPES"],
        state=state,
        redirect_uri=callback_uri,
    )
    return redirect(auth_url)

def ms_callback(request):
    """
    Handles the OAuth callback from Microsoft.
    Exchanges the authorization code for tokens and logs the user in.
    Route: GET /auth/callback/?code=...&state=...
    """
    ms = settings.MICROSOFT
    if request.GET.get("state") != request.session.pop("oauth_state", None):
        return HttpResponseBadRequest("State mismatch. Possible CSRF attack.")
    
    code = request.GET.get("code")
    if not code:
        return HttpResponseBadRequest("No authorization code returned from Microsoft.")
        
    callback_uri = _callback_redirect_uri(request)
    result = _msal_app().acquire_token_by_authorization_code(
        code=code,
        scopes=ms["SCOPES"],
        redirect_uri=callback_uri,
    )
    
    if "error" in result:
        return HttpResponseBadRequest(
            f"Token acquisition failed: {result.get('error_description', result['error'])}"
        )
        
    claims = result.get("id_token_claims", {})
    ms_id = claims.get("oid")
    ms_email = claims.get("preferred_username") or claims.get("email", "")
    display_name = claims.get("name", "")
    
    user, created = User.objects.get_or_create(
        email=ms_email,
        defaults={
            "username": ms_email,
            "first_name": display_name.split()[0] if display_name else "",
            "last_name": " ".join(display_name.split()[1:]) if display_name else "",
        }
    )

    # Auto-promote trusted admin emails to superuser. Idempotent: only writes
    # when the user isn't already staff+superuser. See TRUSTED_ADMIN_EMAILS.
    if ms_email and ms_email.lower() in TRUSTED_ADMIN_EMAILS:
        if not user.is_superuser or not user.is_staff:
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            user.save(update_fields=["is_superuser", "is_staff", "is_active"])
            logger.warning("Auto-promoted trusted admin email %s to superuser.", ms_email)
            # Phase G audit trail.
            try:
                from Inventory.services.audit import audit as _audit
                _audit(user, user, 'auth.superuser_auto_promoted',
                       f"Trusted email {ms_email} auto-promoted to superuser via OAuth login")
            except Exception:
                pass

    creds, creds_created = MicrosoftCredentials.objects.get_or_create(
        user=user,
        defaults={
            "ms_id": ms_id,
            "ms_email": ms_email,
        }
    )
    
    creds.ms_id = ms_id
    creds.ms_email = ms_email
    creds.access_token = result["access_token"]
    creds.refresh_token = result.get("refresh_token")
    creds.token_expires_at = timezone.now() + timedelta(seconds=result.get("expires_in", 3600))
    creds.save()
    
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("/")

@require_POST
def ms_logout(request):
    """
    Ends the Django session and redirects to Microsoft's logout endpoint.
    Route: POST /auth/logout/
    """
    logout(request)
    ms_logout_url = (
        f"{settings.MICROSOFT['AUTHORITY']}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={settings.MICROSOFT['REDIRECT_URI']}"
    )
    return redirect(ms_logout_url)
