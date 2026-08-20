"""Integrazione Gmail (RF-005→RF-008, flusso 8.2). Scope minimi già
autorizzati in `app.google_oauth` (`gmail.readonly`, `gmail.send`,
`gmail.compose`)."""
from __future__ import annotations

import base64
from email.mime.text import MIMEText

import requests

from app.config import Settings

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailError(RuntimeError):
    """Sollevato quando una chiamata all'API Gmail fallisce."""


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _get(url: str, access_token: str, settings: Settings, params: dict | None = None) -> dict:
    try:
        response = requests.get(
            url, headers=_headers(access_token), params=params,
            timeout=settings.external_service_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GmailError(f"Chiamata a Gmail fallita: {exc}") from exc
    return response.json()


def _header_value(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _extract_snippet_fields(message: dict) -> dict:
    payload_headers = message.get("payload", {}).get("headers", [])
    return {
        "id": message["id"],
        "thread_id": message.get("threadId"),
        "from": _header_value(payload_headers, "From"),
        "subject": _header_value(payload_headers, "Subject"),
        "date": _header_value(payload_headers, "Date"),
        "snippet": message.get("snippet", ""),
    }


def list_messages(access_token: str, settings: Settings, query: str = "", max_results: int = 10) -> list[dict]:
    """RF-005/RF-006: lista email (con o senza filtro di ricerca)."""
    list_data = _get(
        f"{GMAIL_BASE}/messages",
        access_token,
        settings,
        params={"maxResults": max_results, "q": query} if query else {"maxResults": max_results},
    )
    message_ids = [m["id"] for m in list_data.get("messages", [])]

    results = []
    for message_id in message_ids:
        detail = _get(
            f"{GMAIL_BASE}/messages/{message_id}",
            access_token,
            settings,
            params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
        )
        results.append(_extract_snippet_fields(detail))
    return results


def _extract_body_text(payload: dict) -> str:
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"] + "===").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        text = _extract_body_text(part)
        if text:
            return text
    return ""


def get_message(access_token: str, message_id: str, settings: Settings) -> dict:
    detail = _get(
        f"{GMAIL_BASE}/messages/{message_id}", access_token, settings, params={"format": "full"}
    )
    fields = _extract_snippet_fields(detail)
    fields["body"] = _extract_body_text(detail.get("payload", {}))
    fields["message_id_header"] = _header_value(detail.get("payload", {}).get("headers", []), "Message-ID")
    return fields


def create_draft(
    access_token: str,
    settings: Settings,
    *,
    to: str,
    subject: str,
    body: str,
    reply_to_message_id: str | None = None,
) -> str:
    """RF-007. Se `reply_to_message_id` è dato, la bozza viene agganciata
    correttamente al thread originale (In-Reply-To/References/threadId)."""
    mime = MIMEText(body)
    mime["to"] = to
    mime["subject"] = subject

    thread_id = None
    if reply_to_message_id:
        original = get_message(access_token, reply_to_message_id, settings)
        thread_id = original["thread_id"]
        if original["message_id_header"]:
            mime["In-Reply-To"] = original["message_id_header"]
            mime["References"] = original["message_id_header"]

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")
    message_body = {"raw": raw}
    if thread_id:
        message_body["threadId"] = thread_id

    try:
        response = requests.post(
            f"{GMAIL_BASE}/drafts",
            headers=_headers(access_token),
            json={"message": message_body},
            timeout=settings.external_service_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GmailError(f"Creazione bozza fallita: {exc}") from exc

    return response.json()["id"]


def send_draft(access_token: str, draft_id: str, settings: Settings) -> str:
    """RF-008: invia una bozza già creata. Ritorna il message_id inviato."""
    try:
        response = requests.post(
            f"{GMAIL_BASE}/drafts/send",
            headers=_headers(access_token),
            json={"id": draft_id},
            timeout=settings.external_service_timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise GmailError(f"Invio bozza fallito: {exc}") from exc

    return response.json()["id"]
