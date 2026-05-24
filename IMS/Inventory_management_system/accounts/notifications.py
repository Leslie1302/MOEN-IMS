import requests
import logging
from typing import Optional, Union, List
from django.contrib.auth.models import User
from .token_manager import get_valid_token

logger = logging.getLogger(__name__)

GRAPH_SEND_MAIL_URL = "https://graph.microsoft.com/v1.0/me/sendMail"


def send_email_notification(
    user: User,
    to: Union[str, List[str]],
    subject: str,
    body: str,
    body_type: str = "HTML",
    cc: Optional[List[str]] = None,
    save_to_sent_items: bool = True,
    attachments: Optional[List[dict]] = None,
) -> dict:
    """
    Send an email via Microsoft Graph API on behalf of `user`.

    `attachments` is an optional list of Graph fileAttachment objects each
    shaped like:
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": "filename.pdf",
            "contentType": "application/pdf",
            "contentBytes": "<base64-encoded content>",
        }
    The caller is responsible for base64-encoding contentBytes.
    """
    token = get_valid_token(user)
    recipients = [to] if isinstance(to, str) else to

    message = {
        "subject": subject,
        "body": {
            "contentType": body_type,
            "content": body,
        },
        "toRecipients": [
            {"emailAddress": {"address": addr}} for addr in recipients
        ],
    }

    if cc:
        message["ccRecipients"] = [
            {"emailAddress": {"address": addr}} for addr in cc
        ]

    if attachments:
        message["attachments"] = attachments

    payload = {
        "message": message,
        "saveToSentItems": save_to_sent_items,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    response = requests.post(GRAPH_SEND_MAIL_URL, json=payload, headers=headers, timeout=30)

    if response.status_code == 202:
        return {"success": True}

    try:
        error_detail = response.json().get("error", {})
        error_code = error_detail.get("code", "Unknown")
        error_message = error_detail.get("message", response.text)
    except Exception:
        error_code = str(response.status_code)
        error_message = response.text

    logger.error(f"Graph API error for user {user.id}: [{error_code}] {error_message}")
    raise RuntimeError(f"Graph API error [{error_code}]: {error_message}")
