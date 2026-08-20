"""Flusso OAuth 2.0 Google (RF-005→RF-010, flusso 8.2 passo 1) via authlib,
come da stack tecnologico (sezione 6.1). Scope minimi (sezione 11.3, punto 4):
sola lettura/invio Gmail necessari, sola lettura/creazione eventi Calendar.
"""
from __future__ import annotations

import requests
from authlib.integrations.requests_client import OAuth2Session
from authlib.oauth2.rfc6749.errors import OAuth2Error

from app.config import Settings

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


class GoogleOAuthError(RuntimeError):
    """Sollevato quando manca la configurazione OAuth o una chiamata a Google fallisce."""


def _require_config(settings: Settings) -> None:
    if not (settings.google_client_id and settings.google_client_secret and settings.google_redirect_uri):
        raise GoogleOAuthError(
            "GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET/GOOGLE_REDIRECT_URI non configurati"
        )


def _client(settings: Settings) -> OAuth2Session:
    return OAuth2Session(
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        redirect_uri=settings.google_redirect_uri,
        scope=" ".join(SCOPES),
    )


def build_authorization_url(settings: Settings) -> tuple[str, str]:
    """Ritorna (url, state). `access_type=offline` + `prompt=consent` sono
    necessari per ottenere sempre un refresh_token, non solo al primo consenso."""
    _require_config(settings)
    client = _client(settings)
    uri, state = client.create_authorization_url(
        AUTHORIZATION_URL, access_type="offline", prompt="consent"
    )
    return uri, state


def exchange_code(code: str, settings: Settings) -> dict:
    """Scambia il codice di autorizzazione per access/refresh token."""
    _require_config(settings)
    client = _client(settings)
    try:
        token = client.fetch_token(TOKEN_URL, code=code)
    except (OAuth2Error, requests.RequestException) as exc:
        raise GoogleOAuthError(f"Scambio codice fallito: {exc}") from exc
    return token


def refresh_access_token(refresh_token: str, settings: Settings) -> dict:
    _require_config(settings)
    client = _client(settings)
    try:
        token = client.refresh_token(TOKEN_URL, refresh_token=refresh_token)
    except (OAuth2Error, requests.RequestException) as exc:
        raise GoogleOAuthError(f"Refresh del token fallito: {exc}") from exc
    return token


def revoke_token(token: str, settings: Settings) -> None:
    try:
        response = requests.post(
            REVOKE_URL,
            params={"token": token},
            timeout=settings.external_service_timeout_seconds,
        )
    except requests.RequestException as exc:
        raise GoogleOAuthError(f"Revoca fallita: {exc}") from exc
    # Google risponde 200 anche se il token era già invalido/scaduto: idempotente.
    if response.status_code not in (200, 400):
        raise GoogleOAuthError(f"Revoca fallita: HTTP {response.status_code}")
