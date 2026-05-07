"""
Gmail tools — read, categorize, and reply to emails via the Gmail API.

Authentication uses OAuth 2.0. On first use the browser will open for consent.
Subsequent calls reuse the cached token.

Environment variables:
    GMAIL_CREDENTIALS_PATH  Path to the OAuth client-secret JSON downloaded from
                            Google Cloud Console (default: gmail_credentials.json).
    GMAIL_TOKEN_PATH        Where to persist the refreshable access token
                            (default: gmail_token.json).
"""

from __future__ import annotations

import base64
import json
import os
from email.mime.text import MIMEText
from pathlib import Path
from typing import Annotated

from langchain_core.tools import tool


_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

_TOKEN_PATH = Path(os.environ.get("GMAIL_TOKEN_PATH", "gmail_token.json"))
_CREDS_PATH = Path(os.environ.get("GMAIL_CREDENTIALS_PATH", "gmail_credentials.json"))


def _get_gmail_service():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google API packages are not installed. Run: "
            "pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        ) from exc

    creds = None
    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CREDS_PATH.exists():
                raise RuntimeError(
                    f"Gmail credentials file not found at '{_CREDS_PATH}'. "
                    "Download an OAuth 2.0 client-secret JSON from Google Cloud Console "
                    "and set GMAIL_CREDENTIALS_PATH to its path."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDS_PATH), _SCOPES)
            creds = flow.run_local_server(port=0)
        _TOKEN_PATH.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


def _extract_plain_body(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    if mime_type.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _extract_plain_body(part)
            if text:
                return text
    return ""


def _message_to_dict(msg: dict, include_body: bool = True) -> dict:
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("threadId"),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "date": headers.get("date", ""),
        "snippet": msg.get("snippet", ""),
        "body": _extract_plain_body(msg.get("payload", {})) if include_body else "",
        "labels": msg.get("labelIds", []),
    }


_GMAIL_CATEGORIES: dict[str, str] = {
    "CATEGORY_PERSONAL": "personal",
    "CATEGORY_SOCIAL": "social",
    "CATEGORY_PROMOTIONS": "promotions",
    "CATEGORY_UPDATES": "updates",
    "CATEGORY_FORUMS": "forums",
    "INBOX": "inbox",
    "SENT": "sent",
    "DRAFT": "drafts",
    "SPAM": "spam",
    "TRASH": "trash",
    "STARRED": "starred",
    "IMPORTANT": "important",
    "UNREAD": "unread",
}


@tool
def check_email(
    max_results: Annotated[int, "Number of emails to return (1-50, default 10)"] = 10,
    query: Annotated[str, "Gmail search query, e.g. 'is:unread', 'from:alice@example.com'"] = "",
    include_body: Annotated[bool, "Fetch the full message body (false for metadata-only)"] = True,
) -> str:
    """Fetch emails from the Gmail inbox. Returns JSON array with id, subject, from, date, body, labels."""
    try:
        max_results = max(1, min(max_results, 50))
        service = _get_gmail_service()
        list_kwargs: dict = {"userId": "me", "maxResults": max_results, "labelIds": ["INBOX"]}
        if query:
            list_kwargs["q"] = query
        response = service.users().messages().list(**list_kwargs).execute()
        emails: list[dict] = []
        for meta in response.get("messages", []):
            if include_body:
                msg = service.users().messages().get(userId="me", id=meta["id"], format="full").execute()
            else:
                msg = service.users().messages().get(
                    userId="me", id=meta["id"], format="metadata",
                    metadataHeaders=["Subject", "From", "To", "Cc", "Date"],
                ).execute()
            emails.append(_message_to_dict(msg, include_body=include_body))
        return json.dumps(emails, indent=2)
    except RuntimeError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: Gmail API error: {exc}"


@tool
def categorize_emails(
    max_results: Annotated[int, "Total emails to fetch (1-100, default 50)"] = 50,
    query: Annotated[str, "Optional Gmail search query"] = "",
) -> str:
    """Fetch emails and group them by Gmail category. Returns JSON object mapping category to email list."""
    try:
        max_results = max(1, min(max_results, 100))
        service = _get_gmail_service()
        list_kwargs: dict = {"userId": "me", "maxResults": max_results}
        if query:
            list_kwargs["q"] = query
        response = service.users().messages().list(**list_kwargs).execute()
        categories: dict[str, list[dict]] = {}
        for meta in response.get("messages", []):
            msg = service.users().messages().get(
                userId="me", id=meta["id"], format="metadata",
                metadataHeaders=["Subject", "From", "To", "Date"],
            ).execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            summary = {
                "id": msg["id"], "thread_id": msg["threadId"],
                "subject": headers.get("subject", ""), "from": headers.get("from", ""),
                "date": headers.get("date", ""), "snippet": msg.get("snippet", ""),
                "labels": msg.get("labelIds", []),
            }
            label_ids: list[str] = msg.get("labelIds", [])
            assigned = False
            for label_id in label_ids:
                if label_id.startswith("CATEGORY_") and label_id in _GMAIL_CATEGORIES:
                    category = _GMAIL_CATEGORIES[label_id]
                    categories.setdefault(category, []).append(summary)
                    assigned = True
                    break
            if not assigned:
                categories.setdefault("uncategorized", []).append(summary)
        return json.dumps(categories, indent=2)
    except RuntimeError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: Gmail API error: {exc}"


@tool
def reply_to_email(
    message_id: Annotated[str, "Gmail message ID to reply to (from check_email 'id' field)"],
    body: Annotated[str, "Plain-text content of the reply"],
) -> str:
    """Send a plain-text reply to an existing Gmail message. Returns JSON with sent message id and thread_id."""
    try:
        service = _get_gmail_service()
        original = service.users().messages().get(
            userId="me", id=message_id, format="metadata",
            metadataHeaders=["Subject", "From", "To", "Cc", "Message-ID", "References"],
        ).execute()
        headers = {h["name"].lower(): h["value"] for h in original.get("payload", {}).get("headers", [])}
        thread_id = original["threadId"]
        reply_to_addr = headers.get("from", "")
        subject = headers.get("subject", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        orig_message_id = headers.get("message-id", "")
        existing_refs = headers.get("references", "")
        references = f"{existing_refs} {orig_message_id}".strip() if orig_message_id else existing_refs
        mime_msg = MIMEText(body, "plain", "utf-8")
        mime_msg["To"] = reply_to_addr
        mime_msg["Subject"] = subject
        if orig_message_id:
            mime_msg["In-Reply-To"] = orig_message_id
        if references:
            mime_msg["References"] = references
        raw = base64.urlsafe_b64encode(mime_msg.as_bytes()).decode("utf-8")
        sent = service.users().messages().send(userId="me", body={"raw": raw, "threadId": thread_id}).execute()
        return json.dumps({"sent_message_id": sent.get("id"), "thread_id": sent.get("threadId")}, indent=2)
    except RuntimeError as exc:
        return f"ERROR: {exc}"
    except Exception as exc:
        return f"ERROR: Gmail API error: {exc}"