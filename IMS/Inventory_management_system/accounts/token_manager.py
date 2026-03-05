import msal
import logging
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth.models import User
from .models import MicrosoftCredentials

logger = logging.getLogger(__name__)

def get_valid_token(user: User) -> str:
    """
    Returns a valid access token for the given user.
    Refreshes automatically if expired.
    Raises RuntimeError if the refresh token is missing or refresh fails.
    The caller should redirect the user to /auth/login/ in that case.
    """
    try:
        creds = MicrosoftCredentials.objects.get(user=user)
    except MicrosoftCredentials.DoesNotExist:
        raise RuntimeError(f"No Microsoft credentials found for user {user.id}.")
        
    if not creds.is_token_expired():
        return creds.access_token

    if not creds.refresh_token:
        raise RuntimeError(
            f"No refresh token for user {user.id}. "
            "User must re-authenticate at /auth/login/."
        )

    ms = settings.MICROSOFT
    app = msal.ConfidentialClientApplication(
        client_id=ms["CLIENT_ID"],
        client_credential=ms["CLIENT_SECRET"],
        authority=ms["AUTHORITY"],
    )
    
    result = app.acquire_token_by_refresh_token(
        refresh_token=creds.refresh_token,
        scopes=ms["SCOPES"],
    )
    
    if "error" in result:
        logger.error(
            f"Token refresh failed for user {user.id}: "
            f"{result.get('error_description', result['error'])}"
        )
        raise RuntimeError(
            f"Token refresh failed: {result.get('error_description')}. "
            "User must re-authenticate."
        )
        
    creds.access_token = result["access_token"]
    if "refresh_token" in result:
        creds.refresh_token = result["refresh_token"]
    creds.token_expires_at = timezone.now() + timedelta(seconds=result.get("expires_in", 3600))
    creds.save(update_fields=["_access_token", "_refresh_token", "token_expires_at"])
    
    return creds.access_token
