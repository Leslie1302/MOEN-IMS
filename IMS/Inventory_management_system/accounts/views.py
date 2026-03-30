import uuid
import msal
from django.conf import settings
from django.contrib.auth import login, logout
from django.shortcuts import redirect
from django.http import HttpResponseBadRequest
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User
from .models import MicrosoftCredentials

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
    auth_url = _msal_app().get_authorization_request_url(
        scopes=ms["SCOPES"],
        state=state,
        redirect_uri=ms["REDIRECT_URI"],
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
        
    result = _msal_app().acquire_token_by_authorization_code(
        code=code,
        scopes=ms["SCOPES"],
        redirect_uri=ms["REDIRECT_URI"],
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

def ms_logout(request):
    """
    Ends the Django session and redirects to Microsoft's logout endpoint.
    Route: GET /auth/logout/
    """
    logout(request)
    ms_logout_url = (
        f"{settings.MICROSOFT['AUTHORITY']}/oauth2/v2.0/logout"
        f"?post_logout_redirect_uri={settings.MICROSOFT['REDIRECT_URI']}"
    )
    return redirect(ms_logout_url)
